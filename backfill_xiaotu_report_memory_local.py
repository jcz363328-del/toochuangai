from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from bjc import dui_db, sf_db
from secret_settings import TUCHUANGAI_STORAGE_ROOT
from xiaotu_report_memory import atomic_write_report_memory, build_report_memory_path


_IMPORTANT_KEYWORDS = (
    "完成",
    "达成",
    "上线",
    "交付",
    "确认",
    "推进",
    "进展",
    "优化",
    "解决",
    "修复",
    "增长",
    "下降",
    "提升",
    "结果",
    "数据",
    "复盘",
    "验证",
    "决定",
    "判断",
    "风险",
    "异常",
    "问题",
    "阻塞",
    "延期",
    "卡点",
)
_INSIGHT_KEYWORDS = (
    "心得",
    "思考",
    "反思",
    "复盘",
    "发现",
    "意识到",
    "认识到",
    "经验",
    "方法",
    "规律",
    "原因",
    "判断",
    "建议",
)
_FOLLOWUP_KEYWORDS = (
    "明日",
    "明天",
    "下一步",
    "后续",
    "待",
    "需要",
    "计划",
    "跟进",
    "继续",
    "未完成",
    "尚未",
    "等待",
    "需确认",
)
_NOISE_PATTERNS = (
    re.compile(r"^(日报|工作日报|今日工作|当日工作|工作内容|总结|计划|明日计划|日期|姓名)[:：]?$"),
    re.compile(r"^(问题与结果|问题及结果|工作与成绩|工作成果|心得与复盘|心得体会|后续计划|下一步计划)[:：]?$"),
    re.compile(r"^[\u4e00-\u9fff]{1,8}(问题|结果|计划|心得|总结|复盘|进展)[:：]?$"),
    re.compile(r"^[\u4e00-\u9fff/／、]{2,16}(情况|内容|事项|模块|部分)[:：]?$"),
    re.compile(r"^[\d\s./:：年月日星期一二三四五六七]+$"),
    re.compile(r"^(无|暂无|没有|同上|测试|test|none|null|n/a)$", re.IGNORECASE),
)


