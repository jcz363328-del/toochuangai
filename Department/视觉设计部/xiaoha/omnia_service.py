"""Join key leases and provider-confirmed accounting around one model call.

No provider generation or retry lives here. The original function keeps its
normal return value and error. Usage lookups cannot hide a completed result.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from functools import lru_cache, wraps
import inspect
import json
import os
from pathlib import Path
import re
import threading
from urllib.parse import quote, urlsplit
import uuid

import requests

from Department.视觉设计部.xiaoha.omnia_cost_ledger import CostLedger
from Department.视觉设计部.xiaoha.omnia_key_pool import (
    bind_current_omnia_task, credential_fingerprint, get_omnia_key_pool,
    load_omnia_api_keys,
)


_current_call = ContextVar("xiaoha_omnia_managed_call", default=None)
_ledger_init_lock = threading.Lock()


class OmniaUsageUnavailable(RuntimeError):
    """The read-only usage lookup failed; no HTTP details are exposed."""


class OmniaAccountingOutcomeUnknown(RuntimeError):
    """The paid task exists but its local recovery metadata could not be saved."""


def _baseline_path():
    return Path(os.environ.get("XIAOHA_OMNIA_BASELINE_FILE") or
                Path(__file__).parent / "history" / ".credentials" / "balance_baseline.json")


@lru_cache(maxsize=4)
def _cached_ledger(db_path, baseline_path):
    try:
        baseline = json.loads(Path(baseline_path).read_text(encoding="utf-8-sig"))
        ledger = CostLedger(db_path)
        ledger.initialize_balance(baseline["balance_usd"], baseline["usage_by_key"],
                                  baseline_id=baseline["baseline_id"])
        return ledger
    except Exception:
        raise RuntimeError("小哈余额初始配置无法读取，请联系管理员检查。") from None


def get_cost_ledger() -> CostLedger | None:
    """Enable management only after the private, verified baseline is present."""
    if os.environ.get("XIAOHA_OMNIA_TRACKING_ENABLED", "").strip() == "0":
        return None
    baseline = _baseline_path()
    if not baseline.is_file():
        return None
    db_path = Path(os.environ.get("XIAOHA_OMNIA_COST_DB") or
                   Path(__file__).parent / "history" / "omnia_costs.sqlite3")
    with _ledger_init_lock:
        return _cached_ledger(str(db_path.resolve()), str(baseline.resolve()))


def _api_base(api_base=None):
    base = str(api_base or os.environ.get("OMNIAKEY_BASE_URL") or
               "https://api.omniakey.com").strip().rstrip("/")
    if base.lower().endswith("/v1"):
        base = base[:-3]
    parsed = urlsplit(base)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or
            parsed.password or parsed.query or parsed.fragment):
        raise OmniaUsageUnavailable("暂时无法查询用量，请稍后刷新。")
    return base


def fetch_usage(api_key: str, api_base=None) -> Decimal:
    """Read the configured provider's per-key cumulative cents as USD.

    This compatibility endpoint was verified for this account's per-key USD
    counters. Redirects are disabled so Authorization cannot leave the origin.
    """
    try:
        response = requests.get(
            _api_base(api_base) + "/v1/dashboard/billing/usage",
            headers={"Authorization": "Bearer " + api_key},
            timeout=(5, 12), allow_redirects=False,
        )
        if response.status_code != 200:
            raise ValueError("Usage response unavailable")
        body = response.json()
        value = body.get("total_usage") if isinstance(body, dict) else None
        if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
            raise ValueError("Invalid usage counter")
        total = Decimal(str(value))
        if not total.is_finite() or total < 0 or total > Decimal("1e14"):
            raise ValueError("Invalid usage counter")
        return total / Decimal(100)
    except Exception:
        raise OmniaUsageUnavailable("暂时无法查询用量，请稍后刷新。") from None


def fetch_task_status(api_key: str, task_id: str, api_base=None) -> str | None:
    """Read the existing task using its original key; never submit generation."""
    try:
        if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", task_id):
            raise ValueError("Invalid task identifier")
        response = requests.get(
            _api_base(api_base) + "/v1/media/tasks/" + quote(task_id, safe=""),
            headers={"Authorization": "Bearer " + api_key},
            timeout=(5, 12), allow_redirects=False,
        )
        if response.status_code != 200:
            raise ValueError("Task response unavailable")
        body = response.json()
        status = body.get("status") if isinstance(body, dict) else None
        if not isinstance(status, str):
            raise ValueError("Invalid task status")
        normalized = status.strip().lower()
        if normalized in {"succeeded", "success", "completed"}:
            return "success"
        if normalized in {"failed", "error"}:
            return "failed"
        if normalized in {"canceled", "cancelled"}:
            return "canceled"
        if normalized in {"queued", "running", "pending", "processing", "submitted"}:
            return None
        raise ValueError("Unknown task status")
    except Exception:
        raise OmniaUsageUnavailable("暂时无法确认原任务状态，请稍后刷新。") from None


def reconcile_omnia_key(ledger, credential, *, usage_fetcher=None, task_status_fetcher=None,
                        api_base=None):
    """Reconcile one exclusively leased key without issuing a paid request.

    Terminal task status and cumulative usage are considered together, allowing
    only the ledger's narrowly verified refund. Failed status/usage lookups do
    not fabricate a refund or erase a real error.
    """
    usage_fetcher = usage_fetcher or (lambda key: fetch_usage(key, api_base))
    task_status_fetcher = task_status_fetcher or (
        lambda key, task: fetch_task_status(key, task, api_base)
    )
    fingerprint = credential.fingerprint
    status_failed = False
    outcomes = {}
    blocked = False

    def blocks_new_call(candidates):
        for item in candidates:
            status = outcomes.get(item["task_id"], item.get("status"))
            if status == "uncertain":
                # The remote job may still be running after the local lease's
                # uncertainty cooldown. Do not overlap another paid task.
                return True
            if (status in {"failed", "canceled"} and item.get("is_latest") and
                    item.get("cost_usd") is not None):
                if Decimal(str(item["cost_usd"])) > Decimal(str(item.get("refund_usd") or 0)):
                    return True
        return False

    try:
        ledger.recover_interrupted_key_calls(fingerprint)
        candidates = ledger.get_task_reconciliation_candidates(fingerprint)
        for task_id in dict.fromkeys(item["task_id"] for item in candidates if item.get("task_id")):
            try:
                outcome = task_status_fetcher(credential.api_key, task_id)
                if outcome is not None:
                    outcomes[task_id] = outcome
            except Exception:
                status_failed = True
        blocked = blocks_new_call(candidates)
        value = usage_fetcher(credential.api_key)
        reconciled = bool(ledger.reconcile_task_outcomes(fingerprint, outcomes, value))
        pending = ledger.latest_pending_call(fingerprint)
        if reconciled and pending:
            ledger.settle_call(pending["call_id"], value,
                               attribution_confirmed=pending["attribution_confirmed"])
        blocked = blocks_new_call(ledger.get_task_reconciliation_candidates(fingerprint))
        return {"usage": value, "reconciled": reconciled,
                "error": not reconciled, "task_status_error": status_failed,
                "blocked": blocked}
    except Exception:
        try:
            ledger.mark_key_error(fingerprint)
        except Exception:
            pass
        return {"usage": None, "reconciled": False, "error": True,
                "task_status_error": status_failed, "blocked": blocked}


@dataclass
class _ManagedCall:
    ledger: CostLedger = field(repr=False)
    api_key: str = field(repr=False)
    api_base: str
    fingerprint: str
    call_id: str
    model: str
    provider_outcome: str = ""
    final_zero: bool = False


def current_omnia_call_metadata():
    """Server-only receipt metadata; contains no credential or balance value."""
    state = _current_call.get()
    return {"call_id": state.call_id, "key_fingerprint": state.fingerprint} if state else {}


def record_omnia_task(task_id: str):
    """Persist the original task/key/call binding after the provider accepts it."""
    state = _current_call.get()
    if state is None:
        return
    try:
        bind_current_omnia_task(task_id)
        if state.call_id:
            state.ledger.attach_task(state.call_id, task_id)
    except Exception:
        raise OmniaAccountingOutcomeUnknown(
            "OmniaKey 任务已提交，但本地回执绑定失败，未自动重新提交；请继续查询原任务。"
        ) from None


def record_omnia_provider_status(status: str):
    """Call on provider success before downloading the generated asset."""
    if status not in {"success", "failed", "uncertain", "rejected"}:
        raise ValueError("Invalid OmniaKey provider status")
    state = _current_call.get()
    if state is not None:
        state.provider_outcome = "failed" if status == "rejected" else status
        state.final_zero = status == "rejected"


def record_omnia_model(model: str):
    """Record a selected fallback model without starting another charge row."""
    state = _current_call.get()
    if state is None:
        return
    state.model = str(model)
    if state.call_id:
        try:
            state.ledger.update_call_model(state.call_id, state.model)
        except Exception:
            raise RuntimeError("小哈调用记录暂时无法更新，请稍后重试。") from None


def _unknown_outcome(error):
    if error is None:
        return False
    return (type(error).__name__ in {"OmniaImageOutcomeUnknown", "ImageOutcomeUnknown",
                                   "OmniaTextOutcomeUnknown", "OmniaAccountingOutcomeUnknown"} or
            isinstance(error, (requests.Timeout, requests.ConnectionError, KeyboardInterrupt)) or
            any(marker in str(error) for marker in (
                "未自动重新提交", "provider_submit_uncertain", "远端结果尚未确认")))


def _read_usage_safely(api_key, api_base):
    try:
        return fetch_usage(api_key, api_base)
    except Exception:
        return None


def _read_task_receipt(receipt_path, task_id):
    """Find recovery metadata without loading the complete append-only log.

    An unreadable or damaged receipt must not silently select the old primary
    credential. Legacy receipts without accounting metadata remain supported.
    """
    if receipt_path is None:
        return None
    path = Path(receipt_path)
    latest = None
    damaged = False
    try:
        with path.open("r", encoding="utf-8-sig") as source:
            while True:
                line = source.readline(65537)
                if not line:
                    break
                if len(line) > 65536:
                    raise ValueError("Oversized receipt")
                if not line.strip():
                    continue
                try:
                    receipt = json.loads(line)
                except (TypeError, ValueError):
                    damaged = True
                    continue
                if not isinstance(receipt, dict) or receipt.get("task_id") != task_id:
                    continue
                if "call_id" not in receipt and "key_fingerprint" not in receipt:
                    continue  # Original single-key receipts have no metadata.
                call_id = receipt.get("call_id")
                fingerprint = receipt.get("key_fingerprint")
                if (not isinstance(call_id, str) or not call_id.strip() or len(call_id) > 256 or
                        not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint)):
                    damaged = True
                    continue
                latest = {"call_id": call_id, "key_fingerprint": fingerprint}
    except FileNotFoundError:
        return None
    except Exception:
        raise RuntimeError("OmniaKey 原任务回执暂时无法读取，未切换密钥或重新提交。") from None
    if damaged and latest is None:
        raise RuntimeError("OmniaKey 原任务回执不完整，未切换密钥或重新提交，请联系管理员恢复回执。")
    return latest


@contextmanager
def managed_omnia_context(*, primary_key, model, resolution="", task_id="", resume=False,
                          api_base=None, account_context="", receipt_path=None):
    """Wrap streaming or ordinary work; obtain admission before this context.

    The main key loader should return current_omnia_credential().api_key while
    this context is active. A resume reuses its old row, never creates a debit.
    """
    if _current_call.get() is not None:
        yield _current_call.get()
        return
    ledger = get_cost_ledger()
    if ledger is None:
        yield None
        return
    keys = load_omnia_api_keys(primary_key)
    base = _api_base(api_base)
    pool = get_omnia_key_pool()
    existing = ledger.find_call_by_task(task_id) if resume and task_id else None
    restore_receipt_binding = False
    if resume and task_id and existing is None:
        receipt = _read_task_receipt(receipt_path, task_id)
        if receipt is not None:
            existing = ledger.find_call_by_id(receipt["call_id"])
            if (existing is None or existing["key_fingerprint"] != receipt["key_fingerprint"] or
                    existing["task_id"] not in ("", receipt["call_id"], task_id)):
                raise RuntimeError("OmniaKey 原任务回执与调用记录不一致，未切换密钥或重新提交。")
            restore_receipt_binding = True
    preferred = (existing["key_fingerprint"] if existing else
                 (pool.task_fingerprint(task_id) or credential_fingerprint(primary_key))
                 if resume else None)
    with pool.hold(keys, preferred_fingerprint=preferred,
                   task_id=task_id if resume else None) as credential:
        call_id = existing["call_id"] if existing else "" if resume else uuid.uuid4().hex
        if restore_receipt_binding:
            ledger.attach_task(call_id, task_id)
        if not resume:
            reconciliation = reconcile_omnia_key(ledger, credential, api_base=base)
            # Accounting uncertainty must never reject a new generation.
            # Without an isolated usage window, retain pending attribution;
            # finish_call can still refresh aggregate usage conservatively.
            before = (reconciliation["usage"]
                      if reconciliation["reconciled"] and not reconciliation["blocked"]
                      else None)
            ledger.begin_call(call_id, "", credential.fingerprint, str(model or "unknown"),
                              str(resolution or ""), before, account_context=account_context)
        state = _ManagedCall(ledger, credential.api_key, base, credential.fingerprint,
                             call_id, str(model or "unknown"))
        token = _current_call.set(state)
        error = None
        try:
            yield state
        except BaseException as exc:
            error = exc
            raise
        finally:
            _current_call.reset(token)
            after = _read_usage_safely(credential.api_key, base)
            outcome = ("success" if error is None or state.provider_outcome == "success" else
                       "failed" if state.provider_outcome == "failed" and not state.final_zero else
                       "uncertain" if _unknown_outcome(error) else state.provider_outcome or "failed")
            try:
                if call_id:
                    ledger.finish_call(call_id, outcome, after,
                                       final_zero=state.final_zero and outcome == "failed")
                elif after is not None:
                    ledger.reconcile_key(credential.fingerprint, after)
                else:
                    ledger.mark_key_error(credential.fingerprint)
            except Exception:
                # Never replace a paid result or the original provider error.
                # The existing row remains pending for later reconciliation.
                try:
                    ledger.mark_key_error(credential.fingerprint)
                except Exception:
                    pass


def managed_omnia_call(kind="image", *, resume=False):
    """Decorate inside limited_request so admission precedes a key lease.

    Argument binding preserves defaults and supports positional calls. The
    decorated module supplies its established primary loader and API base.
    """
    if kind not in {"image", "text"}:
        raise ValueError("Invalid OmniaKey call kind")

    def decorate(function):
        signature = inspect.signature(function)

        @wraps(function)
        def wrapped(*args, **kwargs):
            if _current_call.get() is not None or get_cost_ledger() is None:
                return function(*args, **kwargs)
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            loader = function.__globals__.get("load_omnia_api_key")
            if not callable(loader):
                raise RuntimeError("OmniaKey 主密钥加载器未配置。")
            model = bound.arguments.get("model") or bound.arguments.get("primary_model") or kind
            with managed_omnia_context(
                primary_key=loader(), model=model,
                resolution=bound.arguments.get("resolution", ""),
                task_id=bound.arguments.get("task_id", ""), resume=resume,
                api_base=function.__globals__.get("OMNIAKEY_API_BASE"),
                receipt_path=function.__globals__.get("OMNIAKEY_TASK_RECEIPTS_FILE"),
            ):
                return function(*args, **kwargs)
        return wrapped
    return decorate
