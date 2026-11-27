"""Whole-task OmniaKey leases, shared by image/text calls and all workers.

Credentials are loaded from a private file and remain in memory. Only SHA-256
identifiers and scheduling metadata are stored in the SQLite database. Acquire
the existing request-limiter admission before entering ``hold``. This module
never submits or retries a provider request.
"""

from __future__ import annotations

from contextlib import closing, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import lru_cache
import hashlib
import json
import logging
import os
from pathlib import Path
import sqlite3
import threading
import time
import uuid


MAX_OMNIA_KEYS = 5
_current_credential = ContextVar("xiaoha_omnia_credential", default=None)
_logger = logging.getLogger(__name__)
_pool_init_lock = threading.Lock()


class OmniaKeyPoolError(RuntimeError):
    """A local credential configuration/admission failure, before submission."""


class OmniaKeyWaitTimeout(OmniaKeyPoolError):
    """No credential became available within the local waiting limit."""


def credential_fingerprint(api_key: str) -> str:
    return hashlib.sha256(str(api_key).strip().encode("utf-8")).hexdigest()


def _task_fingerprint(task_id: str) -> str:
    return hashlib.sha256(str(task_id).strip().encode("utf-8")).hexdigest()


def _validated_keys(values):
    if not isinstance(values, (list, tuple)):
        raise OmniaKeyPoolError("OmniaKey 密钥配置格式无效，请联系管理员检查。")
    keys = []
    for value in values:
        if not isinstance(value, str):
            raise OmniaKeyPoolError("OmniaKey 密钥配置格式无效，请联系管理员检查。")
        key = value.strip()
        if key and key not in keys:
            keys.append(key)
    return tuple(keys[:MAX_OMNIA_KEYS])


def load_omnia_api_keys(primary: str = "") -> tuple[str, ...]:
    """Load at most five distinct keys, keeping the original key first.

    An explicit file (or the default private file when it exists) takes
    precedence over plural environment configuration. Malformed configured
    files fail closed instead of silently routing paid work with stale keys.
    No values or parser exception details are included in errors.
    """
    explicit_path = os.environ.get("OMNIAKEY_API_KEYS_FILE", "").strip()
    path = Path(explicit_path) if explicit_path else (
        Path(__file__).parent / "history" / ".credentials" / "omnia_api_keys.json"
    )
    values = []
    if explicit_path or path.exists():
        try:
            values = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            raise OmniaKeyPoolError("OmniaKey 密钥配置无法读取，请联系管理员检查。") from None
    elif os.environ.get("OMNIAKEY_API_KEYS", "").strip():
        try:
            values = json.loads(os.environ["OMNIAKEY_API_KEYS"])
        except (TypeError, ValueError):
            raise OmniaKeyPoolError("OmniaKey 密钥配置格式无效，请联系管理员检查。") from None
    configured = _validated_keys(values)
    primary = str(primary or os.environ.get("OMNIAKEY_API_KEY", "")).strip()
    return _validated_keys(([primary] if primary else []) + list(configured))


@dataclass(frozen=True)
class OmniaCredential:
    api_key: str = field(repr=False)
    fingerprint: str
    _pool: object = field(repr=False, compare=False)
    _lease_token: str = field(repr=False, compare=False)

    def bind_task(self, task_id: str) -> None:
        """Bind a returned provider task ID before polling or writing receipts."""
        self._pool.bind_task(self._lease_token, self.fingerprint, task_id)


def current_omnia_credential() -> OmniaCredential | None:
    return _current_credential.get()


def current_omnia_key_fingerprint() -> str:
    credential = current_omnia_credential()
    return credential.fingerprint if credential is not None else ""


def bind_current_omnia_task(task_id: str) -> None:
    credential = current_omnia_credential()
    if credential is None:
        raise OmniaKeyPoolError("OmniaKey 任务尚未分配密钥，无法绑定回执。")
    credential.bind_task(task_id)


