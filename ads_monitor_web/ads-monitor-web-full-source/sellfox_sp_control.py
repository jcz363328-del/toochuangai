#!/usr/bin/env python3
"""Local two-step control service for Sellfox Sponsored Products tools."""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import re
import threading
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from sellfox_ads_monitor import load_api_credentials
from sellfox_sp_adjust_demo import DEFAULT_MCP_URL, McpClient, api_data, atomic_json


ROOT = Path(__file__).resolve().parent
SHOP_ID = "475394"
PLAN_DIR = ROOT / "outputs" / "sp_control" / "plans"
AUDIT_DIR = ROOT / "outputs" / "sp_control" / "audit"
PLAN_TTL = timedelta(minutes=10)
PLAN_ID_RE = re.compile(r"^SPC-[0-9a-f]{20}$")

FIELD_ALIASES = {
    "shop_id": ("shop_id", "shopId"),
    "campaign_id": ("campaignId", "campaign_id"),
    "group_id": ("groupId", "adGroupId", "group_id"),
    "ad_id": ("adId", "ad_id"),
    "target_id": ("targetId", "keywordId", "target_id"),
    "state": ("state",),
    "budget": ("budget", "dailyBudget"),
    "strategy": ("strategy", "biddingStrategy"),
    "adjustments": ("adjustments", "placementAdjustments"),
    "default_bid": ("defaultBid", "default_bid"),
    "bid": ("bid",),
    "targeting_type": ("targetingType", "targeting_type"),
    "keyword_text": ("keywordText", "keyword", "keyword_text"),
    "match_type": ("matchType", "match_type"),
    "asin": ("asin", "targetAsin"),
    "sku": ("sku",),
    "name": ("name",),
}


def _op(
    operation_id: str,
    group: str,
    label: str,
    description: str,
    candidates: Sequence[str],
    identity: Sequence[str],
    fields: Sequence[str],
    *,
    verified: bool = False,
) -> dict[str, Any]:
    return {
        "id": operation_id,
        "group": group,
        "label": label,
        "description": description,
        "tool_candidates": list(candidates),
        "identity": list(identity),
        "fields": list(fields),
        "verified": verified,
    }


