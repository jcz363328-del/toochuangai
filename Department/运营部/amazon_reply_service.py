"""
亚马逊站内信回复后端服务层。

用途：
1. 从 SQL Server 的两张表读取规则和场景。
2. 根据买家问题匹配最接近的回复场景。
3. 调用 SiliconFlow Kimi 生成英文卖家回复。
4. 对生成结果做禁用词检查。
5. 模型失败时使用数据库模板兜底。

接入方式：
- 在你现有的 Python API 里初始化 AmazonReplyService。
- 接口收到 buyer_question 后调用 service.generate_reply(...)。

依赖：
pip install python-tds
"""

from __future__ import annotations

import json
import os
import re
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from secret_settings import env, sql_server_config

try:
    import pytds
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("缺少 SQL Server 驱动，请先安装：pip install python-tds") from exc


RULE_TABLE = "dbo.YaMaXunHuiFuGuiZe"
SCENARIO_TABLE = "dbo.YaMaXunHuiFuChangJing"

RULE_TYPE_PROHIBITED = "禁用词"
RULE_TYPE_SENSITIVE = "敏感短语"
RULE_TYPE_STYLE = "通用回复规则"

MODEL_ALIASES = {
    "kimi-2.6": "Pro/moonshotai/Kimi-K2.6",
    "kimi-k2.6": "Pro/moonshotai/Kimi-K2.6",
}


@dataclass(frozen=True)
class SqlServerConfig:
    """SQL Server 连接配置。密码建议从环境变量读取，不要写死在代码里。"""

    server: str
    database: str
    user: str
    password: str
    port: int = 1433
    login_timeout: int = 20
    request_timeout: int = 60

    @classmethod
    def from_env(cls) -> "SqlServerConfig":
        db_defaults = sql_server_config(include_port=True)
        return cls(
            server=str(db_defaults.get("server") or ""),
            port=int(db_defaults.get("port") or 1433),
            database=str(db_defaults.get("database") or ""),
            user=str(db_defaults.get("user") or ""),
            password=str(db_defaults.get("password") or ""),
        )


@dataclass(frozen=True)
class SiliconFlowConfig:
    """SiliconFlow 模型调用配置。"""

    api_key: str
    model: str = "Pro/moonshotai/Kimi-K2.6"
    base_url: str = "https://api.siliconflow.cn/v1/chat/completions"
    temperature: float = 0.2
    max_tokens: int = 900
    timeout_seconds: int = 180
    retry_count: int = 1

    @classmethod
    def from_env(cls) -> "SiliconFlowConfig":
        return cls(
            api_key=env("SILICONFLOW_API_KEY") or env("OPENAI_API_KEY"),
            model=normalize_model(env("SILICONFLOW_MODEL", env("OPENAI_TEXT_MODEL", "Pro/moonshotai/Kimi-K2.6"))),
            base_url=env("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1/chat/completions"),
            temperature=float(env("SILICONFLOW_TEMPERATURE", "0.2")),
            max_tokens=int(env("SILICONFLOW_MAX_TOKENS", "900")),
            timeout_seconds=int(env("SILICONFLOW_TIMEOUT_SECONDS", "180")),
            retry_count=int(env("SILICONFLOW_RETRY_COUNT", "1")),
        )


