"""Persistent accounting from provider-confirmed, per-key cumulative usage.

The ledger never charges the provider.  It reconciles a user-verified account
balance with subsequent usage, while keeping ambiguous individual calls pending.
All public records express amounts as percentages of the fixed 100 USD basis.
Credentials and HTTP responses do not belong in this module.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
import sqlite3
import time


_SHANGHAI = timezone(timedelta(hours=8))
_KEY_ID = re.compile(r"^[0-9a-f]{16,128}$")
_USAGE_EPSILON = Decimal("0.000000000001")


class KeyBusyError(RuntimeError):
    """A call already owns this key's accounting window."""


def _amount(value):
    if isinstance(value, bool) or not isinstance(value, (Decimal, int, float, str)):
        raise ValueError("Invalid cumulative usage")
    try:
        result = Decimal(str(value).strip())
        if not result.is_finite() or result < 0 or result > Decimal("1e12"):
            raise ValueError("Invalid cumulative usage")
        return result
    except InvalidOperation:
        raise ValueError("Invalid cumulative usage") from None


def _text(value, name, *, empty=False):
    if not isinstance(value, str) or len(value) > 256 or (not empty and not value.strip()):
        raise ValueError("Invalid " + name)
    return value


def _fingerprint(value):
    if not isinstance(value, str) or not _KEY_ID.fullmatch(value):
        raise ValueError("Use a hexadecimal key fingerprint, never a credential")
    return value


