#!/usr/bin/env python3
"""Create one safe SP adjustment plan and optionally execute it through Sellfox MCP."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Sequence

import requests

from sellfox_ads_monitor import load_api_credentials


ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE = ROOT / "ads-monitor-web/public/data/ads-monitor.json"
DEFAULT_REALTIME_SOURCE = ROOT / "ads-monitor-web/public/data/ads-realtime.json"
DEFAULT_PLAN = ROOT / "outputs/sp_mcp_demo/decision-plan.json"
DEFAULT_MCP_URL = "https://api-mcp.sellfox.com/mcp"
SUPPORTED_ACTIONS = ("DECREASE_BID", "INCREASE_BID")
ACTION_PCTS = {
    "DECREASE_BID": Decimal("-0.05"),
    "INCREASE_BID": Decimal("0.03"),
}
MONEY = Decimal("0.01")
MAX_CHANGE = Decimal("0.10")
PLAN_TTL = timedelta(minutes=30)
SNAPSHOT_TTL = timedelta(hours=36)
ACTION_COOLDOWN = timedelta(hours=48)
WRITE_GATE = "I_UNDERSTAND_THIS_WRITES_SP_ADS"


class DemoError(RuntimeError):
    """A safe, user-facing demo error."""


def decimal_value(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise DemoError(f"{field} 不是有效数字。") from exc
    if not result.is_finite():
        raise DemoError(f"{field} 不是有限数字。")
    return result


def parse_time(value: Any, field: str) -> datetime:
    text = str(value or "").strip().replace("Z", "+00:00")
    try:
        result = datetime.fromisoformat(text)
    except ValueError as exc:
        raise DemoError(f"{field} 时间格式无效。") from exc
    if result.tzinfo is None:
        raise DemoError(f"{field} 必须包含时区。")
    return result.astimezone(timezone.utc)


def money_text(value: Decimal) -> str:
    return format(value.quantize(MONEY, rounding=ROUND_HALF_UP), "f")


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DemoError(f"无法读取 JSON：{path}") from exc
    if not isinstance(payload, dict):
        raise DemoError(f"JSON 顶层必须是对象：{path}")
    return payload


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise DemoError(f"无法计算文件摘要：{path}") from exc
    return digest.hexdigest()


def realtime_evidence(
    path: Path,
    item: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    blocked = {
        "path": str(path.resolve()),
        "sha256": "",
        "gate": "BLOCK",
        "freshness": "missing",
        "reason": "实时层缺失或未覆盖当前活动。",
    }
    if not path.is_file():
        return blocked
    try:
        payload = load_json(path)
        digest = file_sha256(path)
        meta = payload.get("meta")
        snapshots = payload.get("campaign_snapshots")
        if not isinstance(meta, dict) or not isinstance(snapshots, list):
            return {**blocked, "sha256": digest, "reason": "实时层结构无效。"}
        if meta.get("mode") != "live" or meta.get("layer") != "realtime":
            return {**blocked, "sha256": digest, "reason": "实时层不是 live 数据。"}
        expires_at = parse_time(meta.get("expires_at"), "realtime.expires_at")
        snapshot = next(
            (
                row
                for row in snapshots
                if isinstance(row, dict)
                and str(row.get("shop_id") or "") == item["shop_id"]
                and str(row.get("campaign_id") or "") == item["campaign_id"]
            ),
            None,
        )
        if not snapshot:
            return {**blocked, "sha256": digest}
        freshness = str((snapshot.get("freshness") or {}).get("status") or "missing")
        gate = str(snapshot.get("execution_gate") or "BLOCK")
        reason = {
            "NO_OBJECTION": "实时层没有发现阻断条件，但这不等于批准执行。",
            "REVIEW": "实时层存在需结合生命周期和成熟指标人工复核的信号。",
            "BLOCK": "实时层存在阻断条件，不能进入执行确认。",
        }.get(gate, "实时层门禁状态未知。")
        if expires_at < now:
            gate, reason = "BLOCK", "实时层快照已经过期。"
        elif freshness != "fresh":
            gate, reason = "BLOCK", "当前活动的实时数据不新鲜。"
        return {
            "path": str(path.resolve()),
            "sha256": digest,
            "run_id": meta.get("run_id"),
            "generated_at": meta.get("generated_at"),
            "expires_at": meta.get("expires_at"),
            "mature_sha256": (meta.get("mature_ref") or {}).get("sha256"),
            "gate": gate,
            "freshness": freshness,
            "reason": reason,
        }
    except DemoError as exc:
        return {**blocked, "reason": str(exc)}


def safe_proposal(current: Decimal, action: str) -> Decimal:
    proposed = (current * (Decimal("1") + ACTION_PCTS[action])).quantize(
        MONEY, rounding=ROUND_HALF_UP
    )
    proposed = min(Decimal("10.00"), max(Decimal("0.02"), proposed))
    if proposed == current:
        raise DemoError("按安全步长取整后数值没有变化。")
    if abs((proposed - current) / current) > MAX_CHANGE:
        raise DemoError("取整后的变化幅度超过10%。")
    return proposed


def candidate_from(item: dict[str, Any]) -> dict[str, Any] | None:
    action = str(item.get("action_code") or "")
    entity_type = str(item.get("entity_type") or "")
    target_id = str(item.get("target_id") or "")
    currency = str(item.get("currency") or "")
    if action not in SUPPORTED_ACTIONS or item.get("data_status") != "complete":
        return None
    if currency != "USD":
        return None
    if target_id.startswith("text:"):
        return None
    if entity_type not in {"keyword", "target"}:
        return None

    current = decimal_value(item.get("current_value"), "current_value")
    spend = decimal_value(item.get("spend") or 0, "spend")
    orders = decimal_value(item.get("orders") or 0, "orders")
    clicks = decimal_value(item.get("clicks") or 0, "clicks")
    target_acos = decimal_value(item.get("target_acos"), "target_acos")
    raw_acos = item.get("acos")
    acos = decimal_value(raw_acos, "acos") if raw_acos not in {None, ""} else None
    rule_id = str(item.get("rule_id") or "")

    valid = False
    if action == "DECREASE_BID" and rule_id == "high_acos":
        valid = orders >= 3 and spend >= 5 and acos is not None and acos > target_acos * Decimal("1.2")
    elif action == "DECREASE_BID" and rule_id == "zero_order_spend":
        valid = orders == 0 and clicks >= 10 and spend >= 20
    elif action == "INCREASE_BID" and rule_id == "low_acos_scale":
        valid = orders >= 5 and spend >= 5 and acos is not None and acos < target_acos * Decimal("0.8")
    if not valid or current <= 0:
        return None

    proposed = safe_proposal(current, action)
    shop_id = str(item.get("shop_id") or "")
    campaign_id = str(item.get("campaign_id") or "")
    if not shop_id or not campaign_id:
        return None
    if not target_id:
        return None

    targeting_type = "keyword" if entity_type == "keyword" else "product"
    tool = "edit_sp_targeting"
    arguments = {
        "shop_id": shop_id,
        "items": [{
            "targetId": target_id,
            "targetingType": targeting_type,
            "bid": float(proposed),
        }],
    }
    object_id = target_id

    actual_pct = (proposed - current) / current
    return {
        "shop_id": shop_id,
        "shop_name": str(item.get("shop_name") or shop_id),
        "currency": currency,
        "entity_type": entity_type,
        "object_id": object_id,
        "campaign_id": campaign_id,
        "target_id": target_id,
        "targeting_type": targeting_type,
        "target_text": str(item.get("target_text") or ""),
        "action": action,
        "current_value": money_text(current),
        "proposed_value": money_text(proposed),
        "change_pct": format(actual_pct.quantize(Decimal("0.0001")), "f"),
        "metrics": {
            "spend": str(spend),
            "orders": str(orders),
            "clicks": str(clicks),
            "acos": str(acos) if acos is not None else None,
            "target_acos": str(target_acos),
        },
        "rule_id": rule_id,
        "reason": str(item.get("reason") or ""),
        "mcp_call": {"tool": tool, "arguments": arguments},
    }


def candidate_score(item: dict[str, Any]) -> tuple[int, Decimal, str]:
    priority = {"DECREASE_BID": 0, "INCREASE_BID": 1}
    spend = decimal_value(item["metrics"]["spend"], "spend")
    return priority[item["action"]], -spend, item["object_id"]


def plan_id_for(
    source_run_id: Any,
    source_generated_at: Any,
    source_sha256: Any,
    created_at: Any,
    item: dict[str, Any],
) -> str:
    fingerprint = {
        "source_run_id": source_run_id,
        "source_generated_at": source_generated_at,
        "source_sha256": source_sha256,
        "created_at": created_at,
        "item": item,
    }
    digest = hashlib.sha256(
        json.dumps(fingerprint, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return f"SP-{digest}"


def plan_signature(plan: dict[str, Any], client_secret: str) -> str:
    signable = {key: value for key, value in plan.items() if key != "approval_signature"}
    body = json.dumps(signable, ensure_ascii=False, sort_keys=True).encode("utf-8")
    derived_key = hmac.new(
        client_secret.encode("utf-8"),
        b"sellfox-sp-adjust-demo-plan-v1",
        hashlib.sha256,
    ).digest()
    return hmac.new(derived_key, body, hashlib.sha256).hexdigest()


def build_plan(
    source: Path,
    *,
    realtime_source: Path = DEFAULT_REALTIME_SOURCE,
    shop_id: str = "",
    action: str = "DECREASE_BID",
    now: datetime | None = None,
) -> dict[str, Any]:
    payload = load_json(source)
    source_digest = file_sha256(source)
    meta = payload.get("meta")
    recommendations = payload.get("recommendations")
    if not isinstance(meta, dict) or not isinstance(recommendations, list):
        raise DemoError("输入缺少 meta 或 recommendations。")
    if meta.get("mode") != "live":
        raise DemoError("只允许使用已发布的 live 数据，拒绝合成 demo 数据。")
    source_time = parse_time(meta.get("generated_at"), "meta.generated_at")
    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if current_time - source_time > SNAPSHOT_TTL or source_time > current_time + timedelta(minutes=5):
        raise DemoError("数据快照已过期或来自未来，不能生成可执行计划。")

    candidates = []
    for raw in recommendations:
        if not isinstance(raw, dict):
            continue
        if shop_id and str(raw.get("shop_id") or "") != shop_id:
            continue
        if str(raw.get("action_code") or "") != action:
            continue
        try:
            candidate = candidate_from(raw)
        except DemoError:
            continue
        if candidate:
            candidates.append(candidate)
    if not candidates:
        raise DemoError("没有找到通过全部安全门禁的候选建议。")
    candidates.sort(key=candidate_score)
    selected = candidates[0]
    realtime = realtime_evidence(realtime_source, selected, current_time)
    created_at = current_time.isoformat(timespec="seconds")
    plan_id = plan_id_for(
        meta.get("run_id"),
        meta.get("generated_at"),
        source_digest,
        created_at,
        selected,
    )
    return {
        "version": 1,
        "plan_id": plan_id,
        "mode": "DRY_RUN",
        "created_at": created_at,
        "expires_at": (current_time + PLAN_TTL).isoformat(timespec="seconds"),
        "source": {
            "path": str(source.resolve()),
            "run_id": meta.get("run_id"),
            "generated_at": meta.get("generated_at"),
            "sha256": source_digest,
            "coverage": meta.get("coverage"),
        },
        "realtime": realtime,
        "items": [selected],
        "mcp_preflight": "NOT_CHECKED",
        "execution": {
            "sent": False,
            "approval_required": True,
            "one_entity_only": True,
            "write_tools": [selected["mcp_call"]["tool"]],
        },
    }


def verify_source_evidence(plan: dict[str, Any]) -> None:
    source = plan.get("source")
    items = plan.get("items")
    if not isinstance(source, dict) or not isinstance(items, list) or len(items) != 1:
        raise DemoError("计划缺少源证据。")
    source_path = Path(str(source.get("path") or "")).resolve()
    if source_path != DEFAULT_SOURCE.resolve():
        raise DemoError("真实执行只接受系统发布的默认 live 数据文件。")
    if not hmac.compare_digest(file_sha256(source_path), str(source.get("sha256") or "")):
        raise DemoError("源数据文件已变化，请重新生成计划。")
    payload = load_json(source_path)
    meta = payload.get("meta")
    rows = payload.get("recommendations")
    if not isinstance(meta, dict) or not isinstance(rows, list):
        raise DemoError("源数据结构异常。")
    if meta.get("mode") != "live":
        raise DemoError("源数据不是 live 模式。")
    if meta.get("run_id") != source.get("run_id") or meta.get("generated_at") != source.get("generated_at"):
        raise DemoError("源数据批次与计划不一致。")
    wanted = items[0]
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        try:
            rebuilt = candidate_from(raw)
        except DemoError:
            continue
        if rebuilt == wanted:
            return
    raise DemoError("源数据中已找不到完全一致且仍满足规则的建议。")


def verify_realtime_evidence(
    plan: dict[str, Any],
    item: dict[str, Any],
    now: datetime,
) -> None:
    evidence = realtime_evidence(DEFAULT_REALTIME_SOURCE, item, now)
    if Path(str(evidence.get("path") or "")).resolve() != DEFAULT_REALTIME_SOURCE.resolve():
        raise DemoError("真实执行只接受系统发布的默认实时层文件。")
    source = plan.get("source") or {}
    if evidence.get("mature_sha256") != source.get("sha256"):
        raise DemoError("实时层与成熟建议不是同一数据基线，请重新采集。")
    if evidence.get("gate") != "NO_OBJECTION" or evidence.get("freshness") != "fresh":
        raise DemoError(f"实时层阻断执行：{evidence.get('reason') or '状态不满足'}")


def parse_mcp_response(response: requests.Response, allow_empty: bool) -> dict[str, Any]:
    if not response.content:
        if allow_empty:
            return {}
        raise DemoError("MCP 返回空响应。")
    content_type = response.headers.get("Content-Type", "").lower()
    if "text/event-stream" in content_type:
        messages = []
        data_lines = []
        try:
            response_text = response.content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DemoError("MCP SSE 响应不是 UTF-8。") from exc

        def flush_event() -> None:
            if not data_lines:
                return
            raw = "\n".join(data_lines).strip()
            data_lines.clear()
            if not raw or raw == "[DONE]":
                return
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise DemoError("MCP SSE 数据不是有效 JSON。") from exc
            if isinstance(parsed, dict):
                messages.append(parsed)

        for line in response_text.splitlines():
            if not line.strip():
                flush_event()
            elif line.lstrip().startswith("data:"):
                data_lines.append(line.lstrip()[5:].lstrip())
        flush_event()
        if not messages:
            raise DemoError("MCP SSE 响应中没有 data 事件。")
        return messages[-1]
    try:
        payload = json.loads(response.content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DemoError("MCP 返回内容不是有效 JSON。") from exc
    if not isinstance(payload, dict):
        raise DemoError("MCP JSON-RPC 响应格式异常。")
    return payload


class McpClient:
    """Minimal MCP Streamable HTTP client; credentials never enter plan or logs."""

    def __init__(self, url: str, client_id: str, client_secret: str, *, timeout: float = 120):
        if url.rstrip("/") != DEFAULT_MCP_URL:
            raise DemoError("拒绝把赛狐凭据发送到非官方 MCP 地址。")
        self.url = DEFAULT_MCP_URL
        self.session_id = ""
        self.request_id = 0
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "X-Sellfox-Client-Id": client_id,
            "X-Sellfox-Client-Secret": client_secret,
        })

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> "McpClient":
        self.initialize()
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def _post(self, message: dict[str, Any], *, allow_empty: bool = False) -> dict[str, Any]:
        headers = {"Mcp-Session-Id": self.session_id} if self.session_id else {}
        try:
            response = self.session.post(
                self.url,
                json=message,
                headers=headers,
                timeout=self.timeout,
                allow_redirects=False,
            )
            if response.is_redirect:
                raise DemoError("MCP 返回重定向，已拒绝继续携带凭据。")
            response.raise_for_status()
        except requests.RequestException as exc:
            raise DemoError("MCP 网络请求失败。") from exc
        received_session = response.headers.get("Mcp-Session-Id", "")
        if received_session:
            self.session_id = received_session
        payload = parse_mcp_response(response, allow_empty)
        error = payload.get("error")
        if error:
            message_text = error.get("message") if isinstance(error, dict) else str(error)
            raise DemoError(f"MCP JSON-RPC 错误：{message_text}")
        return payload

    def initialize(self) -> None:
        self.request_id += 1
        payload = self._post({
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "sellfox-sp-adjust-demo", "version": "1.0"},
            },
        })
        result = payload.get("result")
        if not isinstance(result, dict):
            raise DemoError("MCP initialize 缺少 result。")
        protocol = str(result.get("protocolVersion") or "2025-03-26")
        self.session.headers["MCP-Protocol-Version"] = protocol
        self._post(
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            allow_empty=True,
        )

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.request_id += 1
        payload = self._post({
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })
        result = payload.get("result")
        if not isinstance(result, dict):
            raise DemoError(f"MCP 工具 {name} 缺少 result。")
        if result.get("isError"):
            raise DemoError(f"MCP 工具 {name} 返回错误。")
        return result

    def list_tools(self) -> dict[str, dict[str, Any]]:
        self.request_id += 1
        payload = self._post({
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": "tools/list",
            "params": {},
        })
        result = payload.get("result")
        tools = result.get("tools") if isinstance(result, dict) else None
        if not isinstance(tools, list):
            raise DemoError("MCP tools/list 缺少 tools。")
        return {
            str(item["name"]): item.get("inputSchema") or {}
            for item in tools
            if isinstance(item, dict) and item.get("name")
        }


def validate_tool_schema(name: str, schema: dict[str, Any]) -> None:
    properties = schema.get("properties")
    required = set(schema.get("required") or [])
    if not isinstance(properties, dict):
        raise DemoError(f"MCP 工具 {name} 的 inputSchema 异常。")
    if name.startswith("get_sp_"):
        expected = {"shop_id"}
    else:
        expected = {"shop_id", "items"}
        items = properties.get("items")
        if not isinstance(items, dict) or items.get("type") != "array":
            raise DemoError(f"MCP 工具 {name} 的 items schema 已变化。")
    if not expected.issubset(properties) or not expected.issubset(required):
        raise DemoError(f"MCP 工具 {name} 的必填参数已变化。")


def tool_json(result: dict[str, Any]) -> dict[str, Any]:
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    for block in result.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "text":
            try:
                parsed = json.loads(str(block.get("text") or ""))
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    raise DemoError("MCP 工具响应中没有结构化 JSON。")


def api_data(result: dict[str, Any]) -> dict[str, Any]:
    payload = tool_json(result)
    if payload.get("error"):
        raise DemoError(f"赛狐 MCP 返回错误：{payload['error']}")
    if "code" in payload and str(payload.get("code")) != "0":
        raise DemoError(f"赛狐 MCP 返回 code={payload.get('code')}。")
    data = payload.get("data", payload)
    if not isinstance(data, dict):
        raise DemoError("赛狐 MCP data 格式异常。")
    return data


def find_current(client: McpClient, item: dict[str, Any]) -> dict[str, Any]:
    if item["entity_type"] == "keyword":
        tool = "get_sp_keyword_list"
        wanted_key, value_key = "keywordId", "bid"
    else:
        tool = "get_sp_product_targeting_list"
        wanted_key, value_key = "targetId", "bid"

    arguments = {
        "shop_id": item["shop_id"],
        "campaign_id": item["campaign_id"],
        "page_size": "1000",
    }
    next_token = ""
    for _ in range(10):
        request_args = {"next_token": next_token} if next_token else arguments
        data = api_data(client.call_tool(tool, request_args))
        rows = data.get("itemList")
        if not isinstance(rows, list):
            raise DemoError(f"{tool} 缺少 itemList。")
        for row in rows:
            if isinstance(row, dict) and str(row.get(wanted_key) or "") == item["object_id"]:
                state = str(row.get("state") or "")
                if state != "enabled":
                    raise DemoError("目标当前不是 enabled，拒绝执行。")
                serving = str(row.get("servingStatus") or "").lower()
                blocked = ("paused", "archived", "disabled", "ended", "ineligible", "suspended")
                if serving and any(token in serving for token in blocked):
                    raise DemoError("目标当前不是正常投放状态，拒绝执行。")
                return {"value": decimal_value(row.get(value_key), value_key), "row": row}
        next_token = str(data.get("nextToken") or "")
        if not next_token:
            break
    raise DemoError("MCP 实时数据中找不到目标对象。")


def verify_current(client: McpClient, item: dict[str, Any], expected_key: str) -> None:
    actual = find_current(client, item)["value"]
    expected = decimal_value(item[expected_key], expected_key)
    if abs(actual - expected) > Decimal("0.005"):
        raise DemoError(
            f"MCP 当前值 {money_text(actual)} 与计划值 {money_text(expected)} 不一致。"
        )


def required_tools_for(item: dict[str, Any]) -> set[str]:
    read_tool = {
        "keyword": "get_sp_keyword_list",
        "target": "get_sp_product_targeting_list",
    }[item["entity_type"]]
    return {read_tool, item["mcp_call"]["tool"]}


def schema_digest(tool_schemas: dict[str, dict[str, Any]], names: set[str]) -> str:
    return hashlib.sha256(
        json.dumps(
            {name: tool_schemas[name] for name in sorted(names)},
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def verify_plan_via_mcp(plan: dict[str, Any], url: str) -> None:
    client_id, client_secret = load_api_credentials()
    item = plan["items"][0]
    with McpClient(url, client_id, client_secret) as client:
        tool_schemas = client.list_tools()
        required_tools = required_tools_for(item)
        if not required_tools.issubset(tool_schemas):
            raise DemoError("MCP 缺少计划所需的读写工具。")
        for name in required_tools:
            validate_tool_schema(name, tool_schemas[name])
        verify_current(client, item, "current_value")
    plan["mcp_preflight"] = "CURRENT_VALUE_VERIFIED"
    plan["mcp_preflight_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    plan["mcp_tools_verified"] = sorted(required_tools)
    plan["mcp_schema_sha256"] = schema_digest(tool_schemas, required_tools)
    plan["approval_signature"] = plan_signature(plan, client_secret)


def validate_execution(plan: dict[str, Any], confirm: str, now: datetime) -> dict[str, Any]:
    if plan.get("version") != 1:
        raise DemoError("不支持该计划版本。")
    if plan.get("mode") != "DRY_RUN" or plan.get("execution", {}).get("sent"):
        raise DemoError("计划状态不允许执行。")
    if plan.get("mcp_preflight") != "CURRENT_VALUE_VERIFIED":
        raise DemoError("计划没有完成 MCP 实时预检。")
    if not plan.get("approval_signature"):
        raise DemoError("计划缺少 MCP 预检签名。")
    if confirm != plan.get("plan_id"):
        raise DemoError("--confirm 必须精确等于 plan_id。")
    if os.environ.get("SELLFOX_SP_WRITE_ENABLED") != WRITE_GATE:
        raise DemoError("真实写入总开关未开启。")
    items = plan.get("items")
    if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
        raise DemoError("Demo 每次只能执行一个对象。")
    source = plan.get("source")
    if not isinstance(source, dict):
        raise DemoError("计划缺少 source。")
    expected_plan_id = plan_id_for(
        source.get("run_id"),
        source.get("generated_at"),
        source.get("sha256"),
        plan.get("created_at"),
        items[0],
    )
    if not hmac.compare_digest(str(plan.get("plan_id") or ""), expected_plan_id):
        raise DemoError("计划内容或 plan_id 已被修改。")
    created_at = parse_time(plan.get("created_at"), "created_at")
    expires_at = parse_time(plan.get("expires_at"), "expires_at")
    expected_expiry = created_at + PLAN_TTL
    if abs((expires_at - expected_expiry).total_seconds()) > 1:
        raise DemoError("计划有效期字段已被修改。")
    if expected_expiry < now:
        raise DemoError("执行计划已过期，请重新生成。")
    source_time = parse_time(source.get("generated_at"), "source.generated_at")
    if source_time > now + timedelta(minutes=5) or now - source_time > SNAPSHOT_TTL:
        raise DemoError("源数据已过期，请重新采集。")
    if items[0].get("currency") != "USD":
        raise DemoError("最小 Demo 的真实执行目前只允许 USD。")
    call = items[0].get("mcp_call")
    if not isinstance(call, dict) or call.get("tool") != "edit_sp_targeting":
        raise DemoError("计划包含未授权的 MCP 写工具。")
    return items[0]


def enforce_cooldown(directory: Path, item: dict[str, Any], now: datetime) -> None:
    for path in directory.glob("execution-SP-*.json"):
        audit = load_json(path)
        if audit.get("shop_id") != item["shop_id"] or audit.get("object_id") != item["object_id"]:
            continue
        attempted_at = parse_time(
            audit.get("write_attempted_at") or audit.get("reserved_at"),
            "write_attempted_at",
        )
        if timedelta(0) <= now - attempted_at < ACTION_COOLDOWN:
            raise DemoError("该对象48小时内已有写入尝试，处于冷却期。")


@contextmanager
def execution_lock(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = directory / ".execution.lock"
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise DemoError("已有 SP 执行进程或待人工检查的遗留锁。") from exc
    try:
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        os.fsync(descriptor)
        yield
    finally:
        os.close(descriptor)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def reserve_audit(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise DemoError("本地已有该 plan_id 的执行记录，拒绝重复执行。") from exc


def execute_plan(plan_path: Path, confirm: str, url: str) -> dict[str, Any]:
    plan = load_json(plan_path)
    now = datetime.now(timezone.utc)
    item = validate_execution(plan, confirm, now)
    client_id, client_secret = load_api_credentials()
    expected_signature = plan_signature(plan, client_secret)
    if not hmac.compare_digest(str(plan.get("approval_signature") or ""), expected_signature):
        raise DemoError("MCP 预检签名无效，计划可能被修改。")

    audit_directory = DEFAULT_PLAN.parent
    audit_path = audit_directory / f"execution-{plan['plan_id']}.json"
    with execution_lock(audit_directory):
        verify_source_evidence(plan)
        verify_realtime_evidence(plan, item, now)
        if audit_path.exists():
            raise DemoError("本地已有该 plan_id 的执行记录，拒绝重复执行。")
        enforce_cooldown(audit_directory, item, now)
        with McpClient(url, client_id, client_secret) as client:
            required_tools = required_tools_for(item)
            tool_schemas = client.list_tools()
            if not required_tools.issubset(tool_schemas):
                raise DemoError("执行前发现 MCP 工具缺失。")
            for name in required_tools:
                validate_tool_schema(name, tool_schemas[name])
            if not hmac.compare_digest(
                schema_digest(tool_schemas, required_tools),
                str(plan.get("mcp_schema_sha256") or ""),
            ):
                raise DemoError("MCP 工具 schema 已变化，请重新生成计划。")
            verify_current(client, item, "current_value")

            call = item["mcp_call"]
            reserved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            audit = {
                "plan_id": plan["plan_id"],
                "reserved_at": reserved_at,
                "tool": call["tool"],
                "shop_id": item["shop_id"],
                "object_id": item["object_id"],
                "before": item["current_value"],
                "after": item["proposed_value"],
                "status": "RESERVED",
                "verified": False,
            }
            reserve_audit(audit_path, audit)
            audit["write_attempted_at"] = datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            )
            audit["status"] = "SUBMITTING"
            atomic_json(audit_path, audit)
            try:
                data = api_data(client.call_tool(call["tool"], call["arguments"]))
                success_ids = {str(value) for value in data.get("successIds") or []}
                fail_list = data.get("failList") or []
                if item["object_id"] not in success_ids or fail_list:
                    raise DemoError("MCP 写入没有返回唯一成功结果。")
                verify_current(client, item, "proposed_value")
            except Exception as exc:
                audit["status"] = "UNKNOWN"
                audit["message"] = str(exc)[:500]
                atomic_json(audit_path, audit)
                if isinstance(exc, DemoError):
                    raise
                raise DemoError("写入结果不确定，已记录审计并禁止重试。") from exc

        audit.update({
            "executed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "status": "VERIFIED",
            "verified": True,
        })
        atomic_json(audit_path, audit)
        return {
            "status": "executed",
            "audit": str(audit_path),
            "plan_id": audit["plan_id"],
            "shop_id": item["shop_id"],
            "object_id": item["object_id"],
            "before": audit["before"],
            "after": audit["after"],
            "verified": audit["verified"],
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="用真实监控数据生成一条 SP MCP 调控计划；默认永远不写广告。"
    )
    parser.add_argument("--input", default=str(DEFAULT_SOURCE))
    parser.add_argument("--output", default=str(DEFAULT_PLAN))
    parser.add_argument("--shop-id", default="")
    parser.add_argument("--action", choices=SUPPORTED_ACTIONS, default="DECREASE_BID")
    parser.add_argument("--verify-mcp", action="store_true", help="只读核对 MCP 当前值")
    parser.add_argument("--execute-plan", help="执行已冻结的计划；默认不启用")
    parser.add_argument("--confirm", default="")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.execute_plan:
            result = execute_plan(
                Path(args.execute_plan).resolve(), args.confirm, DEFAULT_MCP_URL
            )
        else:
            output = Path(args.output).resolve()
            plan = build_plan(
                Path(args.input).resolve(),
                realtime_source=DEFAULT_REALTIME_SOURCE,
                shop_id=args.shop_id,
                action=args.action,
            )
            if args.verify_mcp:
                verify_plan_via_mcp(plan, DEFAULT_MCP_URL)
            atomic_json(output, plan)
            item = plan["items"][0]
            result = {
                "status": "dry-run",
                "plan_id": plan["plan_id"],
                "mcp_preflight": plan["mcp_preflight"],
                "action": item["action"],
                "shop_id": item["shop_id"],
                "object_id": item["object_id"],
                "current_value": item["current_value"],
                "proposed_value": item["proposed_value"],
                "sent": False,
                "realtime_gate": plan["realtime"]["gate"],
                "plan": str(output),
            }
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except DemoError as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False))
        return 2
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(
            json.dumps(
                {"status": "error", "message": f"未预期错误：{type(exc).__name__}"},
                ensure_ascii=False,
            )
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
