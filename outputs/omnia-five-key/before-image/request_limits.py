"""Cross-process admission control for XiaoHa's outbound model requests.

Only scheduling metadata is persisted; credentials, prompts and assets never enter
this database.  Hold a slot for a whole model task, including polling/downloads.
"""

from __future__ import annotations

from contextlib import closing, contextmanager
from contextvars import ContextVar
from functools import lru_cache, wraps
import logging
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
import uuid


DEFAULT_GROUP_LIMITS = {
    "omnia_image": 1,
    "omnia_text": 2,
    "ark": 2,
    "jimeng": 1,
    "cutout": 2,
    "download": 6,
}
_wait_callback = ContextVar("xiaoha_request_wait_callback", default=None)
_admitted_depth = ContextVar("xiaoha_request_admitted_depth", default=0)
_logger = logging.getLogger(__name__)


class RequestQueueFull(RuntimeError):
    """The request was rejected locally and has not reached a provider."""


class RequestQueueTimeout(RequestQueueFull):
    """The request timed out locally and has not reached a provider."""


def _env_number(name, default, low, high, cast=int):
    try:
        return max(low, min(high, cast(os.environ.get(name, default))))
    except (TypeError, ValueError):
        return default


class RequestLimiter:
    def __init__(
        self,
        db_path=None,
        *,
        group_limits=None,
        model_limit=None,
        provider_limit=None,
        max_waiting=None,
        queue_timeout=None,
        lease_seconds=30.0,
        heartbeat_interval=None,
        poll_interval=0.2,
        uncertain_cooldown=60.0,
        rate_limit_cooldown=15.0,
    ):
        self.db_path = Path(db_path or os.environ.get("XIAOHA_REQUEST_DB") or
                            Path(__file__).parent / "history" / "request_limits.sqlite3")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.group_limits = {
            group: _env_number(f"XIAOHA_{group.upper()}_CONCURRENCY", limit, 1, 16)
            for group, limit in DEFAULT_GROUP_LIMITS.items()
        }
        if group_limits:
            self.group_limits.update({key: max(1, min(16, int(value)))
                                      for key, value in group_limits.items()})
        self.model_limit = (int(model_limit) if model_limit is not None else
                            _env_number("XIAOHA_MODEL_CONCURRENCY", 6, 1, 64))
        self.provider_limit = (
            max(1, int(provider_limit)) if provider_limit is not None else
            _env_number("XIAOHA_OMNIA_CONCURRENCY", 2, 1, 16)
        )
        self.max_waiting = (int(max_waiting) if max_waiting is not None else
                            _env_number("XIAOHA_MAX_WAITING", 64, 1, 4096))
        self.queue_timeout = (float(queue_timeout) if queue_timeout is not None else
                              _env_number("XIAOHA_QUEUE_TIMEOUT", 900, 1, 7200, float))
        self.lease_seconds = max(0.15, float(lease_seconds))
        self.heartbeat_interval = min(
            max(0.025, float(heartbeat_interval or self.lease_seconds / 3)),
            self.lease_seconds / 3,
        )
        self.poll_interval = max(0.005, float(poll_interval))
        self.uncertain_cooldown = max(0, float(uncertain_cooldown))
        self.rate_limit_cooldown = max(0, float(rate_limit_cooldown))
        with closing(self._connect()) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS request_tickets (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    token TEXT NOT NULL UNIQUE,
                    group_name TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('waiting', 'active')),
                    expires_at REAL NOT NULL,
                    retained INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS request_settings (
                    key TEXT PRIMARY KEY, value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS request_cooldowns (
                    resource TEXT PRIMARY KEY, until_at REAL NOT NULL
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
        connection.execute("DELETE FROM request_tickets WHERE expires_at <= ?", (now,))
        connection.execute("DELETE FROM request_cooldowns WHERE until_at <= ?", (now,))

    @staticmethod
    def _draining(connection):
        row = connection.execute(
            "SELECT value FROM request_settings WHERE key = 'draining'"
        ).fetchone()
        return bool(row and row["value"] == "1")

    def ensure_accepting(self):
        with closing(self._connect()) as connection:
            if self._draining(connection):
                raise RequestQueueFull("小哈正在维护，暂不接收新请求；本次请求尚未提交，请稍后再试。")

    def drain(self, enabled=True):
        """Reject new tickets; existing queued and running tickets keep working."""
        with self._transaction() as connection:
            connection.execute(
                "INSERT INTO request_settings(key, value) VALUES ('draining', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("1" if enabled else "0",),
            )

    def _resources(self, group):
        resources = {f"group:{group}": self.group_limits[group]}
        if group != "download":
            resources["model"] = self.model_limit
        if group in ("omnia_image", "omnia_text"):
            resources["provider:omnia"] = self.provider_limit
        return resources

    def _register(self, group):
        token = uuid.uuid4().hex
        with self._transaction() as connection:
            now = time.time()
            self._cleanup(connection, now)
            if self._draining(connection) and _admitted_depth.get() == 0:
                raise RequestQueueFull("小哈正在维护，暂不接收新请求；本次请求尚未提交，请稍后再试。")
            waiting = connection.execute(
                "SELECT COUNT(*) FROM request_tickets WHERE state = 'waiting'"
            ).fetchone()[0]
            if waiting >= self.max_waiting:
                raise RequestQueueFull("小哈等待队列已满，本次请求尚未提交，请稍后再试。")
            connection.execute(
                "INSERT INTO request_tickets(token, group_name, state, expires_at) "
                "VALUES (?, ?, 'waiting', ?)", (token, group, now + self.lease_seconds)
            )
        return token

    def _try_acquire(self, token, group):
        with self._transaction() as connection:
            now = time.time()
            self._cleanup(connection, now)
            rows = connection.execute("SELECT * FROM request_tickets ORDER BY sequence").fetchall()
            own = next((row for row in rows if row["token"] == token), None)
            if own is None:
                raise RequestQueueTimeout("小哈排队租约已过期，本次请求尚未提交，请重新操作。")
            active = {}
            for row in rows:
                if row["state"] == "active":
                    for resource in self._resources(row["group_name"]):
                        active[resource] = active.get(resource, 0) + 1
            cooldowns = {row[0] for row in connection.execute(
                "SELECT resource FROM request_cooldowns WHERE until_at > ?", (now,)
            )}

            def available(candidate_group):
                return all(resource not in cooldowns and active.get(resource, 0) < limit
                           for resource, limit in self._resources(candidate_group).items())

            resources = self._resources(group)
            earlier = [row for row in rows if row["state"] == "waiting" and
                       row["sequence"] < own["sequence"] and
                       resources.keys() & self._resources(row["group_name"]).keys()]
            # Work-conserving FIFO: a blocked provider does not stall other ones.
            if available(group) and not any(available(row["group_name"]) for row in earlier):
                connection.execute(
                    "UPDATE request_tickets SET state = 'active', expires_at = ? WHERE token = ?",
                    (now + self.lease_seconds, token),
                )
                return True, 0
            connection.execute("UPDATE request_tickets SET expires_at = ? WHERE token = ?",
                               (now + self.lease_seconds, token))
            return False, len(earlier) + 1

    def _heartbeat(self, token, stop):
        last_warning = float("-inf")
        while not stop.wait(self.heartbeat_interval):
            try:
                with closing(self._connect()) as connection:
                    connection.execute(
                        "UPDATE request_tickets SET expires_at = ? WHERE token = ? AND retained = 0",
                        (time.time() + self.lease_seconds, token),
                    )
            except sqlite3.Error as exc:
                # Transient lock contention is retried by the next heartbeat.
                now = time.monotonic()
                if now - last_warning >= 30:
                    _logger.warning(
                        "XiaoHa request lease heartbeat failed; retrying (%s)",
                        type(exc).__name__, exc_info=True,
                    )
                    last_warning = now
                continue

    @staticmethod
    def _outcome_unknown(error):
        return error is not None and (
            type(error).__name__ == "OmniaImageOutcomeUnknown" or
            any(marker in str(error) for marker in ("未自动重新提交", "provider_submit_uncertain"))
        )

    @staticmethod
    def _rate_limited(error):
        if error is None:
            return False
        response = getattr(error, "response", None)
        return (getattr(response, "status_code", None) == 429 or
                getattr(error, "status_code", None) == 429 or
                bool(re.search(r"(?<!\d)429(?!\d)|rate.limit|too many requests", str(error), re.I)))

    @staticmethod
    def _cooldown_resource(group):
        return "provider:omnia" if group.startswith("omnia_") else f"group:{group}"

    def _set_cooldown(self, connection, group, seconds):
        connection.execute(
            "INSERT INTO request_cooldowns(resource, until_at) VALUES (?, ?) "
            "ON CONFLICT(resource) DO UPDATE SET until_at = MAX(until_at, excluded.until_at)",
            (self._cooldown_resource(group), time.time() + seconds),
        )

    def cooldown(self, group, seconds=None):
        """Delay new admissions for a provider after an intermediate HTTP 429.

        Already admitted tasks retain their slot and should apply their own retry
        delay. Omnia image/text share this cooldown across processes.
        """
        if group not in self.group_limits:
            raise ValueError(f"Unknown XiaoHa request group: {group}")
        duration = self.rate_limit_cooldown if seconds is None else max(0, float(seconds))
        with self._transaction() as connection:
            self._set_cooldown(connection, group, duration)

    def _release(self, token, group, error, acquired):
        with self._transaction() as connection:
            now = time.time()
            if acquired and self._rate_limited(error):
                self._set_cooldown(connection, group, self.rate_limit_cooldown)
            if acquired and self._outcome_unknown(error) and self.uncertain_cooldown:
                connection.execute(
                    "UPDATE request_tickets SET expires_at = ?, retained = 1 WHERE token = ?",
                    (now + self.uncertain_cooldown, token),
                )
            else:
                connection.execute("DELETE FROM request_tickets WHERE token = ?", (token,))

    @contextmanager
    def slot(self, group, on_wait=None):
        """Acquire one whole-task slot; callback(group, 0) means admission.

        While queued, callback(group, ahead) receives a positive queue position,
        at most once a second. No provider request has happened at this point.
        """
        if group not in self.group_limits:
            raise ValueError(f"Unknown XiaoHa request group: {group}")
        token = self._register(group)
        acquired = False
        error = None
        admitted_context = None
        stop = threading.Event()
        heartbeat = threading.Thread(target=self._heartbeat, args=(token, stop), daemon=True)
        heartbeat.start()
        started = time.monotonic()
        last_notified = float("-inf")
        try:
            while True:
                acquired, ahead = self._try_acquire(token, group)
                now = time.monotonic()
                if on_wait and (acquired or now - last_notified >= 1):
                    try:
                        on_wait(group, ahead)
                    except Exception:
                        pass  # Rendering/progress hooks must not fail a paid task.
                    last_notified = now
                if acquired:
                    break
                remaining = self.queue_timeout - (now - started)
                if remaining <= 0:
                    raise RequestQueueTimeout("小哈排队等待超时，本次请求尚未提交，请稍后再试。")
                stop.wait(min(self.poll_interval, remaining))
            admitted_context = _admitted_depth.set(_admitted_depth.get() + 1)
            yield
        except BaseException as exc:
            error = exc
            raise
        finally:
            if admitted_context is not None:
                _admitted_depth.reset(admitted_context)
            stop.set()
            heartbeat.join(timeout=11)
            try:
                self._release(token, group, error, acquired)
            except Exception as cleanup_error:
                # A finished paid request must keep its result even if the
                # scheduling database becomes unavailable during cleanup. With
                # its heartbeat stopped, the remaining lease expires naturally.
                _logger.warning(
                    "XiaoHa request slot cleanup failed; lease will expire "
                    "(group=%s, error=%s)", group, type(cleanup_error).__name__,
                    exc_info=True,
                )

    def snapshot(self):
        with self._transaction() as connection:
            self._cleanup(connection, time.time())
            groups = {group: {"active": 0, "waiting": 0, "limit": limit}
                      for group, limit in self.group_limits.items()}
            active = waiting = retained = 0
            for row in connection.execute(
                "SELECT group_name, state, retained, COUNT(*) AS count "
                "FROM request_tickets GROUP BY group_name, state, retained"
            ):
                groups.setdefault(row["group_name"], {"active": 0, "waiting": 0, "limit": 0})[
                    row["state"]] += row["count"]
                if row["state"] == "active":
                    active += row["count"]
                    retained += row["count"] if row["retained"] else 0
                else:
                    waiting += row["count"]
            return {
                "active": active, "waiting": waiting, "retained": retained,
                "groups": groups, "draining": self._draining(connection),
                "model_limit": self.model_limit, "omnia_limit": self.provider_limit,
                "max_waiting": self.max_waiting,
                "cooldowns": {row[0]: row[1] for row in connection.execute(
                    "SELECT resource, until_at FROM request_cooldowns")},
            }


@lru_cache(maxsize=4)
def _cached_limiter(path):
    return RequestLimiter(path)


def get_request_limiter():
    path = str(Path(os.environ.get("XIAOHA_REQUEST_DB") or
                    Path(__file__).parent / "history" / "request_limits.sqlite3").resolve())
    return _cached_limiter(path)


def ensure_accepting():
    get_request_limiter().ensure_accepting()


@contextmanager
def admitted_job(existing=False):
    """Keep every stage of one accepted job eligible during maintenance.

    ``existing=True`` is only for jobs already admitted before entering a local
    worker queue. New HTTP requests use the default, which checks maintenance
    before admitting the job. Each provider operation still needs its own slot.
    """
    if not existing:
        ensure_accepting()
    token = _admitted_depth.set(_admitted_depth.get() + 1)
    try:
        yield
    finally:
        _admitted_depth.reset(token)


@contextmanager
def request_wait_callback(callback):
    token = _wait_callback.set(callback)
    try:
        yield
    finally:
        _wait_callback.reset(token)


def limited_request(group):
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            with get_request_limiter().slot(group, on_wait=_wait_callback.get()):
                return function(*args, **kwargs)
        return wrapped
    return decorate