class AmazonReplyService:
    """可直接接入 Python 项目的服务类。"""

    def __init__(self, db_config: SqlServerConfig, ai_config: SiliconFlowConfig):
        self.db_config = db_config
        self.ai_config = ai_config
        self.knowledge_cache: dict[str, Any] | None = None
        self.knowledge_cache_time = 0.0
        self.knowledge_cache_ttl_seconds = int(os.getenv("AMAZON_REPLY_KNOWLEDGE_TTL_SECONDS", "300") or 300)
        self.fast_template_enabled = str(os.getenv("AMAZON_REPLY_FAST_TEMPLATE", "1")).strip().lower() not in {
            "0",
            "false",
            "off",
            "no",
        }

    @classmethod
    def from_env(cls) -> "AmazonReplyService":
        """从环境变量创建服务实例，适合在 API 启动时初始化一次。"""

        return cls(SqlServerConfig.from_env(), SiliconFlowConfig.from_env())

    def generate_reply(self, buyer_question: str, extra_context: str = "") -> dict[str, Any]:
        """
        生成卖家回复。

        返回结构适合直接作为 API JSON 响应：
        {
          "modelOk": bool,
          "matchedScenarios": [...],
          "prohibitedHits": [...],
          "category": "...",
          "englishReply": "...",
          "chineseExplanation": "...",
          "requiredInfo": "...",
          "riskNotes": "..."
        }
        """

        buyer_question = clean(buyer_question)
        extra_context = clean(extra_context)
        if not buyer_question:
            raise ValueError("buyer_question 不能为空")

        started_at = time.perf_counter()
        knowledge = self.load_knowledge()
        knowledge_ms = int((time.perf_counter() - started_at) * 1000)
        matched_scenarios = self.match_scenarios(
            text=f"{buyer_question}\n{extra_context}",
            scenarios=knowledge["scenarios"],
            limit=2,
        )

        model_ok = False
        source = "model"
        model_ms = 0
        if self._should_use_fast_template(buyer_question, extra_context, matched_scenarios):
            result = self._local_fallback(matched_scenarios)
            source = "template"
            result["riskNotes"] = "已使用匹配场景模板快速生成，并完成禁用词检查。"
        else:
            model_started_at = time.perf_counter()
            try:
                result = self._generate_with_model(buyer_question, extra_context, knowledge, matched_scenarios)
                model_ok = True
            except Exception as exc:
                # 模型异常时不要让业务中断，使用最接近的数据库模板兜底。
                result = self._local_fallback(matched_scenarios)
                source = "fallback"
                result["riskNotes"] = f"模型调用失败，已使用本地模板。错误：{exc}"
            finally:
                model_ms = int((time.perf_counter() - model_started_at) * 1000)

        prohibited_hits = self.scan_reply(result.get("englishReply", ""), knowledge["prohibitedTerms"])
        return {
            "modelOk": model_ok,
            "source": source,
            "elapsedMs": int((time.perf_counter() - started_at) * 1000),
            "knowledgeMs": knowledge_ms,
            "modelMs": model_ms,
            "matchedScenarios": [{"id": item["id"], "title": item["title"]} for item in matched_scenarios],
            "prohibitedHits": prohibited_hits,
            "category": result.get("category", ""),
            "englishReply": result.get("englishReply", ""),
            "chineseExplanation": result.get("chineseExplanation", ""),
            "requiredInfo": result.get("requiredInfo", ""),
            "riskNotes": result.get("riskNotes", ""),
        }

    def load_knowledge(self) -> dict[str, Any]:
        """从 SQL Server 读取启用中的规则和场景。"""

        now = time.monotonic()
        if (
            self.knowledge_cache
            and self.knowledge_cache_ttl_seconds > 0
            and now - self.knowledge_cache_time < self.knowledge_cache_ttl_seconds
        ):
            return self.knowledge_cache

        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT Id, GuiZeLeiXing, NeiRong, AnQuanTiShi, PaiXu
                FROM {RULE_TABLE}
                WHERE QiYong = 1
                ORDER BY PaiXu ASC, Id ASC
                """
            )
            rule_rows = cur.fetchall()

            cur.execute(
                f"""
                SELECT Id, BiaoTi, GuanJianCi, GouMaiZheWenTiShiLi,
                       MaiJiaHuiFuYingWen, ZhongWenShuoMing, NeiBuBeiZhu, PaiXu
                FROM {SCENARIO_TABLE}
                WHERE QiYong = 1
                ORDER BY PaiXu ASC, Id ASC
                """
            )
            scenario_rows = cur.fetchall()

        prohibited_terms = []
        sensitive_phrases = []
        style_rules = []

        for row in rule_rows:
            rule_type = clean(row["GuiZeLeiXing"])
            if rule_type == RULE_TYPE_PROHIBITED:
                prohibited_terms.append(clean(row["NeiRong"]))
            elif rule_type == RULE_TYPE_SENSITIVE:
                sensitive_phrases.append(
                    {
                        "phrase": clean(row["NeiRong"]),
                        "safeHint": clean(row["AnQuanTiShi"]),
                    }
                )
            elif rule_type == RULE_TYPE_STYLE:
                style_rules.append(clean(row["NeiRong"]))

        scenarios = []
        for row in scenario_rows:
            scenarios.append(
                {
                    "id": row["Id"],
                    "title": clean(row["BiaoTi"]),
                    "keywords": parse_json_array(row["GuanJianCi"]),
                    "buyerExamples": parse_json_array(row["GouMaiZheWenTiShiLi"]),
                    "sellerReplyEn": clean(row["MaiJiaHuiFuYingWen"]),
                    "sellerReplyZh": clean(row["ZhongWenShuoMing"]),
                    "internalNotes": clean(row["NeiBuBeiZhu"]),
                }
            )

        knowledge = {
            "prohibitedTerms": prohibited_terms,
            "sensitivePhrases": sensitive_phrases,
            "styleRules": style_rules,
            "scenarios": scenarios,
        }
        self.knowledge_cache = knowledge
        self.knowledge_cache_time = now
        return knowledge

    def invalidate_knowledge_cache(self) -> None:
        self.knowledge_cache = None
        self.knowledge_cache_time = 0.0

    def list_management_items(self) -> dict[str, Any]:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT Id, GuiZeLeiXing, NeiRong, AnQuanTiShi, PaiXu
                FROM {RULE_TABLE}
                WHERE QiYong = 1
                ORDER BY PaiXu ASC, Id ASC
                """
            )
            rule_rows = cur.fetchall()
            cur.execute(
                f"""
                SELECT Id, BiaoTi, GuanJianCi, GouMaiZheWenTiShiLi,
                       MaiJiaHuiFuYingWen, ZhongWenShuoMing, NeiBuBeiZhu, PaiXu
                FROM {SCENARIO_TABLE}
                WHERE QiYong = 1
                ORDER BY PaiXu ASC, Id ASC
                """
            )
            scenario_rows = cur.fetchall()

        prohibited_terms = []
        sensitive_phrases = []
        for row in rule_rows:
            rule_type = clean(row["GuiZeLeiXing"])
            item = {
                "id": row["Id"],
                "content": clean(row["NeiRong"]),
                "safeHint": clean(row["AnQuanTiShi"]),
                "sortOrder": row["PaiXu"],
            }
            if rule_type == RULE_TYPE_PROHIBITED:
                prohibited_terms.append(item)
            elif rule_type == RULE_TYPE_SENSITIVE:
                sensitive_phrases.append(item)

        scenarios = []
        for row in scenario_rows:
            scenarios.append(
                {
                    "id": row["Id"],
                    "title": clean(row["BiaoTi"]),
                    "keywords": parse_json_array(row["GuanJianCi"]),
                    "buyerExamples": parse_json_array(row["GouMaiZheWenTiShiLi"]),
                    "sellerReplyEn": clean(row["MaiJiaHuiFuYingWen"]),
                    "sellerReplyZh": clean(row["ZhongWenShuoMing"]),
                    "internalNotes": clean(row["NeiBuBeiZhu"]),
                    "sortOrder": row["PaiXu"],
                }
            )
        return {
            "prohibitedTerms": prohibited_terms,
            "sensitivePhrases": sensitive_phrases,
            "scenarios": scenarios,
        }

    def _next_sort_order(self, table_name: str) -> int:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(f"SELECT ISNULL(MAX(PaiXu), 0) + 10 AS NextPaiXu FROM {table_name}")
            row = cur.fetchone()
        if isinstance(row, dict):
            return int(row.get("NextPaiXu") or 10)
        return int(row[0] if row else 10)

    def add_rule(self, rule_type: str, content: str, safe_hint: str = "") -> dict[str, Any]:
        rule_type = clean(rule_type)
        content = clean(content)
        safe_hint = clean(safe_hint)
        if rule_type not in {RULE_TYPE_PROHIBITED, RULE_TYPE_SENSITIVE}:
            raise ValueError("rule_type 只能是禁用词或敏感短语")
        if not content:
            raise ValueError("内容不能为空")
        sort_order = self._next_sort_order(RULE_TABLE)
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                f"""
                INSERT INTO {RULE_TABLE} (GuiZeLeiXing, NeiRong, AnQuanTiShi, PaiXu, QiYong)
                OUTPUT INSERTED.Id
                VALUES (%s, %s, %s, %s, 1)
                """,
                (rule_type, content, safe_hint, sort_order),
            )
            row = cur.fetchone()
        item_id = row[0] if row and not isinstance(row, dict) else (row.get("Id") if row else None)
        self.invalidate_knowledge_cache()
        return {
            "id": item_id,
            "content": content,
            "safeHint": safe_hint,
            "sortOrder": sort_order,
        }

    def disable_rule(self, rule_id: int) -> None:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                f"""
                UPDATE {RULE_TABLE}
                SET QiYong = 0
                WHERE Id = %s AND GuiZeLeiXing IN (%s, %s)
                """,
                (int(rule_id), RULE_TYPE_PROHIBITED, RULE_TYPE_SENSITIVE),
            )
        self.invalidate_knowledge_cache()

    def add_scenario(
        self,
        title: str,
        keywords: list[str] | None = None,
        buyer_examples: list[str] | None = None,
        seller_reply_en: str = "",
        seller_reply_zh: str = "",
        internal_notes: str = "",
    ) -> dict[str, Any]:
        title = clean(title)
        if not title:
            raise ValueError("场景标题不能为空")
        keywords = [clean(item) for item in (keywords or []) if clean(item)]
        buyer_examples = [clean(item) for item in (buyer_examples or []) if clean(item)]
        seller_reply_en = clean(seller_reply_en)
        seller_reply_zh = clean(seller_reply_zh)
        internal_notes = clean(internal_notes)
        sort_order = self._next_sort_order(SCENARIO_TABLE)
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                f"""
                INSERT INTO {SCENARIO_TABLE}
                    (BiaoTi, GuanJianCi, GouMaiZheWenTiShiLi, MaiJiaHuiFuYingWen,
                     ZhongWenShuoMing, NeiBuBeiZhu, PaiXu, QiYong)
                OUTPUT INSERTED.Id
                VALUES (%s, %s, %s, %s, %s, %s, %s, 1)
                """,
                (
                    title,
                    json.dumps(keywords, ensure_ascii=False),
                    json.dumps(buyer_examples, ensure_ascii=False),
                    seller_reply_en,
                    seller_reply_zh,
                    internal_notes,
                    sort_order,
                ),
            )
            row = cur.fetchone()
        item_id = row[0] if row and not isinstance(row, dict) else (row.get("Id") if row else None)
        self.invalidate_knowledge_cache()
        return {
            "id": item_id,
            "title": title,
            "keywords": keywords,
            "buyerExamples": buyer_examples,
            "sellerReplyEn": seller_reply_en,
            "sellerReplyZh": seller_reply_zh,
            "internalNotes": internal_notes,
            "sortOrder": sort_order,
        }

    def disable_scenario(self, scenario_id: int) -> None:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                f"UPDATE {SCENARIO_TABLE} SET QiYong = 0 WHERE Id = %s",
                (int(scenario_id),),
            )
        self.invalidate_knowledge_cache()

    def match_scenarios(self, text: str, scenarios: list[dict[str, Any]], limit: int = 4) -> list[dict[str, Any]]:
        """根据关键词和买家示例做轻量匹配，返回最接近的场景。"""

        input_text = clean(text).lower()
        input_tokens = set(tokenize(input_text))
        scored = []

        for scenario in scenarios:
            score = 0

            # 关键词命中权重更高。
            for keyword in scenario.get("keywords", []):
                key = clean(keyword).lower()
                if key and key in input_text:
                    score += 4

            # 买家示例做词级重叠，提升同类问题的召回。
            for example in scenario.get("buyerExamples", []):
                for token in tokenize(example):
                    if token in input_tokens:
                        score += 1

            if score > 0:
                scored.append((score, scenario))

        scored.sort(key=lambda item: item[0], reverse=True)
        if scored:
            return [dict(scenario, _matchScore=score) for score, scenario in scored[:limit]]

        # 完全匹配不到时，至少给模型一个参考场景，避免空上下文。
        return [dict(scenarios[0], _matchScore=0)] if scenarios else []

    def scan_reply(self, reply: str, prohibited_terms: list[str]) -> list[str]:
        """扫描卖家英文回复中是否出现数据库里的禁用词。"""

        text = clean(reply).lower()
        hits = []
        for term in prohibited_terms:
            value = clean(term).lower()
            if not value:
                continue
            if re.fullmatch(r"[a-z0-9][a-z0-9 \-]*", value):
                pattern = rf"(?<![a-z0-9]){re.escape(value)}(?![a-z0-9])"
                if re.search(pattern, text):
                    hits.append(term)
            elif value in text:
                hits.append(term)
        return sorted(set(hits), key=str.lower)

    def _should_use_fast_template(
        self,
        buyer_question: str,
        extra_context: str,
        matched_scenarios: list[dict[str, Any]],
    ) -> bool:
        if not self.fast_template_enabled or extra_context:
            return False
        if len(clean(buyer_question)) > 420 or not matched_scenarios:
            return False
        if int(matched_scenarios[0].get("_matchScore") or 0) <= 0:
            return False
        return bool(clean(matched_scenarios[0].get("sellerReplyEn")))

    def _generate_with_model(
        self,
        buyer_question: str,
        extra_context: str,
        knowledge: dict[str, Any],
        matched_scenarios: list[dict[str, Any]],
    ) -> dict[str, str]:
        """调用 SiliconFlow Kimi，并解析为统一返回结构。"""

        if not self.ai_config.api_key:
            raise RuntimeError("缺少 SILICONFLOW_API_KEY")

        payload = {
            "model": normalize_model(self.ai_config.model),
            "temperature": self.ai_config.temperature,
            "max_tokens": self.ai_config.max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an Amazon seller in-message reply assistant. "
                        "Do not include prohibited words in the seller-facing English reply. "
                        "Do not ask buyers to affect public product opinions, scores, stars, or similar actions. "
                        "If a money return is needed, use split wording such as re-fund or ref-und. "
                        "Return compact JSON with keys: category, englishReply, chineseExplanation, requiredInfo, riskNotes."
                    ),
                },
                {
                    "role": "user",
                    "content": self._build_prompt(buyer_question, extra_context, knowledge, matched_scenarios),
                },
            ],
        }

        last_error: Exception | None = None
        for _ in range(self.ai_config.retry_count + 1):
            try:
                completion = self._post_siliconflow(payload)
                content = completion["choices"][0]["message"]["content"]
                parsed = parse_json_from_text(content)
                if not parsed:
                    raise RuntimeError("模型返回内容不是有效 JSON")
                return {
                    "category": clean(parsed.get("category")),
                    "englishReply": clean(parsed.get("englishReply") or parsed.get("english_reply")),
                    "chineseExplanation": clean(parsed.get("chineseExplanation") or parsed.get("chinese_explanation")),
                    "requiredInfo": clean(parsed.get("requiredInfo") or parsed.get("required_info")),
                    "riskNotes": clean(parsed.get("riskNotes") or parsed.get("risk_notes")),
                }
            except Exception as exc:
                last_error = exc

        raise RuntimeError(str(last_error) if last_error else "模型调用失败")

    def _post_siliconflow(self, payload: dict[str, Any]) -> dict[str, Any]:
        """使用标准库发送 HTTPS 请求，避免额外 requests 依赖。"""

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.ai_config.base_url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.ai_config.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.ai_config.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"SiliconFlow API 返回错误 {exc.code}: {safe_detail(detail)}") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise RuntimeError(f"模型响应超时，已等待 {self.ai_config.timeout_seconds} 秒") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"无法连接 SiliconFlow API: {exc.reason}") from exc

    def _build_prompt(
        self,
        buyer_question: str,
        extra_context: str,
        knowledge: dict[str, Any],
        matched_scenarios: list[dict[str, Any]],
    ) -> str:
        """构造模型提示词，所有规则都来自数据库。"""

        scenario_text = "\n\n".join(format_scenario(scenario) for scenario in matched_scenarios)
        prohibited_terms = knowledge["prohibitedTerms"][:80]
        sensitive_text = "\n".join(
            f"- {item['phrase']}: {item['safeHint']}" for item in knowledge["sensitivePhrases"]
        )
        style_text = "\n".join(f"- {item}" for item in knowledge["styleRules"][:12])

        return "\n\n".join(
            [
                f"Buyer question:\n{buyer_question}",
                f"Extra context:\n{extra_context or 'None'}",
                f"Prohibited terms:\n{', '.join(prohibited_terms)}",
                f"Sensitive phrases:\n{sensitive_text}",
                f"Style rules:\n{style_text}",
                f"Matched scenarios:\n{scenario_text}",
                "Generate one concise English reply under 85 words and a short Chinese explanation.",
            ]
        )

    def _local_fallback(self, matched_scenarios: list[dict[str, Any]]) -> dict[str, str]:
        """模型不可用时的模板兜底。"""

        if not matched_scenarios:
            return {
                "category": "通用处理",
                "englishReply": (
                    "Hi there, sorry for the inconvenience. Could you please send clear photos and more order details? "
                    "We will check this carefully and handle it properly for you. Thank you for your patience."
                ),
                "chineseExplanation": "未匹配到具体场景，先请买家提供照片和订单细节。",
                "requiredInfo": "需要照片、订单信息、具体问题描述。",
                "riskNotes": "当前为本地通用回复。",
            }

        scenario = matched_scenarios[0]
        return {
            "category": scenario["title"],
            "englishReply": scenario["sellerReplyEn"],
            "chineseExplanation": scenario["sellerReplyZh"],
            "requiredInfo": "请根据实际订单补充金额、订单号或照片等必要信息。",
            "riskNotes": "当前为本地模板回复。",
        }

    def _connect(self):
        """创建 SQL Server 连接。as_dict=True 让查询结果可用字段名读取。"""

        return pytds.connect(
            server=self.db_config.server,
            port=self.db_config.port,
            database=self.db_config.database,
            user=self.db_config.user,
            password=self.db_config.password,
            login_timeout=self.db_config.login_timeout,
            timeout=self.db_config.request_timeout,
            as_dict=True,
            autocommit=True,
            appname="AmazonReplyPythonBackend",
        )