class _TextExtractor(HTMLParser):
    _BLOCK_TAGS = {
        "p",
        "div",
        "section",
        "article",
        "li",
        "ul",
        "ol",
        "br",
        "tr",
        "table",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _sql_escape(value: Any) -> str:
    return str(value or "").replace("%", "%%").replace("'", "''")


def _row_values(row: Any, size: int) -> list[Any]:
    values = list(row) if isinstance(row, (list, tuple)) else []
    return values + [""] * max(0, size - len(values))


def _clean_text(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if "<" in raw and ">" in raw:
        parser = _TextExtractor()
        try:
            parser.feed(raw)
            raw = "".join(parser.parts)
        except Exception:
            raw = re.sub(r"<[^>]+>", "\n", raw)
    raw = html.unescape(raw)
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    raw = re.sub(r"[\u200b-\u200f\u202a-\u202e\ufeff]", "", raw)
    raw = re.sub(r"[ \t]+", " ", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return raw.strip()


def _normalize_sentence(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"^[\s#>*•●○▪▫\-—–_]+", "", text)
    text = re.sub(r"^\d{1,3}[.)、．]\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip(" \t-—；;")
    return text[:500]


def _split_sentences(value: Any) -> list[str]:
    text = _clean_text(value)
    if not text:
        return []
    chunks = re.split(r"\n+|(?<=[。！？；;])", text)
    output: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        sentence = _normalize_sentence(chunk)
        if len(sentence) < 4 or len(sentence) > 500:
            continue
        if any(pattern.fullmatch(sentence) for pattern in _NOISE_PATTERNS):
            continue
        key = re.sub(r"[\s，。；;、:：.!！?？]", "", sentence).casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(sentence)
    return output


def _keyword_score(sentence: str, keywords: tuple[str, ...]) -> int:
    keyword_hits = sum(1 for keyword in keywords if keyword in sentence)
    if keyword_hits <= 0:
        return 0
    score = keyword_hits * 3
    if re.search(r"\d+(?:\.\d+)?%|\d+(?:\.\d+)?(?:万|千|个|件|单|人|次|款|组)", sentence):
        score += 2
    if 12 <= len(sentence) <= 160:
        score += 1
    return score


def _pick_sentences(
    sentences: list[str],
    *,
    keywords: tuple[str, ...],
    limit: int,
    fallback: bool = False,
) -> list[str]:
    ranked: list[tuple[int, int, str]] = []
    for index, sentence in enumerate(sentences):
        score = _keyword_score(sentence, keywords)
        if score > 0 or fallback:
            ranked.append((score, -index, sentence))
    ranked.sort(reverse=True)
    selected = [item[2] for item in ranked[: max(0, limit)]]
    selected.sort(key=lambda text: sentences.index(text))
    return selected


def _stable_id(prefix: str, *parts: Any) -> str:
    source = "|".join(str(part or "").strip() for part in parts)
    return f"{prefix}_{hashlib.sha1(source.encode('utf-8')).hexdigest()[:12]}"


def list_report_users() -> list[dict[str, Any]]:
    rows = sf_db(
        """
        SELECT
            LTRIM(RTRIM(XingMing)) AS user_name,
            COUNT(*) AS report_count,
            MIN(RiQi) AS first_date,
            MAX(RiQi) AS last_date
        FROM baogao
        WHERE NULLIF(LTRIM(RTRIM(XingMing)), N'') IS NOT NULL
          AND (LeiXing = N'日报' OR LeiXing IS NULL OR LTRIM(RTRIM(LeiXing)) = N'')
        GROUP BY LTRIM(RTRIM(XingMing))
        ORDER BY COUNT(*) DESC, LTRIM(RTRIM(XingMing))
        """
    ) or []
    users: list[dict[str, Any]] = []
    for row in rows:
        values = _row_values(row, 4)
        users.append(
            {
                "user_name": str(values[0] or "").strip(),
                "report_count": int(values[1] or 0),
                "first_date": str(values[2] or "").strip(),
                "last_date": str(values[3] or "").strip(),
            }
        )
    return users


def load_user_reports(user_name: str) -> list[dict[str, str]]:
    name_esc = _sql_escape(user_name)
    rows = sf_db(
        f"""
        SELECT WenDangID, RiQi, BiaoTi, ZhengWen, TuPianNeiRong
        FROM baogao
        WHERE LTRIM(RTRIM(XingMing)) = N'{name_esc}'
          AND (LeiXing = N'日报' OR LeiXing IS NULL OR LTRIM(RTRIM(LeiXing)) = N'')
        ORDER BY RiQi ASC, WenDangID ASC
        """
    ) or []
    reports: list[dict[str, str]] = []
    for row in rows:
        values = _row_values(row, 5)
        reports.append(
            {
                "report_id": str(values[0] or "").strip(),
                "report_date": str(values[1] or "").strip()[:10],
                "title": _clean_text(values[2]),
                "body": _clean_text(values[3]),
                "image_ocr": _clean_text(values[4]),
            }
        )
    return reports


def _report_extract(report: dict[str, str]) -> dict[str, Any]:
    sentences = _split_sentences(
        "\n".join(
            value
            for value in (
                report.get("body", ""),
                report.get("image_ocr", ""),
            )
            if value
        )
    )
    important = _pick_sentences(
        sentences,
        keywords=_IMPORTANT_KEYWORDS,
        limit=4,
        fallback=True,
    )
    insights = _pick_sentences(sentences, keywords=_INSIGHT_KEYWORDS, limit=2)
    followups = _pick_sentences(sentences, keywords=_FOLLOWUP_KEYWORDS, limit=3)
    changes = _pick_sentences(
        sentences,
        keywords=("完成", "推进", "进展", "变化", "提升", "下降", "解决", "阻塞", "延期", "异常"),
        limit=2,
    )
    return {
        "date": report.get("report_date", ""),
        "report_id": report.get("report_id", ""),
        "title": report.get("title", ""),
        "important_events": important,
        "changes": changes,
        "insights": insights,
        "follow_ups": followups,
    }


def _dedupe_recent_items(items: list[dict[str, str]], limit: int) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in reversed(items):
        text = str(
            item.get("text")
            or item.get("item")
            or item.get("title")
            or item.get("latest_progress")
            or ""
        ).strip()
        key = re.sub(r"[\s，。；;、:：.!！?？]", "", text).casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(item)
        if len(output) >= limit:
            break
    output.reverse()
    return output


def build_local_snapshot(user_name: str, reports: list[dict[str, str]]) -> dict[str, Any]:
    extracted = [_report_extract(report) for report in reports]
    recent_timeline = extracted[-60:]

    insight_items: list[dict[str, str]] = []
    followup_items: list[dict[str, str]] = []
    focus_items: list[dict[str, Any]] = []
    for entry in extracted:
        date_text = str(entry.get("date") or "")
        report_id = str(entry.get("report_id") or "")
        for insight in entry.get("insights") or []:
            insight_items.append(
                {
                    "date": date_text,
                    "text": insight,
                    "source_report_id": report_id,
                }
            )
        for followup in entry.get("follow_ups") or []:
            followup_items.append(
                {
                    "id": _stable_id("followup", user_name, report_id, followup),
                    "item": followup,
                    "since": date_text,
                    "status": "open",
                    "source_report_id": report_id,
                }
            )

    for entry in extracted[-30:]:
        date_text = str(entry.get("date") or "")
        report_id = str(entry.get("report_id") or "")
        for event in (entry.get("important_events") or [])[:2]:
            focus_items.append(
                {
                    "thread_id": _stable_id("thread", user_name, event),
                    "title": event[:120],
                    "status": "需结合后续日报确认",
                    "first_seen": date_text,
                    "last_seen": date_text,
                    "latest_progress": event,
                    "next_action": "",
                    "evidence_report_ids": [report_id] if report_id else [],
                }
            )

    month_entries: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in extracted[:-60]:
        month = str(entry.get("date") or "")[:7] or "日期未知"
        month_entries[month].append(entry)
    archives: list[dict[str, Any]] = []
    for month in sorted(month_entries):
        entries = month_entries[month]
        highlights: list[str] = []
        for entry in entries:
            highlights.extend(entry.get("important_events") or [])
        deduped: list[str] = []
        seen_highlights: set[str] = set()
        for text in highlights:
            key = re.sub(r"[\s，。；;、:：.!！?？]", "", str(text)).casefold()
            if not key or key in seen_highlights:
                continue
            seen_highlights.add(key)
            deduped.append(str(text))
            if len(deduped) >= 12:
                break
        archives.append(
            {
                "period": month,
                "report_count": len(entries),
                "highlights": deduped,
            }
        )

    first_date = reports[0].get("report_date", "") if reports else ""
    last_date = reports[-1].get("report_date", "") if reports else ""
    return {
        "schema_version": 1,
        "user_name": user_name,
        "user_open_id": "",
        "snapshot_version": 1,
        "last_report_id": reports[-1].get("report_id", "") if reports else "",
        "updated_through": last_date,
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "overview": f"历史日报共{len(reports)}份，时间范围为{first_date or '未知'}至{last_date or '未知'}。本文件由本地抽取规则初始化，内容均来自原始日报。",
        "current_focus": _dedupe_recent_items(focus_items, 20),
        "key_insights": _dedupe_recent_items(insight_items, 80),
        "open_followups": _dedupe_recent_items(followup_items, 80),
        "recent_timeline": recent_timeline,
        "archives": archives[-36:],
        "history_report_count": len(reports),
        "history_first_date": first_date,
        "history_last_date": last_date,
        "history_backfilled_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "history_backfill_method": "local_extractive_v1",
    }


def upsert_memory_path(user_name: str, file_path: str) -> None:
    name_esc = _sql_escape(user_name)
    path_esc = _sql_escape(file_path)
    dui_db(
        f"""
        IF OBJECT_ID(N'dbo.baogao_zhenghe', N'U') IS NULL
            THROW 50001, N'缺少数据表 dbo.baogao_zhenghe', 1;

        IF EXISTS (
            SELECT 1
            FROM dbo.baogao_zhenghe WITH (UPDLOCK, HOLDLOCK)
            WHERE yonghu = N'{name_esc}'
        )
            UPDATE dbo.baogao_zhenghe
            SET zhenghe = N'{path_esc}'
            WHERE yonghu = N'{name_esc}';
        ELSE
            INSERT INTO dbo.baogao_zhenghe (yonghu, zhenghe)
            VALUES (N'{name_esc}', N'{path_esc}');
        """
    )


def backfill_user(user_name: str, overwrite: bool) -> dict[str, Any]:
    file_path = build_report_memory_path(TUCHUANGAI_STORAGE_ROOT, user_name)
    path = Path(file_path)
    if path.is_file() and not overwrite:
        upsert_memory_path(user_name, file_path)
        return {
            "user_name": user_name,
            "status": "skipped_existing",
            "file_path": file_path,
        }
    reports = load_user_reports(user_name)
    if not reports:
        return {"user_name": user_name, "status": "skipped_no_reports"}
    snapshot = build_local_snapshot(user_name, reports)
    atomic_write_report_memory(file_path, snapshot)
    saved = json.loads(path.read_text(encoding="utf-8"))
    if saved.get("user_name") != user_name or int(saved.get("history_report_count") or 0) != len(reports):
        raise RuntimeError("落盘JSON校验失败")
    upsert_memory_path(user_name, file_path)
    return {
        "user_name": user_name,
        "status": "created",
        "report_count": len(reports),
        "file_path": file_path,
        "timeline_count": len(saved.get("recent_timeline") or []),
        "insight_count": len(saved.get("key_insights") or []),
        "followup_count": len(saved.get("open_followups") or []),
    }


def verify_backfill(users: list[dict[str, Any]]) -> dict[str, Any]:
    db_rows = sf_db(
        """
        SELECT yonghu, zhenghe
        FROM dbo.baogao_zhenghe
        WHERE NULLIF(LTRIM(RTRIM(yonghu)), N'') IS NOT NULL
        """
    ) or []
    db_paths: dict[str, list[str]] = defaultdict(list)
    for row in db_rows:
        values = _row_values(row, 2)
        db_paths[str(values[0] or "").strip()].append(str(values[1] or "").strip())

    missing_files: list[str] = []
    invalid_files: list[dict[str, str]] = []
    path_mismatches: list[dict[str, Any]] = []
    report_count_mismatches: list[dict[str, Any]] = []
    valid_files = 0
    for item in users:
        user_name = str(item.get("user_name") or "").strip()
        expected_path = build_report_memory_path(TUCHUANGAI_STORAGE_ROOT, user_name)
        path = Path(expected_path)
        if not path.is_file():
            missing_files.append(user_name)
            continue
        try:
            saved = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            invalid_files.append({"user_name": user_name, "error": str(exc)})
            continue
        if not isinstance(saved, dict) or str(saved.get("user_name") or "").strip() != user_name:
            invalid_files.append({"user_name": user_name, "error": "JSON用户名不匹配"})
            continue
        valid_files += 1
        expected_count = int(item.get("report_count") or 0)
        saved_count = int(saved.get("history_report_count") or 0)
        if expected_count != saved_count:
            report_count_mismatches.append(
                {
                    "user_name": user_name,
                    "expected": expected_count,
                    "actual": saved_count,
                }
            )
        stored_paths = db_paths.get(user_name) or []
        matching_paths = [
            stored_path
            for stored_path in stored_paths
            if str(Path(stored_path).resolve(strict=False)).casefold()
            == str(path.resolve(strict=False)).casefold()
        ]
        if not matching_paths:
            path_mismatches.append(
                {
                    "user_name": user_name,
                    "expected": expected_path,
                    "stored": stored_paths,
                }
            )

    duplicate_db_users = sorted(
        user_name for user_name, paths in db_paths.items() if len(paths) > 1
    )
    return {
        "expected_users": len(users),
        "valid_files": valid_files,
        "missing_files": missing_files,
        "invalid_files": invalid_files,
        "report_count_mismatches": report_count_mismatches,
        "path_mismatches": path_mismatches,
        "duplicate_db_users": duplicate_db_users,
        "success": not any(
            (
                missing_files,
                invalid_files,
                report_count_mismatches,
                path_mismatches,
                duplicate_db_users,
            )
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="本地抽取历史日报并创建每用户长期记忆JSON")
    parser.add_argument("--inventory-only", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--user", action="append", default=[])
    parser.add_argument("--limit-users", type=int, default=0)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--pause-seconds", type=float, default=0.1)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    users = list_report_users()
    requested = {str(value or "").strip() for value in args.user if str(value or "").strip()}
    if requested:
        users = [item for item in users if item["user_name"] in requested]
    if args.limit_users > 0:
        users = users[: args.limit_users]
    if args.inventory_only:
        print(
            json.dumps(
                {
                    "user_count": len(users),
                    "report_count": sum(int(item.get("report_count") or 0) for item in users),
                    "users": users,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.verify_only:
        result = verify_backfill(users)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["success"] else 1

    print(
        json.dumps(
            {
                "stage": "start",
                "method": "local_extractive_v1",
                "user_count": len(users),
                "report_count": sum(int(item.get("report_count") or 0) for item in users),
                "storage_root": str(TUCHUANGAI_STORAGE_ROOT),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    results: list[dict[str, Any]] = []
    for index, item in enumerate(users, start=1):
        user_name = str(item.get("user_name") or "").strip()
        try:
            result = backfill_user(user_name, overwrite=bool(args.overwrite))
        except Exception as exc:
            result = {"user_name": user_name, "status": "failed", "error": str(exc)}
        result["index"] = index
        result["total_users"] = len(users)
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if index < len(users) and args.pause_seconds > 0:
            time.sleep(args.pause_seconds)

    summary = {
        "stage": "complete",
        "method": "local_extractive_v1",
        "created": sum(1 for item in results if item.get("status") == "created"),
        "skipped": sum(1 for item in results if str(item.get("status") or "").startswith("skipped")),
        "failed": sum(1 for item in results if item.get("status") == "failed"),
        "results": results,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