OPERATIONS = (
    _op("campaign_state", "活动", "启停/归档", "开启、暂停或归档当前 SP 活动。", ("edit_sp_campaign", "update_sp_campaign"), ("campaign_id",), ("state",)),
    _op("campaign_budget", "活动", "日预算", "修改活动每日预算。", ("edit_sp_campaign", "update_sp_campaign"), ("campaign_id",), ("budget",)),
    _op("campaign_strategy", "活动", "竞价策略", "修改动态竞价策略。", ("edit_sp_campaign", "update_sp_campaign"), ("campaign_id",), ("strategy",)),
    _op("placement_adjustment", "活动", "广告位加价", "修改搜索首页、商品页和其余搜索位加价。", ("edit_sp_campaign", "update_sp_campaign"), ("campaign_id",), ("adjustments",)),
    _op("ad_group_state", "广告组", "广告组状态", "开启、暂停或归档广告组。", ("edit_sp_ad_group", "update_sp_ad_group"), ("group_id",), ("state",)),
    _op("ad_group_default_bid", "广告组", "默认竞价", "修改广告组默认竞价。", ("edit_sp_ad_group", "update_sp_ad_group"), ("group_id",), ("default_bid",)),
    _op("ad_group_create", "广告组", "新建广告组", "在当前活动下新建广告组。", ("create_sp_ad_group", "add_sp_ad_group"), ("campaign_id",), ("name", "default_bid")),
    _op("ad_product_state", "广告商品", "商品状态", "开启、暂停或归档广告商品。", ("edit_sp_ad_product", "update_sp_ad_product"), ("ad_id",), ("state",)),
    _op("ad_product_create", "广告商品", "添加广告商品", "把 SKU/ASIN 添加到广告组。", ("create_sp_ad_product", "add_sp_ad_product"), ("campaign_id", "group_id"), ("sku", "asin")),
    _op("keyword_bid", "关键词", "关键词竞价", "修改现有关键词竞价。", ("edit_sp_targeting",), ("target_id",), ("targeting_type", "bid"), verified=True),
    _op("keyword_state", "关键词", "关键词状态", "开启、暂停或归档关键词。", ("edit_sp_targeting", "edit_sp_keyword"), ("target_id",), ("targeting_type", "state")),
    _op("keyword_create", "关键词", "添加关键词", "添加精准、词组或广泛关键词。", ("create_sp_keyword", "add_sp_keyword", "create_sp_targeting"), ("campaign_id", "group_id"), ("keyword_text", "match_type", "bid")),
    _op("product_target_bid", "商品投放", "商品投放竞价", "修改现有 ASIN/类目投放竞价。", ("edit_sp_targeting",), ("target_id",), ("targeting_type", "bid"), verified=True),
    _op("product_target_state", "商品投放", "商品投放状态", "开启、暂停或归档商品投放。", ("edit_sp_targeting", "edit_sp_product_targeting"), ("target_id",), ("targeting_type", "state")),
    _op("product_target_create", "商品投放", "添加商品投放", "添加 ASIN 或类目商品投放。", ("create_sp_product_targeting", "add_sp_product_targeting", "create_sp_targeting"), ("campaign_id", "group_id"), ("asin", "bid")),
    _op("negative_keyword_create", "否定投放", "添加否定关键词", "添加否定精准或否定词组。", ("create_sp_negative_keyword", "add_sp_negative_keyword"), ("campaign_id", "group_id"), ("keyword_text", "match_type")),
    _op("negative_keyword_remove", "否定投放", "取消否定关键词", "移除现有否定关键词。", ("delete_sp_negative_keyword", "remove_sp_negative_keyword"), ("target_id",), ()),
    _op("negative_target_create", "否定投放", "添加否定商品", "添加否定 ASIN 商品投放。", ("create_sp_negative_product_targeting", "add_sp_negative_product_targeting", "create_sp_negative_target"), ("campaign_id", "group_id"), ("asin",)),
    _op("negative_target_remove", "否定投放", "取消否定商品", "移除现有否定商品投放。", ("delete_sp_negative_product_targeting", "remove_sp_negative_product_targeting", "delete_sp_negative_target"), ("target_id",), ()),
    _op("campaign_create", "新建", "新建 SP 活动", "创建新的自动或手动 SP 活动。", ("create_sp_campaign", "add_sp_campaign"), (), ("name", "budget", "strategy")),
)
OPERATIONS_BY_ID = {item["id"]: item for item in OPERATIONS}

CONTEXT_ENTITY_RULES = {
    "ad_group_state": ("ad_groups", "group_id", ("groupId", "group_id")),
    "ad_group_default_bid": ("ad_groups", "group_id", ("groupId", "group_id")),
    "ad_product_state": ("ad_products", "ad_id", ("adId", "ad_id")),
    "keyword_bid": ("keywords", "target_id", ("keywordId", "targetId", "target_id")),
    "keyword_state": ("keywords", "target_id", ("keywordId", "targetId", "target_id")),
    "product_target_bid": ("product_targets", "target_id", ("targetId", "target_id")),
    "product_target_state": ("product_targets", "target_id", ("targetId", "target_id")),
    "negative_keyword_remove": ("negative_keywords", "target_id", ("keywordId", "negativeKeywordId", "targetId")),
    "negative_target_remove": ("negative_product_targets", "target_id", ("targetId", "negativeTargetId")),
}
CONTEXT_ROW_BY_OPERATION = {
    "ad_group_state": ("ad_groups", "group_id", ("groupId", "group_id")),
    "ad_group_default_bid": ("ad_groups", "group_id", ("groupId", "group_id")),
    "ad_product_state": ("ad_products", "ad_id", ("adId", "ad_id")),
    "keyword_bid": ("keywords", "target_id", ("keywordId", "targetId", "target_id")),
    "keyword_state": ("keywords", "target_id", ("keywordId", "targetId", "target_id")),
    "product_target_bid": ("product_targets", "target_id", ("targetId", "target_id")),
    "product_target_state": ("product_targets", "target_id", ("targetId", "target_id")),
    "negative_keyword_remove": ("negative_keywords", "target_id", ("keywordId", "negativeKeywordId", "targetId")),
    "negative_target_remove": ("negative_product_targets", "target_id", ("targetId", "negativeTargetId")),
}
GROUP_SCOPED_OPERATIONS = {
    "ad_product_create",
    "keyword_create",
    "product_target_create",
    "negative_keyword_create",
    "negative_target_create",
}