class CostLedger:
    def __init__(self, db_path, *, now=None):
        self.db_path = str(db_path)
        self._now = now or (lambda: datetime.now(_SHANGHAI))
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            self._enable_wal(db)
            db.executescript("""
                CREATE TABLE IF NOT EXISTS account_baseline (
                    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                    baseline_id TEXT NOT NULL,
                    balance_usd TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS key_usage (
                    fingerprint TEXT PRIMARY KEY,
                    baseline_usd TEXT NOT NULL,
                    current_usd TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    error INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS calls (
                    call_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    key_fingerprint TEXT NOT NULL REFERENCES key_usage(fingerprint),
                    model TEXT NOT NULL,
                    resolution TEXT NOT NULL,
                    account_context TEXT NOT NULL,
                    outcome TEXT NOT NULL DEFAULT 'submitted',
                    billing_status TEXT NOT NULL DEFAULT 'pending',
                    before_usd TEXT,
                    after_usd TEXT,
                    cost_usd TEXT,
                    refund_usd TEXT NOT NULL DEFAULT '0',
                    attributable INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    finished_at TEXT,
                    settled_at TEXT
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_call_per_key
                    ON calls(key_fingerprint) WHERE outcome = 'submitted';
                CREATE INDEX IF NOT EXISTS calls_task ON calls(task_id);
                CREATE INDEX IF NOT EXISTS calls_key ON calls(key_fingerprint);
            """)
            # Old ledgers retain their original costs and baseline. Serialize
            # the additive migration across simultaneous first-open workers.
            db.execute("BEGIN IMMEDIATE")
            try:
                columns = {row["name"] for row in db.execute("PRAGMA table_info(calls)")}
                if "refund_usd" not in columns:
                    db.execute("ALTER TABLE calls ADD COLUMN refund_usd TEXT NOT NULL DEFAULT '0'")
                db.commit()
            except BaseException:
                db.rollback()
                raise

    @staticmethod
    def _enable_wal(db, *, timeout=10.0):
        """Retry cross-process first-open WAL contention for at most ten seconds."""
        deadline = time.monotonic() + min(10.0, max(0.0, float(timeout)))
        try:
            while True:
                remaining = max(0.0, deadline - time.monotonic())
                # SQLite's ordinary connection timeout is longer than this
                # startup budget, so cap each individual attempt explicitly.
                db.execute(f"PRAGMA busy_timeout={min(100, int(remaining * 1000))}")
                try:
                    db.execute("PRAGMA journal_mode=WAL")
                    return
                except sqlite3.OperationalError as exc:
                    code = getattr(exc, "sqlite_errorcode", 0) or 0
                    contention = ((code & 0xFF) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)
                                  or "locked" in str(exc).lower() or "busy" in str(exc).lower())
                    remaining = deadline - time.monotonic()
                    if not contention or remaining <= 0:
                        raise
                    time.sleep(min(.05, remaining))
        finally:
            db.execute("PRAGMA busy_timeout=30000")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def _write(self):
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def _timestamp(self):
        value = self._now()
        if value.tzinfo is None:
            value = value.replace(tzinfo=_SHANGHAI)
        return value.astimezone(_SHANGHAI).strftime("%Y-%m-%d %H:%M:%S")

    def initialize_balance(self, balance_usd, usage_by_key, *, baseline_id):
        """Initialize once; repeated startup never resets the spending baseline.

        The caller must have confirmed that these are USD *per-key* counters.
        Existing baselines can only be reused with the same id and key set.
        """
        balance = _amount(balance_usd)
        baseline_id = _text(baseline_id, "baseline id")
        values = {_fingerprint(key): _amount(value) for key, value in usage_by_key.items()}
        if not values:
            raise ValueError("At least one confirmed key usage counter is required")
        with self._write() as db:
            existing = db.execute("SELECT * FROM account_baseline").fetchone()
            if existing:
                keys = {r[0] for r in db.execute("SELECT fingerprint FROM key_usage")}
                if existing["baseline_id"] != baseline_id or keys != set(values):
                    raise ValueError("An existing baseline cannot be silently replaced")
                return False
            now = self._timestamp()
            db.execute("INSERT INTO account_baseline VALUES (1, ?, ?, ?)",
                       (baseline_id, str(balance), now))
            db.executemany("INSERT INTO key_usage VALUES (?, ?, ?, ?, 0)",
                           [(key, str(value), str(value), now) for key, value in values.items()])
        return True

    @staticmethod
    def _require_key(db, fingerprint):
        row = db.execute("SELECT * FROM key_usage WHERE fingerprint = ?", (fingerprint,)).fetchone()
        if row is None:
            raise ValueError("Key has no confirmed starting baseline")
        return row

    def _observe(self, db, fingerprint, total, now):
        row = self._require_key(db, fingerprint)
        current = Decimal(row["current_usd"])
        if total < current - _USAGE_EPSILON:
            # Resets, stale replicas and refunds cannot be distinguished from a
            # cumulative counter alone. Preserve the last reconciled balance.
            db.execute("UPDATE key_usage SET error = 1 WHERE fingerprint = ?", (fingerprint,))
            return False
        # JSON float representations can differ at the last few digits. Do
        # not manufacture a refund or retain a false warning for that noise.
        total = max(current, total)
        db.execute("UPDATE key_usage SET current_usd = ?, updated_at = ?, error = 0 WHERE fingerprint = ?",
                   (str(total), now, fingerprint))
        return True

    def begin_call(self, call_id, task_id, key_fingerprint, model, resolution,
                   before_usage_usd=None, *, account_context=""):
        """Open one accounting window; a duplicate id never submits a new debit.

        The caller must additionally hold its key lease across the HTTP request.
        An older unresolved call makes this window unsafe to attribute, but does
        not prevent generation or aggregate balance reconciliation.
        """
        call_id = _text(call_id, "call id")
        task_id = _text(task_id, "task id", empty=True)
        key_fingerprint = _fingerprint(key_fingerprint)
        model = _text(model, "model")
        resolution = _text(resolution, "resolution", empty=True)
        account_context = _text(account_context, "account context", empty=True)
        before = None if before_usage_usd is None else _amount(before_usage_usd)
        identity = (task_id, key_fingerprint, model, resolution, account_context)
        with self._write() as db:
            existing = db.execute("SELECT * FROM calls WHERE call_id = ?", (call_id,)).fetchone()
            if existing:
                old_identity = tuple(existing[k] for k in
                                     ("task_id", "key_fingerprint", "model", "resolution", "account_context"))
                if old_identity != identity:
                    raise ValueError("Call id already belongs to a different request")
                return self._public_call(existing)
            self._require_key(db, key_fingerprint)
            if db.execute("SELECT 1 FROM calls WHERE key_fingerprint = ? AND outcome = 'submitted'",
                          (key_fingerprint,)).fetchone():
                raise KeyBusyError("This key already has an active call")
            pending = db.execute("SELECT 1 FROM calls WHERE key_fingerprint = ? AND billing_status = 'pending'",
                                 (key_fingerprint,)).fetchone()
            now = self._timestamp()
            observed = before is not None and self._observe(db, key_fingerprint, before, now)
            if before is None:
                db.execute("UPDATE key_usage SET error = 1 WHERE fingerprint = ?", (key_fingerprint,))
            db.execute("""INSERT INTO calls
                (call_id, task_id, key_fingerprint, model, resolution, account_context,
                 before_usd, attributable, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                       (call_id, *identity, str(before) if observed else None,
                        int(observed and not pending), now))
            row = db.execute("SELECT * FROM calls WHERE call_id = ?", (call_id,)).fetchone()
            return self._public_call(row)

    def finish_call(self, call_id, status, after_usage_usd=None, *,
                    attribution_confirmed=True, final_zero=False):
        """Record the request outcome and optionally reconcile its final usage.

        A zero difference remains pending unless the caller has authoritative
        confirmation that billing is final. A failed request may still have a
        positive provider charge; its failure is retained independently.
        """
        if status not in ("success", "failed", "uncertain"):
            raise ValueError("Invalid call outcome")
        after = None if after_usage_usd is None else _amount(after_usage_usd)
        with self._write() as db:
            row = db.execute("SELECT * FROM calls WHERE call_id = ?", (call_id,)).fetchone()
            if row is None:
                raise ValueError("Unknown call id")
            now = self._timestamp()
            if row["outcome"] == "submitted" or row["outcome"] == "uncertain":
                db.execute("UPDATE calls SET outcome = ?, finished_at = COALESCE(finished_at, ?) WHERE call_id = ?",
                           (status, now, call_id))
                row = db.execute("SELECT * FROM calls WHERE call_id = ?", (call_id,)).fetchone()
            self._settle(db, row, after, now, attribution_confirmed, final_zero)
            return self._public_call(db.execute("SELECT * FROM calls WHERE call_id = ?", (call_id,)).fetchone())

    def _settle(self, db, row, after, now, attribution_confirmed, final_zero):
        if after is None:
            db.execute("UPDATE key_usage SET error = 1 WHERE fingerprint = ?", (row["key_fingerprint"],))
            return
        observed = self._observe(db, row["key_fingerprint"], after, now)
        if row["billing_status"] == "settled":
            # A repeated request recovery can refresh the key's health and
            # total without changing the immutable original per-call charge.
            return
        if not observed or not attribution_confirmed or not row["attributable"] or row["before_usd"] is None:
            return
        # A later call makes late cumulative readings ambiguous, even if its
        # own billing has already completed. Never give its spend to this call.
        later = db.execute("SELECT 1 FROM calls WHERE key_fingerprint = ? AND rowid > "
                           "(SELECT rowid FROM calls WHERE call_id = ?)",
                           (row["key_fingerprint"], row["call_id"])).fetchone()
        if later:
            return
        cost = after - Decimal(row["before_usd"])
        if abs(cost) <= _USAGE_EPSILON:
            cost = Decimal(0)
        if cost < 0 or (cost == 0 and not final_zero):
            return
        db.execute("UPDATE calls SET after_usd = ?, cost_usd = ?, billing_status = 'settled', "
                   "settled_at = ? WHERE call_id = ?",
                   (str(after), str(cost), now, row["call_id"]))

    def settle_call(self, call_id, after_usage_usd, *, attribution_confirmed=True, final_zero=False):
        """Retry reconciliation without changing the generation outcome."""
        after = _amount(after_usage_usd)
        with self._write() as db:
            row = db.execute("SELECT * FROM calls WHERE call_id = ?", (call_id,)).fetchone()
            if row is None:
                raise ValueError("Unknown call id")
            if row["outcome"] == "submitted":
                raise ValueError("Finish the request before settling its usage")
            self._settle(db, row, after, self._timestamp(), attribution_confirmed, final_zero)
            return self._public_call(db.execute("SELECT * FROM calls WHERE call_id = ?", (call_id,)).fetchone())

    def reconcile_key(self, key_fingerprint, total_usage_usd):
        """Refresh aggregate balance only; do not guess a pending call's cost."""
        key_fingerprint = _fingerprint(key_fingerprint)
        total = _amount(total_usage_usd)
        with self._write() as db:
            return self._observe(db, key_fingerprint, total, self._timestamp())

    def get_task_reconciliation_candidates(self, key_fingerprint):
        """Return SERVER-ONLY original-key tasks eligible for status lookup.

        Unknown outcomes can become confirmed without changing their costs.
        Only the latest call can qualify for a counter-backed refund, because
        any subsequent call would make a cumulative decrease ambiguous.
        """
        key_fingerprint = _fingerprint(key_fingerprint)
        with self._connect() as db:
            latest = db.execute("SELECT call_id FROM calls WHERE key_fingerprint = ? "
                                "ORDER BY rowid DESC LIMIT 1", (key_fingerprint,)).fetchone()
            if latest is None:
                return []
            rows = db.execute("SELECT * FROM calls WHERE key_fingerprint = ? AND task_id != '' "
                              "AND (outcome = 'uncertain' OR call_id = ?) ORDER BY rowid DESC LIMIT 100",
                              (key_fingerprint, latest["call_id"])).fetchall()
            candidates = []
            for row in rows:
                if row["outcome"] != "uncertain" and not (
                        row["billing_status"] == "settled" and row["cost_usd"] is not None
                        and Decimal(row["cost_usd"]) > Decimal(row["refund_usd"])):
                    continue
                candidates.append(dict(self._recovery_call(row),
                                       after_usage_usd=row["after_usd"], cost_usd=row["cost_usd"],
                                       refund_usd=row["refund_usd"],
                                       is_latest=row["call_id"] == latest["call_id"]))
            return candidates

    def reconcile_task_outcomes(self, key_fingerprint, outcomes, after_usage_usd):
        """Apply original-key terminal statuses and an unambiguous full refund.

        The caller MUST hold the original key's exclusive lease and obtain the
        statuses using that key, followed by a fresh cumulative usage reading.
        An accepted refund needs a failed/canceled latest call, its recorded
        charged window, and a matching counter drop. No price estimate or
        failure status alone is enough to restore balance.
        """
        key_fingerprint = _fingerprint(key_fingerprint)
        after = _amount(after_usage_usd)
        if not isinstance(outcomes, dict):
            raise ValueError("Invalid task outcomes")
        checked = {}
        for task_id, status in outcomes.items():
            task_id = _text(task_id, "task id")
            if status not in ("success", "failed", "canceled"):
                raise ValueError("Only confirmed terminal outcomes can be reconciled")
            checked[task_id] = status
        with self._write() as db:
            key = self._require_key(db, key_fingerprint)
            now = self._timestamp()
            for task_id, status in checked.items():
                db.execute("UPDATE calls SET outcome = ?, finished_at = COALESCE(finished_at, ?) "
                           "WHERE key_fingerprint = ? AND task_id = ?",
                           ("success" if status == "success" else "failed", now, key_fingerprint, task_id))
            current = Decimal(key["current_usd"])
            if after >= current - _USAGE_EPSILON:
                return self._observe(db, key_fingerprint, after, now)

            latest = db.execute("SELECT * FROM calls WHERE key_fingerprint = ? ORDER BY rowid DESC LIMIT 1",
                                (key_fingerprint,)).fetchone()
            eligible = (latest is not None and checked.get(latest["task_id"]) in ("failed", "canceled")
                        and latest["billing_status"] == "settled" and latest["cost_usd"] is not None
                        and latest["before_usd"] is not None and latest["after_usd"] is not None)
            if eligible:
                original = Decimal(latest["cost_usd"])
                refunded = Decimal(latest["refund_usd"])
                outstanding = original - refunded
                matches = (outstanding > 0
                           and abs(current - (Decimal(latest["after_usd"]) - refunded)) <= _USAGE_EPSILON
                           and abs((current - after) - outstanding) <= _USAGE_EPSILON
                           and abs(after - Decimal(latest["before_usd"])) <= _USAGE_EPSILON)
                if matches:
                    db.execute("UPDATE calls SET refund_usd = ? WHERE call_id = ?",
                               (str(original), latest["call_id"]))
                    db.execute("UPDATE key_usage SET current_usd = ?, updated_at = ?, error = 0 "
                               "WHERE fingerprint = ?", (str(after), now, key_fingerprint))
                    return True
            db.execute("UPDATE key_usage SET error = 1 WHERE fingerprint = ?", (key_fingerprint,))
            return False

    def mark_key_error(self, key_fingerprint):
        key_fingerprint = _fingerprint(key_fingerprint)
        with self._write() as db:
            self._require_key(db, key_fingerprint)
            db.execute("UPDATE key_usage SET error = 1 WHERE fingerprint = ?", (key_fingerprint,))

    def failed_key_fingerprints(self):
        """Return SERVER-ONLY identifiers of currently unhealthy usage counters."""
        with self._connect() as db:
            return tuple(row["fingerprint"] for row in db.execute(
                "SELECT fingerprint FROM key_usage WHERE error != 0 ORDER BY fingerprint"))

    def recover_interrupted_calls(self):
        """At exclusive process startup, retain interrupted requests as unknown.

        Call only after ensuring no old worker is still using this ledger. No
        request is retried and no uncertain spend is converted to zero.
        """
        with self._write() as db:
            now = self._timestamp()
            db.execute("UPDATE key_usage SET error = 1 WHERE fingerprint IN "
                       "(SELECT key_fingerprint FROM calls WHERE outcome = 'submitted')")
            result = db.execute("UPDATE calls SET outcome = 'uncertain', finished_at = ? WHERE outcome = 'submitted'",
                                (now,))
            return result.rowcount

    def recover_interrupted_key_calls(self, key_fingerprint):
        """Recover only the key whose exclusive pool lease the caller holds.

        This releases a stale submitted window after a worker crash, without
        touching active calls on other channels or retrying provider work.
        """
        key_fingerprint = _fingerprint(key_fingerprint)
        with self._write() as db:
            self._require_key(db, key_fingerprint)
            result = db.execute("UPDATE calls SET outcome = 'uncertain', finished_at = ? "
                                "WHERE key_fingerprint = ? AND outcome = 'submitted'",
                                (self._timestamp(), key_fingerprint))
            if result.rowcount:
                db.execute("UPDATE key_usage SET error = 1 WHERE fingerprint = ?", (key_fingerprint,))
            return result.rowcount

    def latest_pending_call(self, key_fingerprint):
        """Return SERVER-ONLY metadata for an isolated latest pending window.

        An active latest call suppresses recovery of older records. The caller
        should hold the key lease while obtaining a fresh usage counter and
        settling this record so no generation overlaps its reconciliation.
        """
        key_fingerprint = _fingerprint(key_fingerprint)
        with self._connect() as db:
            row = db.execute("SELECT * FROM calls WHERE key_fingerprint = ? ORDER BY rowid DESC LIMIT 1",
                             (key_fingerprint,)).fetchone()
            if row is None or row["outcome"] == "submitted" or row["billing_status"] != "pending":
                return None
            return {"call_id": row["call_id"], "outcome": row["outcome"],
                    "attribution_confirmed": bool(row["attributable"])}

    def attach_task(self, call_id, task_id):
        """Bind the provider task id once; retrying the same binding is harmless.

        Call begin_call with an empty task id (or the call id as placeholder)
        while the asynchronous submission has not returned its provider id.
        """
        call_id = _text(call_id, "call id")
        task_id = _text(task_id, "task id")
        with self._write() as db:
            row = db.execute("SELECT * FROM calls WHERE call_id = ?", (call_id,)).fetchone()
            if row is None:
                raise ValueError("Unknown call id")
            if row["task_id"] not in ("", call_id, task_id):
                raise ValueError("Call is already bound to a different provider task")
            duplicate = db.execute("SELECT 1 FROM calls WHERE task_id = ? AND call_id != ?",
                                   (task_id, call_id)).fetchone()
            if duplicate:
                raise ValueError("Provider task already belongs to another call")
            db.execute("UPDATE calls SET task_id = ? WHERE call_id = ?", (task_id, call_id))
            return self._public_call(db.execute("SELECT * FROM calls WHERE call_id = ?", (call_id,)).fetchone())

    def update_call_model(self, call_id, model):
        """Record a submitted call's resolved model without creating a charge."""
        call_id = _text(call_id, "call id")
        model = _text(model, "model")
        with self._write() as db:
            row = db.execute("SELECT * FROM calls WHERE call_id = ?", (call_id,)).fetchone()
            if row is None:
                raise ValueError("Unknown call id")
            if row["outcome"] == "submitted":
                db.execute("UPDATE calls SET model = ? WHERE call_id = ?", (model, call_id))
            return self._public_call(db.execute("SELECT * FROM calls WHERE call_id = ?", (call_id,)).fetchone())

    def find_call_by_task(self, task_id):
        """Return SERVER-ONLY recovery metadata, never a browser/UI snapshot.

        The complete fingerprint locates the original key lease, and the exact
        starting counter allows the existing call to be reconciled. It contains
        no credentials. Recovery must reuse its call_id rather than begin anew.
        """
        task_id = _text(task_id, "task id")
        with self._connect() as db:
            rows = db.execute("SELECT * FROM calls WHERE task_id = ? LIMIT 2", (task_id,)).fetchall()
            if not rows:
                return None
            if len(rows) != 1:
                raise ValueError("Task id matches multiple calls")
            return self._recovery_call(rows[0])

    def find_call_by_id(self, call_id):
        """Return SERVER-ONLY metadata to recover a receipt saved before binding.

        The caller must verify the receipt's fingerprint and existing task id
        before attaching its provider task. This lookup never creates a call.
        """
        call_id = _text(call_id, "call id")
        with self._connect() as db:
            row = db.execute("SELECT * FROM calls WHERE call_id = ?", (call_id,)).fetchone()
            return self._recovery_call(row) if row is not None else None

    @staticmethod
    def _recovery_call(row):
        return {"call_id": row["call_id"], "task_id": row["task_id"],
                "key_fingerprint": row["key_fingerprint"],
                "before_usage_usd": row["before_usd"],
                "status": row["outcome"], "billing_status": row["billing_status"],
                "attribution_confirmed": bool(row["attributable"])}

    def snapshot(self):
        """Return only safe percentages and reconciliation metadata."""
        with self._connect() as db:
            db.execute("BEGIN")
            baseline = db.execute("SELECT * FROM account_baseline").fetchone()
            if baseline is None:
                return {"percent": None, "updated_at": "", "error": True,
                        "pending_calls": 0, "active_calls": 0}
            keys = db.execute("SELECT * FROM key_usage").fetchall()
            spent = sum((Decimal(r["current_usd"]) - Decimal(r["baseline_usd"]) for r in keys), Decimal(0))
            remaining = max(Decimal(0), Decimal(baseline["balance_usd"]) - spent)
            counts = db.execute("SELECT SUM(billing_status = 'pending' AND outcome != 'submitted'), "
                                "SUM(outcome = 'submitted') FROM calls").fetchone()
            return {"percent": float(remaining),
                    "updated_at": min((r["updated_at"] for r in keys), default=baseline["created_at"]),
                    "error": any(r["error"] for r in keys),
                    "pending_calls": int(counts[0] or 0), "active_calls": int(counts[1] or 0)}

    @staticmethod
    def _public_call(row):
        refunded = Decimal(row["refund_usd"])
        cost = Decimal(row["cost_usd"]) if row["cost_usd"] is not None else None
        return {"call_id": row["call_id"], "task_id": row["task_id"], "model": row["model"],
                "resolution": row["resolution"], "channel": row["key_fingerprint"][:8],
                "cost_percent": float(max(Decimal(0), cost - refunded)) if cost is not None else None,
                "refunded": refunded > 0, "refund_percent": float(refunded),
                "status": "submitted" if row["outcome"] == "submitted" else row["billing_status"],
                "outcome": row["outcome"], "created_at": row["created_at"],
                "finished_at": row["finished_at"] or "", "settled_at": row["settled_at"] or ""}

    def list_calls(self, limit=100, *, task_id=None):
        limit = min(500, max(1, int(limit)))
        with self._connect() as db:
            if task_id is None:
                rows = db.execute("SELECT * FROM calls ORDER BY rowid DESC LIMIT ?", (limit,)).fetchall()
            else:
                rows = db.execute("SELECT * FROM calls WHERE task_id = ? ORDER BY rowid DESC LIMIT ?",
                                  (_text(task_id, "task id"), limit)).fetchall()
            return [self._public_call(row) for row in rows]
