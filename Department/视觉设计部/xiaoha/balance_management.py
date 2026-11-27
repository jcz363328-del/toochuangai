"""Cache only the display-safe percentage of the current account balance."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import math
import threading
import time


SHANGHAI_TIMEZONE = timezone(timedelta(hours=8), name="Asia/Shanghai")


def balance_usd_to_percent(value) -> float:
    """Convert a real remaining balance against the fixed reference capacity."""
    if isinstance(value, bool) or not isinstance(value, (Decimal, int, float, str)):
        raise ValueError("余额数据无效")
    try:
        amount = value if isinstance(value, Decimal) else Decimal(str(value).strip())
        if not amount.is_finite():
            raise ValueError("余额数据无效")
        percent = float(max(Decimal(0), amount) / Decimal("100") * Decimal("100"))
    except (InvalidOperation, OverflowError):
        raise ValueError("余额数据无效") from None
    if not math.isfinite(percent):
        raise ValueError("余额数据无效")
    return percent


@dataclass(frozen=True)
class _CacheEntry:
    percent: float | None
    updated_at: str
    error: bool
    expires_at: float

    def snapshot(self):
        return {"percent": self.percent, "updated_at": self.updated_at, "error": self.error}


@dataclass
class _InFlight:
    done: threading.Event = field(default_factory=threading.Event)
    result: dict | None = None


class BalanceCache:
    """Bounded per-scope cache, sharing one refresh among concurrent callers."""

    def __init__(self, *, clock=time.monotonic, now=None, ttl_seconds=300,
                 failure_ttl_seconds=30, max_scopes=8):
        self._clock = clock
        self._now = now or (lambda: datetime.now(SHANGHAI_TIMEZONE))
        self._ttl = ttl_seconds
        self._failure_ttl = failure_ttl_seconds
        self._max_scopes = min(8, max(1, int(max_scopes)))
        self._entries: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._inflight: dict[str, _InFlight] = {}
        self._lock = threading.Lock()

    def snapshot(self, scope, fetch_usd, force=False):
        """The caller supplies an opaque scope and a real-balance fetch function."""
        with self._lock:
            previous = self._entries.get(scope)
            running = self._inflight.get(scope)
            if running is None and not force and previous and self._clock() < previous.expires_at:
                self._entries.move_to_end(scope)
                return previous.snapshot()
            if running is None:
                running = _InFlight()
                self._inflight[scope] = running
                owns_refresh = True
            else:
                owns_refresh = False

        if not owns_refresh:
            running.done.wait()
            return dict(running.result)

        # Never put fetched amounts, provider payloads, callbacks or exceptions
        # into the cache. Only the public display fields survive a refresh.
        entry = _CacheEntry(previous.percent if previous else None,
                            previous.updated_at if previous else "", True, 0)
        try:
            percent = balance_usd_to_percent(fetch_usd())
            updated = self._now()
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=SHANGHAI_TIMEZONE)
            updated_at = updated.astimezone(SHANGHAI_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
            entry = _CacheEntry(percent, updated_at, False, 0)
        except Exception:
            pass
        finally:
            # Even a cancelled owner must release all concurrent waiters.
            entry = _CacheEntry(entry.percent, entry.updated_at, entry.error,
                                self._clock() + (self._failure_ttl if entry.error else self._ttl))
            with self._lock:
                self._entries[scope] = entry
                self._entries.move_to_end(scope)
                while len(self._entries) > self._max_scopes:
                    self._entries.popitem(last=False)
                running.result = entry.snapshot()
                self._inflight.pop(scope, None)
                running.done.set()
        return entry.snapshot()