class SpControlError(RuntimeError):
    status_code = 400
    error_code = "SP_CONTROL_INVALID"

    def __init__(self, message: str, *, status_code: int | None = None, error_code: str | None = None):
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code
        if error_code is not None:
            self.error_code = error_code


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _decimal(value: Any, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise SpControlError(f"{name} 不是有效数字。") from exc
    if not result.is_finite():
        raise SpControlError(f"{name} 不是有限数字。")
    return result


def _schema_digest(schema: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(schema, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _signature(plan: Mapping[str, Any], secret: str) -> str:
    signable = {key: value for key, value in plan.items() if key != "signature"}
    key = hmac.new(secret.encode("utf-8"), b"sellfox-sp-control-v1", hashlib.sha256).digest()
    body = json.dumps(signable, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hmac.new(key, body, hashlib.sha256).hexdigest()


def _tool_for(operation: Mapping[str, Any], schemas: Mapping[str, Any]) -> str:
    for name in operation["tool_candidates"]:
        if name in schemas:
            return name
    return ""


def _property_name(properties: Mapping[str, Any], canonical: str) -> str:
    aliases = FIELD_ALIASES.get(canonical, (canonical,))
    return next((name for name in aliases if name in properties), aliases[0])


def _has_property(properties: Mapping[str, Any], canonical: str) -> bool:
    return any(name in properties for name in FIELD_ALIASES.get(canonical, (canonical,)))


def _item_schema(schema: Mapping[str, Any]) -> Mapping[str, Any]:
    items = schema.get("properties", {}).get("items", {})
    nested = items.get("items", {}) if isinstance(items, Mapping) else {}
    return nested if isinstance(nested, Mapping) else {}


def _build_arguments(
    operation: Mapping[str, Any],
    values: Mapping[str, Any],
    schema: Mapping[str, Any],
    shop_id: str = SHOP_ID,
) -> dict[str, Any]:
    properties = schema.get("properties")
    if not isinstance(properties, Mapping):
        raise SpControlError("赛狐 MCP 工具 schema 缺少 properties。", status_code=503, error_code="MCP_SCHEMA_INVALID")
    item_schema = _item_schema(schema)
    item_properties = item_schema.get("properties", {}) if isinstance(item_schema, Mapping) else {}
    item_properties = item_properties if isinstance(item_properties, Mapping) else {}
    canonical = [*operation["identity"], *operation["fields"]]
    if operation["id"] != "campaign_create":
        canonical.extend(
            name
            for name in ("campaign_id", "group_id")
            if name not in canonical
            and name in values
            and (_has_property(item_properties, name) or _has_property(properties, name))
        )
    item = {
        _property_name(item_properties, name): copy.deepcopy(values[name])
        for name in canonical
        if name in values
    }
    if "items" in properties:
        arguments = {_property_name(properties, "shop_id"): shop_id, "items": [item]}
    else:
        arguments = {_property_name(properties, "shop_id"): shop_id}
        arguments.update({_property_name(properties, name): copy.deepcopy(values[name]) for name in canonical if name in values})
    required = set(schema.get("required") or [])
    missing = sorted(required.difference(arguments))
    if missing:
        raise SpControlError(f"MCP 工具新增必填字段：{','.join(missing)}。", status_code=409, error_code="MCP_SCHEMA_CHANGED")
    item_required = set(item_schema.get("required") or []) if isinstance(item_schema, Mapping) else set()
    missing_item = sorted(item_required.difference(item))
    if missing_item:
        raise SpControlError(f"MCP 调控对象缺少字段：{','.join(missing_item)}。", status_code=409, error_code="MCP_SCHEMA_CHANGED")
    return arguments


def _normalize_values(operation: Mapping[str, Any], payload: Mapping[str, Any]) -> dict[str, Any]:
    values = dict(payload.get("values") or {})
    campaign_id = str(payload.get("campaign_id") or "")
    if not campaign_id.isdigit():
        raise SpControlError("campaign_id 无效。")
    values.setdefault("campaign_id", campaign_id)
    for name in operation["identity"]:
        value = str(values.get(name) or "").strip()
        if name.endswith("_id") and (not value or not value.isdigit()):
            raise SpControlError(f"{name} 无效。")
        values[name] = value
    for name in operation["fields"]:
        if name not in values or values[name] in (None, ""):
            raise SpControlError(f"缺少 {name}。")
    for name in ("bid", "default_bid"):
        if name in values:
            amount = _decimal(values[name], name)
            if not Decimal("0.02") <= amount <= Decimal("10"):
                raise SpControlError(f"{name} 必须在 0.02–10.00 之间。")
            values[name] = float(amount)
    if "budget" in values:
        amount = _decimal(values["budget"], "budget")
        if not Decimal("1") <= amount <= Decimal("1000000"):
            raise SpControlError("budget 必须在 1–1,000,000 之间。")
        values["budget"] = float(amount)
    if "state" in values and values["state"] not in {"enabled", "paused", "archived"}:
        raise SpControlError("state 只允许 enabled、paused 或 archived。")
    if "targeting_type" in values and values["targeting_type"] not in {"keyword", "product"}:
        raise SpControlError("targeting_type 无效。")
    return values


def _context_rows(context: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    structure = context.get("structure")
    if not isinstance(structure, Mapping):
        return []
    rows = structure.get(key)
    return [row for row in rows if isinstance(row, Mapping)] if isinstance(rows, list) else []


def _context_id(row: Mapping[str, Any], aliases: Sequence[str]) -> str:
    return next((str(row[name]) for name in aliases if row.get(name) not in (None, "")), "")


def _validate_context(
    operation: Mapping[str, Any],
    values: Mapping[str, Any],
    context: Mapping[str, Any] | None,
) -> None:
    if not isinstance(context, Mapping):
        raise SpControlError("缺少当前活动结构，未生成调控计划。", status_code=409, error_code="CONTROL_CONTEXT_REQUIRED")
    campaign = context.get("campaign") if isinstance(context.get("campaign"), Mapping) else {}
    context_campaign_id = str(campaign.get("campaignId") or campaign.get("campaign_id") or context.get("campaign_id") or "")
    if context_campaign_id != values["campaign_id"]:
        raise SpControlError("调控活动与当前页面不一致。", status_code=409, error_code="CONTROL_CONTEXT_MISMATCH")
    operation_id = operation["id"]
    if operation_id in GROUP_SCOPED_OPERATIONS:
        group_ids = {_context_id(row, ("groupId", "group_id")) for row in _context_rows(context, "ad_groups")}
        if values.get("group_id") not in group_ids:
            raise SpControlError("所选广告组不属于当前活动。", status_code=409, error_code="CONTROL_ENTITY_MISMATCH")
    rule = CONTEXT_ENTITY_RULES.get(operation_id)
    if rule:
        section, value_key, aliases = rule
        entity_ids = {_context_id(row, aliases) for row in _context_rows(context, section)}
        if values.get(value_key) not in entity_ids:
            raise SpControlError("所选调控对象不属于当前活动。", status_code=409, error_code="CONTROL_ENTITY_MISMATCH")


def _row_value(row: Mapping[str, Any], canonical: str) -> Any:
    for alias in FIELD_ALIASES.get(canonical, (canonical,)):
        if alias in row and row[alias] not in (None, ""):
            return copy.deepcopy(row[alias])
    return None


def _control_change_snapshot(
    operation: Mapping[str, Any],
    values: Mapping[str, Any],
    context: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    operation_id = str(operation["id"])
    if operation_id.startswith("campaign_") or operation_id == "placement_adjustment":
        row = context.get("campaign") if isinstance(context.get("campaign"), Mapping) else {}
    else:
        rule = CONTEXT_ROW_BY_OPERATION.get(operation_id)
        row = {}
        if rule:
            section, value_key, aliases = rule
            expected = str(values.get(value_key) or "")
            row = next(
                (
                    item for item in _context_rows(context, section)
                    if _context_id(item, aliases) == expected
                ),
                {},
            )
    before = {
        field: current
        for field in operation["fields"]
        if (current := _row_value(row, field)) is not None
    }
    after = {
        field: copy.deepcopy(values[field])
        for field in operation["fields"]
        if field in values
    }
    if operation_id.endswith("_create"):
        before = {}
        after["created"] = True
    if operation_id.endswith("_remove"):
        after["removed"] = True
    return before, after


class SpControlService:
    def __init__(
        self,
        *,
        shop_id: str = SHOP_ID,
        plan_dir: Path = PLAN_DIR,
        audit_dir: Path = AUDIT_DIR,
        credentials_loader: Callable[[], tuple[str, str]] = load_api_credentials,
        client_factory: Callable[[str, str], Any] | None = None,
    ) -> None:
        self.shop_id = shop_id
        self.plan_dir = plan_dir.resolve()
        self.audit_dir = audit_dir.resolve()
        self.credentials_loader = credentials_loader
        self.client_factory = client_factory or (lambda client_id, secret: McpClient(DEFAULT_MCP_URL, client_id, secret, timeout=30))
        self._lock = threading.Lock()
        self._schemas: dict[str, dict[str, Any]] = {}
        self._checked_at: datetime | None = None
        self._last_error = ""

    def _load_schemas(self) -> dict[str, dict[str, Any]]:
        client_id, secret = self.credentials_loader()
        try:
            with self.client_factory(client_id, secret) as client:
                schemas = client.list_tools()
        except Exception as exc:
            self._last_error = type(exc).__name__
            raise SpControlError("赛狐 MCP 暂时不可用，未发送任何广告修改。", status_code=503, error_code="MCP_UNAVAILABLE") from exc
        self._schemas = {name: schema for name, schema in schemas.items() if "_sp_" in name}
        self._checked_at = _now()
        self._last_error = ""
        return self._schemas

    def capabilities(self, *, refresh: bool = False) -> dict[str, Any]:
        if refresh:
            try:
                self._load_schemas()
            except SpControlError:
                pass
        operations = []
        for operation in OPERATIONS:
            tool = _tool_for(operation, self._schemas)
            available = bool(tool) or (operation["verified"] and not self._schemas)
            operations.append({
                **{key: operation[key] for key in ("id", "group", "label", "description")},
                "available": available,
                "availability": "live" if tool else "verified_contract" if operation["verified"] else "awaiting_capability",
                "tool": tool or (operation["tool_candidates"][0] if operation["verified"] else ""),
            })
        return {
            "status": "ok" if self._schemas else "degraded",
            "shop_id": self.shop_id,
            "mcp_status": "available" if self._schemas else "unavailable" if self._last_error else "not_checked",
            "checked_at": self._checked_at.isoformat(timespec="seconds") if self._checked_at else "",
            "operations": operations,
            "policy": {"single_object": True, "preview_required": True, "confirmation_required": True, "audit_required": True},
        }

    def preview(self, payload: Mapping[str, Any], *, context: Mapping[str, Any] | None = None) -> dict[str, Any]:
        operation = OPERATIONS_BY_ID.get(str(payload.get("operation") or ""))
        if not operation:
            raise SpControlError("未知 SP 调控操作。")
        values = _normalize_values(operation, payload)
        _validate_context(operation, values, context)
        schemas = self._load_schemas()
        tool = _tool_for(operation, schemas)
        if not tool:
            raise SpControlError("赛狐 MCP 当前未开放该 SP 写工具。", status_code=409, error_code="CAPABILITY_UNAVAILABLE")
        arguments = _build_arguments(operation, values, schemas[tool], self.shop_id)
        before, after = _control_change_snapshot(operation, values, context)
        campaign_context = context.get("campaign") if isinstance(context.get("campaign"), Mapping) else {}
        context_snapshot = {
            key: current
            for key in ("budget", "strategy", "targeting_type", "adjustments")
            if (current := _row_value(campaign_context, key)) is not None
        }
        client_id, secret = self.credentials_loader()
        created_at = _now()
        base = {
            "version": 1,
            "operation": operation["id"],
            "operation_label": operation["label"],
            "shop_id": self.shop_id,
            "campaign_id": values["campaign_id"],
            "tool": tool,
            "arguments": arguments,
            "values": values,
            "before": before,
            "after": after,
            "context": context_snapshot,
            "created_at": created_at.isoformat(timespec="seconds"),
            "expires_at": (created_at + PLAN_TTL).isoformat(timespec="seconds"),
            "schema_sha256": _schema_digest(schemas[tool]),
            "confirmation": f"确认执行 {values['campaign_id']}",
        }
        plan_id = f"SPC-{hashlib.sha256(json.dumps(base, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()[:20]}"
        plan = {"plan_id": plan_id, **base}
        plan["signature"] = _signature(plan, secret)
        atomic_json(self.plan_dir / f"{plan_id}.json", plan)
        return {key: plan[key] for key in ("plan_id", "operation", "operation_label", "campaign_id", "tool", "values", "before", "after", "created_at", "expires_at", "confirmation")}

    def execute(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        plan_id = str(payload.get("plan_id") or "")
        if not PLAN_ID_RE.fullmatch(plan_id):
            raise SpControlError("plan_id 无效。")
        try:
            plan = json.loads((self.plan_dir / f"{plan_id}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise SpControlError("调控计划不存在或已损坏。", status_code=404, error_code="PLAN_NOT_FOUND") from exc
        client_id, secret = self.credentials_loader()
        if not hmac.compare_digest(str(plan.get("signature") or ""), _signature(plan, secret)):
            raise SpControlError("调控计划签名无效。", status_code=409, error_code="PLAN_TAMPERED")
        if str(payload.get("confirmation") or "") != plan.get("confirmation"):
            raise SpControlError("确认文本不匹配。")
        if str(plan.get("shop_id") or "") != self.shop_id:
            raise SpControlError("调控计划不属于当前店铺。", status_code=409, error_code="CONTROL_SHOP_MISMATCH")
        if datetime.fromisoformat(plan["expires_at"]) < _now():
            raise SpControlError("调控计划已过期，请重新预览。", status_code=409, error_code="PLAN_EXPIRED")
        audit_path = self.audit_dir / f"execution-{plan_id}.json"
        with self._lock:
            attempted_at = _now()
            audit = {
                "plan_id": plan_id,
                "operation": plan["operation"],
                "shop_id": self.shop_id,
                "campaign_id": plan["campaign_id"],
                "tool": plan["tool"],
                "values": plan.get("values", {}),
                "before": plan.get("before", {}),
                "after": plan.get("after", {}),
                "context": plan.get("context", {}),
                "operation_label": plan.get("operation_label", ""),
                "attempted_at": attempted_at.isoformat(timespec="seconds"),
                "status": "reserved",
            }
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with audit_path.open("x", encoding="utf-8") as handle:
                    json.dump(audit, handle, ensure_ascii=False, indent=2)
                    handle.write("\n")
            except FileExistsError as exc:
                raise SpControlError("该调控计划已经执行过。", status_code=409, error_code="PLAN_ALREADY_USED") from exc
            try:
                with self.client_factory(client_id, secret) as client:
                    schemas = client.list_tools()
                    schema = schemas.get(plan["tool"])
                    if not isinstance(schema, Mapping) or _schema_digest(schema) != plan["schema_sha256"]:
                        raise SpControlError("MCP 工具 schema 已变化，请重新预览。", status_code=409, error_code="MCP_SCHEMA_CHANGED")
                    result = api_data(client.call_tool(plan["tool"], plan["arguments"]))
                audit.update(status="succeeded", result=result, finished_at=_now().isoformat(timespec="seconds"))
            except Exception as exc:
                audit.update(status="failed", error_type=type(exc).__name__, finished_at=_now().isoformat(timespec="seconds"))
                atomic_json(audit_path, audit)
                if isinstance(exc, SpControlError):
                    raise
                raise SpControlError("赛狐未确认调控成功，请查看审计记录后重试。", status_code=502, error_code="EXECUTION_FAILED") from exc
            atomic_json(audit_path, audit)
        return {
            "status": audit["status"],
            "plan_id": plan_id,
            "operation": plan["operation"],
            "operation_label": plan["operation_label"],
            "campaign_id": plan["campaign_id"],
            "finished_at": audit["finished_at"],
            "result": audit.get("result", {}),
        }