def format_scenario(scenario: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"Title: {scenario['title']}",
            f"Buyer examples: {' | '.join(scenario['buyerExamples'])}",
            f"Seller reply English: {scenario['sellerReplyEn']}",
            f"Chinese note: {scenario['sellerReplyZh']}",
            f"Internal notes: {scenario['internalNotes']}",
        ]
    )


def parse_json_array(value: Any) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(str(value))
        if isinstance(parsed, list):
            return [clean(item) for item in parsed if clean(item)]
    except json.JSONDecodeError:
        return []
    return []


def parse_json_from_text(text: str) -> dict[str, Any] | None:
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            return json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return None


def normalize_model(model: str) -> str:
    value = clean(model)
    return MODEL_ALIASES.get(value.lower(), value)


def tokenize(value: str) -> list[str]:
    return re.findall(r"[\w\u4e00-\u9fff]+", clean(value).lower())


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def safe_detail(value: str) -> str:
    return str(value or "")[:800]


# FastAPI 接入示例：
# from fastapi import APIRouter
# router = APIRouter()
# service = AmazonReplyService.from_env()
#
# @router.post("/amazon-reply/generate")
# def generate_reply(payload: dict):
#     return service.generate_reply(
#         buyer_question=payload.get("buyerQuestion", ""),
#         extra_context=payload.get("extraContext", ""),
#     )
