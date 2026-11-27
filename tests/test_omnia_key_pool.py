import multiprocessing
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from Department.视觉设计部.xiaoha import omnia_key_pool as pool_module


TEST_KEYS = tuple(f"test-only-key-{index}" for index in range(5))


def _process_lease(path, start, ready, active, maximum, lock, fingerprints, failures):
    try:
        pool = pool_module.OmniaKeyPool(path, poll_interval=0.01)
        ready.put(True)
        start.wait(15)
        with pool.hold(TEST_KEYS) as credential:
            with lock:
                if fingerprints.get(credential.fingerprint, 0):
                    failures.put("duplicate concurrent key")
                fingerprints[credential.fingerprint] = 1
                active.value += 1
                maximum.value = max(maximum.value, active.value)
            time.sleep(0.2)
            with lock:
                fingerprints[credential.fingerprint] = 0
                active.value -= 1
    except Exception as error:
        failures.put(type(error).__name__)


def _crashed_lease(path, ready):
    pool = pool_module.OmniaKeyPool(path, lease_seconds=0.25, poll_interval=0.01)
    with pool.hold(TEST_KEYS[:1]):
        ready.set()
        os._exit(0)


class OmniaImageOutcomeUnknown(RuntimeError):
    pass


class OmniaKeyConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "keys.json"

    def test_private_file_and_original_key_are_deduplicated_with_original_first(self):
        self.path.write_text('[" extra ", "original", "extra", "third"]', encoding="utf-8")
        with patch.dict(os.environ, {"OMNIAKEY_API_KEYS_FILE": str(self.path),
                                     "OMNIAKEY_API_KEYS": '["ignored"]'}):
            self.assertEqual(pool_module.load_omnia_api_keys("original"), ("original", "extra", "third"))

    def test_caps_at_five_keys(self):
        self.path.write_text('["1", "2", "3", "4", "5", "6"]', encoding="utf-8")
        with patch.dict(os.environ, {"OMNIAKEY_API_KEYS_FILE": str(self.path)}):
            self.assertEqual(pool_module.load_omnia_api_keys("old"), ("old", "1", "2", "3", "4"))

    def test_invalid_file_does_not_leak_or_silently_fallback(self):
        self.path.write_text('private-value-invalid-json', encoding="utf-8")
        with patch.dict(os.environ, {"OMNIAKEY_API_KEYS_FILE": str(self.path),
                                     "OMNIAKEY_API_KEYS": '["fallback"]'}):
            with self.assertRaises(pool_module.OmniaKeyPoolError) as raised:
                pool_module.load_omnia_api_keys("old")
        self.assertNotIn("private-value", str(raised.exception))

    def test_explicit_missing_file_fails_closed(self):
        with patch.dict(os.environ, {"OMNIAKEY_API_KEYS_FILE": str(self.path)}):
            with self.assertRaises(pool_module.OmniaKeyPoolError):
                pool_module.load_omnia_api_keys("old")

    def test_plural_environment_and_single_key_fallback(self):
        with patch.dict(os.environ, {"OMNIAKEY_API_KEYS_FILE": "", "OMNIAKEY_API_KEYS": '["second"]',
                                     "OMNIAKEY_API_KEY": "first"}), patch.object(Path, "exists", return_value=False):
            self.assertEqual(pool_module.load_omnia_api_keys(), ("first", "second"))
        with patch.dict(os.environ, {"OMNIAKEY_API_KEYS_FILE": "", "OMNIAKEY_API_KEYS": "",
                                     "OMNIAKEY_API_KEY": "first"}), patch.object(Path, "exists", return_value=False):
            self.assertEqual(pool_module.load_omnia_api_keys(), ("first",))

    def test_invalid_list_member_rejected(self):
        self.path.write_text('["first", 123]', encoding="utf-8")
        with patch.dict(os.environ, {"OMNIAKEY_API_KEYS_FILE": str(self.path)}):
            with self.assertRaises(pool_module.OmniaKeyPoolError):
                pool_module.load_omnia_api_keys()


class OmniaKeyLeaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "keys.sqlite3"
        self.pool = self.make_pool()

    def make_pool(self, **kwargs):
        return pool_module.OmniaKeyPool(self.path, poll_interval=0.01, **kwargs)

    def test_round_robin_and_context_cleanup(self):
        actual = []
        for _ in range(7):
            with self.pool.hold(TEST_KEYS) as credential:
                actual.append(credential.api_key)
                self.assertIs(pool_module.current_omnia_credential(), credential)
                self.assertEqual(pool_module.current_omnia_key_fingerprint(), credential.fingerprint)
                self.assertNotIn(credential.api_key, repr(credential))
            self.assertIsNone(pool_module.current_omnia_credential())
        self.assertEqual(actual, list(TEST_KEYS) + list(TEST_KEYS[:2]))
        self.assertEqual(self.pool.snapshot(), {"active": 0, "retained": 0})

    def test_five_processes_concurrently_but_each_key_is_exclusive(self):
        ctx = multiprocessing.get_context("spawn")
        with ctx.Manager() as manager:
            active, maximum = ctx.Value("i", 0), ctx.Value("i", 0)
            lock, start, ready, failures = ctx.Lock(), ctx.Event(), ctx.Queue(), ctx.Queue()
            fingerprints = manager.dict()
            processes = [ctx.Process(target=_process_lease, args=(str(self.path), start, ready,
                         active, maximum, lock, fingerprints, failures)) for _ in range(8)]
            try:
                for process in processes:
                    process.start()
                for _ in processes:
                    self.assertTrue(ready.get(timeout=15))
                start.set()
                for process in processes:
                    process.join(15)
                    self.assertEqual(process.exitcode, 0)
                self.assertEqual(maximum.value, 5)
                self.assertTrue(failures.empty())
                self.assertEqual(self.pool.snapshot()["active"], 0)
            finally:
                for process in processes:
                    if process.is_alive():
                        process.terminate()
                        process.join()

    def test_nested_hold_reuses_key_without_consuming_another_slot(self):
        with self.pool.hold(TEST_KEYS) as first:
            with self.pool.hold(TEST_KEYS) as second:
                self.assertIs(first, second)
                self.assertEqual(self.pool.snapshot()["active"], 1)
            self.assertIs(pool_module.current_omnia_credential(), first)

    def test_heartbeat_keeps_key_busy_for_long_task(self):
        pool = self.make_pool(lease_seconds=0.15, heartbeat_interval=0.025)
        ready, done, errors = threading.Event(), threading.Event(), []

        def holding():
            try:
                with pool.hold(TEST_KEYS[:1]):
                    ready.set()
                    done.wait(3)
            except BaseException as error:
                errors.append(error)

        thread = threading.Thread(target=holding)
        thread.start()
        try:
            self.assertTrue(ready.wait(3))
            time.sleep(0.35)
            with self.assertRaises(pool_module.OmniaKeyWaitTimeout):
                with self.make_pool(queue_timeout=0.1).hold(TEST_KEYS[:1]):
                    self.fail("Leased a key whose heartbeat is active")
        finally:
            done.set()
            thread.join(3)
        self.assertEqual(errors, [])

    def test_crashed_process_lease_expires(self):
        ctx = multiprocessing.get_context("spawn")
        ready = ctx.Event()
        process = ctx.Process(target=_crashed_lease, args=(str(self.path), ready))
        try:
            process.start()
            self.assertTrue(ready.wait(10))
            process.join(10)
            self.assertEqual(process.exitcode, 0)
            with self.make_pool(queue_timeout=2).hold(TEST_KEYS[:1]) as credential:
                self.assertEqual(credential.api_key, TEST_KEYS[0])
        finally:
            if process.is_alive():
                process.terminate()
                process.join()

    def test_unknown_outcome_retains_only_its_key_and_resumes_same_task(self):
        first = ""
        with self.assertRaises(OmniaImageOutcomeUnknown):
            with self.pool.hold(TEST_KEYS) as credential:
                first = credential.fingerprint
                pool_module.bind_current_omnia_task("provider-task-one")
                raise OmniaImageOutcomeUnknown("uncertain")
        self.assertEqual(self.pool.snapshot(), {"active": 0, "retained": 1})
        with self.pool.hold(TEST_KEYS) as credential:
            self.assertNotEqual(credential.fingerprint, first)
        with self.make_pool(queue_timeout=0.2).hold(TEST_KEYS, task_id="provider-task-one") as resumed:
            self.assertEqual(resumed.fingerprint, first)
            self.assertEqual(self.pool.snapshot(), {"active": 1, "retained": 0})
        self.assertEqual(self.pool.snapshot(), {"active": 0, "retained": 0})

    def test_unknown_outcome_without_task_does_not_retry_or_switch_key(self):
        pool = self.make_pool(uncertain_cooldown=0.3)
        with self.assertRaises(OmniaImageOutcomeUnknown):
            with pool.hold(TEST_KEYS[:1]):
                raise OmniaImageOutcomeUnknown("uncertain")
        with self.assertRaises(pool_module.OmniaKeyWaitTimeout):
            with self.make_pool(queue_timeout=0.1).hold(TEST_KEYS[:1]):
                self.fail("Retained key should remain busy")
        with self.make_pool(queue_timeout=1).hold(TEST_KEYS[:1]):
            pass

    def test_successful_task_binding_survives_pool_instances_and_configuration_order(self):
        with self.pool.hold(TEST_KEYS) as credential:
            original = credential.fingerprint
            credential.bind_task("task-stable")
        other = self.make_pool()
        self.assertEqual(other.task_fingerprint("task-stable"), original)
        with other.hold(tuple(reversed(TEST_KEYS)), task_id="task-stable") as resumed:
            self.assertEqual(resumed.fingerprint, original)

    def test_unknown_or_removed_task_key_never_falls_back_to_another_key(self):
        with self.assertRaises(pool_module.OmniaKeyPoolError):
            with self.pool.hold(TEST_KEYS, task_id="not-found"):
                self.fail("Unknown task must not rotate")
        with self.pool.hold(TEST_KEYS) as credential:
            credential.bind_task("known")
        with self.assertRaises(pool_module.OmniaKeyPoolError):
            with self.pool.hold(TEST_KEYS[1:], task_id="known"):
                self.fail("Missing original key must not rotate")

    def test_legacy_task_with_explicit_key_can_be_bound(self):
        selected = pool_module.credential_fingerprint(TEST_KEYS[3])
        with self.pool.hold(TEST_KEYS, preferred_fingerprint=selected, task_id="legacy") as credential:
            self.assertEqual(credential.api_key, TEST_KEYS[3])
        self.assertEqual(self.pool.task_fingerprint("legacy"), selected)

    def test_task_binding_cannot_be_overwritten(self):
        first, second = map(pool_module.credential_fingerprint, TEST_KEYS[:2])
        with self.pool.hold(TEST_KEYS, preferred_fingerprint=first) as credential:
            credential.bind_task("same-task")
        with self.assertRaises(pool_module.OmniaKeyPoolError):
            with self.pool.hold(TEST_KEYS, task_id="same-task", preferred_fingerprint=second):
                self.fail("Must not change the task credential")
        with self.pool.hold(TEST_KEYS, preferred_fingerprint=second) as credential:
            with self.assertRaises(pool_module.OmniaKeyPoolError):
                credential.bind_task("same-task")

    def test_database_contains_no_keys_or_original_task_ids(self):
        with self.pool.hold(TEST_KEYS) as credential:
            credential.bind_task("sensitive-provider-task-value")
        with closing(sqlite3.connect(str(self.path))) as connection:
            database = "\n".join(connection.iterdump())
        for value in (*TEST_KEYS, "sensitive-provider-task-value"):
            self.assertNotIn(value, database)

    def test_ordinary_error_releases_and_wait_callback_errors_do_not_break_task(self):
        def broken_callback(waiting):
            raise RuntimeError("rendering failure")

        with self.assertRaisesRegex(ValueError, "local validation"):
            with self.pool.hold(TEST_KEYS, on_wait=broken_callback):
                raise ValueError("local validation")
        self.assertEqual(self.pool.snapshot(), {"active": 0, "retained": 0})

    def test_nonblocking_read_lease_skips_busy_key(self):
        ready, done = threading.Event(), threading.Event()
        key = pool_module.credential_fingerprint(TEST_KEYS[0])

        def holding():
            with self.pool.hold(TEST_KEYS, preferred_fingerprint=key):
                ready.set()
                done.wait(3)

        thread = threading.Thread(target=holding)
        thread.start()
        try:
            self.assertTrue(ready.wait(3))
            started = time.monotonic()
            with self.pool.try_hold_nonblocking(TEST_KEYS, preferred_fingerprint=key) as credential:
                self.assertIsNone(credential)
            self.assertLess(time.monotonic() - started, 0.5)
        finally:
            done.set()
            thread.join(3)
        with self.pool.try_hold_nonblocking(TEST_KEYS, preferred_fingerprint=key) as credential:
            self.assertEqual(credential.fingerprint, key)

    def test_cold_getter_constructs_only_once_across_threads(self):
        pool_module._cached_pool.cache_clear()
        self.addCleanup(pool_module._cached_pool.cache_clear)
        barrier = threading.Barrier(8)
        constructor = pool_module.OmniaKeyPool

        def get_pool(_):
            barrier.wait(5)
            return pool_module.get_omnia_key_pool()

        with patch.dict(os.environ, {"XIAOHA_OMNIA_KEY_DB": str(Path(self.temp.name) / "cold.sqlite3")}), \
                patch.object(pool_module, "OmniaKeyPool", wraps=constructor) as construct:
            with ThreadPoolExecutor(max_workers=8) as executor:
                instances = list(executor.map(get_pool, range(8)))
        self.assertEqual(len({id(instance) for instance in instances}), 1)
        self.assertEqual(construct.call_count, 1)

    def test_constructor_retries_transient_wal_lock(self):
        original_connect = pool_module.OmniaKeyPool._connect
        attempts = []

        class LockedOnce:
            def __init__(self, connection):
                self.connection = connection

            def execute(self, sql, *args):
                if sql == "PRAGMA journal_mode=WAL":
                    attempts.append(True)
                    if len(attempts) == 1:
                        raise sqlite3.OperationalError("database is locked")
                return self.connection.execute(sql, *args)

            def executescript(self, sql):
                return self.connection.executescript(sql)

            def close(self):
                return self.connection.close()

        def connect(instance):
            return LockedOnce(original_connect(instance))

        with patch.object(pool_module.OmniaKeyPool, "_connect", new=connect):
            self.make_pool()
        self.assertEqual(len(attempts), 2)


if __name__ == "__main__":
    unittest.main()