class OmniaKeyPool:
    def __init__(self, db_path=None, *, lease_seconds=30.0,
                 heartbeat_interval=None, poll_interval=0.2, queue_timeout=900.0,
                 uncertain_cooldown=60.0):
        self.db_path = Path(db_path or os.environ.get("XIAOHA_OMNIA_KEY_DB") or
                            Path(__file__).parent / "history" / "omnia_keys.sqlite3")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.lease_seconds = max(0.15, float(lease_seconds))
        self.heartbeat_interval = min(
            max(0.025, float(heartbeat_interval or self.lease_seconds / 3)),
            self.lease_seconds / 3,
        )
        self.poll_interval = max(0.005, float(poll_interval))
        self.queue_timeout = max(0.01, float(queue_timeout))
        self.uncertain_cooldown = max(0.0, float(uncertain_cooldown))
        with closing(self._connect()) as connection:
            deadline = time.monotonic() + 10.0
            while True:
                try:
                    connection.execute("PRAGMA journal_mode=WAL")
                    break
                except sqlite3.OperationalError as error:
                    if not any(word in str(error).lower() for word in ("locked", "busy")):
                        raise
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise
                    time.sleep(min(0.025, remaining))
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS omnia_key_usage (
                    fingerprint TEXT PRIMARY KEY,
                    last_sequence INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS omnia_key_leases (
                    fingerprint TEXT PRIMARY KEY,
                    token TEXT NOT NULL UNIQUE,
                    task_hash TEXT NOT NULL DEFAULT '',
                    expires_at REAL NOT NULL,
                    retained INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS omnia_task_keys (
                    task_hash TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
            """)

    def _connect(self):
        connection = sqlite3.connect(str(self.db_path), timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    @contextmanager
    def _transaction(self):
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _cleanup(connection, now):
        connection.execute("DELETE FROM omnia_key_leases WHERE expires_at <= ?", (now,))

    def _try_acquire(self, token, fingerprints, preferred, task_hash):
        with self._transaction() as connection:
            now = time.time()
            self._cleanup(connection, now)
            target = preferred
            if task_hash:
                binding = connection.execute(
                    "SELECT fingerprint FROM omnia_task_keys WHERE task_hash = ?", (task_hash,)
                ).fetchone()
                if binding:
                    if target and target != binding["fingerprint"]:
                        raise OmniaKeyPoolError("OmniaKey 原任务的密钥不匹配，未重新提交任务。")
                    target = binding["fingerprint"]
                elif not target:
                    raise OmniaKeyPoolError("OmniaKey 原任务的密钥记录不存在，请联系管理员恢复回执。")
            if target and target not in fingerprints:
                raise OmniaKeyPoolError("OmniaKey 原任务使用的密钥已移除，未重新提交任务。")
            # Only this exact provider task can reclaim its uncertain lease.
            if task_hash and target:
                connection.execute(
                    "DELETE FROM omnia_key_leases WHERE fingerprint = ? AND task_hash = ? "
                    "AND retained = 1", (target, task_hash),
                )
            for fingerprint in fingerprints:
                connection.execute(
                    "INSERT OR IGNORE INTO omnia_key_usage(fingerprint) VALUES (?)", (fingerprint,)
                )
            busy = {row[0] for row in connection.execute("SELECT fingerprint FROM omnia_key_leases")}
            choices = [target] if target else list(fingerprints)
            available = [fingerprint for fingerprint in choices if fingerprint not in busy]
            if not available:
                return None
            usage = {row[0]: row[1] for row in connection.execute(
                "SELECT fingerprint, last_sequence FROM omnia_key_usage"
            )}
            selected = min(available, key=lambda fingerprint: (usage[fingerprint], fingerprints.index(fingerprint)))
            sequence = max(usage.values(), default=0) + 1
            connection.execute(
                "UPDATE omnia_key_usage SET last_sequence = ? WHERE fingerprint = ?", (sequence, selected)
            )
            connection.execute(
                "INSERT INTO omnia_key_leases(fingerprint, token, task_hash, expires_at) VALUES (?, ?, ?, ?)",
                (selected, token, task_hash, now + self.lease_seconds),
            )
            if task_hash:
                connection.execute(
                    "INSERT OR IGNORE INTO omnia_task_keys(task_hash, fingerprint, created_at) VALUES (?, ?, ?)",
                    (task_hash, selected, now),
                )
            return selected

    def bind_task(self, token, fingerprint, task_id):
        if not str(task_id or "").strip():
            raise OmniaKeyPoolError("OmniaKey 任务编号为空，无法绑定回执。")
        task_hash = _task_fingerprint(task_id)
        with self._transaction() as connection:
            lease = connection.execute(
                "SELECT task_hash FROM omnia_key_leases WHERE fingerprint = ? AND token = ? AND retained = 0",
                (fingerprint, token),
            ).fetchone()
            if lease is None:
                raise OmniaKeyPoolError("OmniaKey 密钥租约已失效，请继续查询原任务，勿重新提交。")
            if lease["task_hash"] and lease["task_hash"] != task_hash:
                raise OmniaKeyPoolError("OmniaKey 租约已绑定其他任务，未重新提交任务。")
            binding = connection.execute(
                "SELECT fingerprint FROM omnia_task_keys WHERE task_hash = ?", (task_hash,)
            ).fetchone()
            if binding and binding["fingerprint"] != fingerprint:
                raise OmniaKeyPoolError("OmniaKey 原任务的密钥不匹配，未重新提交任务。")
            connection.execute(
                "INSERT OR IGNORE INTO omnia_task_keys(task_hash, fingerprint, created_at) VALUES (?, ?, ?)",
                (task_hash, fingerprint, time.time()),
            )
            connection.execute("UPDATE omnia_key_leases SET task_hash = ? WHERE token = ?", (task_hash, token))

    def task_fingerprint(self, task_id: str) -> str:
        """Return only the credential fingerprint for a persisted provider task."""
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT fingerprint FROM omnia_task_keys WHERE task_hash = ?", (_task_fingerprint(task_id),)
            ).fetchone()
            return row[0] if row else ""

    def _heartbeat(self, token, stop):
        while not stop.wait(self.heartbeat_interval):
            try:
                with closing(self._connect()) as connection:
                    connection.execute(
                        "UPDATE omnia_key_leases SET expires_at = ? WHERE token = ? AND retained = 0",
                        (time.time() + self.lease_seconds, token),
                    )
            except sqlite3.Error:
                # Keep exception text and credentials out of logs.
                continue

    @staticmethod
    def _outcome_unknown(error):
        return error is not None and (
            type(error).__name__ in {"OmniaImageOutcomeUnknown", "OmniaTextOutcomeUnknown"} or
            any(marker in str(error) for marker in ("未自动重新提交", "provider_submit_uncertain"))
        )

    def _release(self, token, error):
        with self._transaction() as connection:
            if self._outcome_unknown(error) and self.uncertain_cooldown:
                connection.execute(
                    "UPDATE omnia_key_leases SET retained = 1, expires_at = ? WHERE token = ?",
                    (time.time() + self.uncertain_cooldown, token),
                )
            else:
                connection.execute("DELETE FROM omnia_key_leases WHERE token = ?", (token,))

    @contextmanager
    def hold(self, keys, *, preferred_fingerprint=None, task_id=None, on_wait=None, _nonblocking=False):
        """Lease one key for the complete task, including polling/downloads.

        Callback receives ``True`` while waiting and ``False`` on admission.
        ``task_id`` resumes a known provider task and never rotates credentials.
        A supplied preferred fingerprint permits recovery of a legacy receipt.
        Nested use reuses the current lease, subject to matching task/key checks.
        """
        keys = _validated_keys(keys)
        if not keys:
            raise OmniaKeyPoolError("OmniaKey 尚未配置可用密钥，请联系管理员检查。")
        by_fingerprint = {credential_fingerprint(key): key for key in keys}
        preferred = str(preferred_fingerprint or "").strip()
        task_hash = _task_fingerprint(task_id) if str(task_id or "").strip() else ""
        current = current_omnia_credential()
        if current is not None:
            if current.fingerprint not in by_fingerprint or (preferred and preferred != current.fingerprint):
                raise OmniaKeyPoolError("OmniaKey 当前任务的密钥不匹配，未重新提交任务。")
            if task_hash:
                current.bind_task(task_id)
            yield current
            return
        token = uuid.uuid4().hex
        selected = None
        error = None
        context_token = None
        stop = threading.Event()
        heartbeat = None
        started = time.monotonic()
        last_notified = float("-inf")
        try:
            while selected is None:
                selected = self._try_acquire(token, tuple(by_fingerprint), preferred, task_hash)
                now = time.monotonic()
                if on_wait and (selected is not None or now - last_notified >= 1):
                    try:
                        on_wait(selected is None)
                    except Exception:
                        pass
                    last_notified = now
                if selected is not None:
                    break
                if _nonblocking:
                    yield None
                    return
                remaining = self.queue_timeout - (now - started)
                if remaining <= 0:
                    raise OmniaKeyWaitTimeout("小哈密钥排队等待超时，本次请求尚未提交，请稍后再试。")
                stop.wait(min(self.poll_interval, remaining))
            credential = OmniaCredential(by_fingerprint[selected], selected, self, token)
            context_token = _current_credential.set(credential)
            heartbeat = threading.Thread(target=self._heartbeat, args=(token, stop), daemon=True)
            heartbeat.start()
            yield credential
        except BaseException as exc:
            error = exc
            raise
        finally:
            if context_token is not None:
                _current_credential.reset(context_token)
            stop.set()
            if heartbeat is not None:
                heartbeat.join(timeout=11)
            if selected is not None:
                try:
                    self._release(token, error)
                except sqlite3.Error:
                    _logger.warning("OmniaKey lease cleanup failed; the lease will expire.")

    def try_hold_nonblocking(self, keys, *, preferred_fingerprint):
        """Return a context yielding the requested credential, or None if busy.

        Read-only balance refreshes can reconcile a pending task only while
        holding this exclusive lease. Busy/uncertain keys are not reclaimed.
        """
        return self.hold(keys, preferred_fingerprint=preferred_fingerprint, _nonblocking=True)

    def snapshot(self):
        with self._transaction() as connection:
            self._cleanup(connection, time.time())
            rows = connection.execute("SELECT retained, COUNT(*) FROM omnia_key_leases GROUP BY retained")
            counts = dict(rows)
            return {"active": counts.get(0, 0), "retained": counts.get(1, 0)}


@lru_cache(maxsize=4)
def _cached_pool(path):
    return OmniaKeyPool(path)


def get_omnia_key_pool() -> OmniaKeyPool:
    path = str(Path(os.environ.get("XIAOHA_OMNIA_KEY_DB") or
                    Path(__file__).parent / "history" / "omnia_keys.sqlite3").resolve())
    # functools.lru_cache can invoke its function concurrently on cache misses.
    # Serialize that first initialization within a worker; WAL retry above also
    # handles independent processes starting against the same fresh database.
    with _pool_init_lock:
        return _cached_pool(path)
