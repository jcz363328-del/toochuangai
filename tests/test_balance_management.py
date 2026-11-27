from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime, timezone
from decimal import Decimal
import threading
import unittest
from unittest.mock import Mock

from Department.视觉设计部.xiaoha.balance_management import BalanceCache


class BalanceManagementTests(unittest.TestCase):
    def setUp(self):
        self.elapsed = 0.0
        self.now = datetime(2026, 11, 24, 7, 0, 0, tzinfo=timezone.utc)
        self.cache = BalanceCache(clock=lambda: self.elapsed, now=lambda: self.now)

    def test_real_remaining_balance_is_the_percentage_source(self):
        fetch = Mock(return_value=Decimal('25.75'))
        result = self.cache.snapshot('scope-a', fetch)
        self.assertEqual(result, {
            'percent': 25.75, 'updated_at': '2026-11-24 15:00:00', 'error': False,
        })
        fetch.assert_called_once_with()

    def test_success_is_cached_for_five_minutes(self):
        fetch = Mock(side_effect=[Decimal('30'), Decimal('28')])
        first = self.cache.snapshot('scope-a', fetch)
        self.elapsed = 299
        self.assertEqual(self.cache.snapshot('scope-a', fetch), first)
        fetch.assert_called_once()
        self.elapsed = 300
        self.now = datetime(2026, 11, 24, 7, 5, 0, tzinfo=timezone.utc)
        refreshed = self.cache.snapshot('scope-a', fetch)
        self.assertEqual(refreshed['percent'], 28)
        self.assertEqual(refreshed['updated_at'], '2026-11-24 15:05:00')
        self.assertEqual(fetch.call_count, 2)

    def test_forced_refresh_bypasses_success_and_failure_ttl(self):
        fetch = Mock(side_effect=[20, RuntimeError('private-provider-response'), 40])
        self.cache.snapshot('scope-a', fetch)
        failed = self.cache.snapshot('scope-a', fetch, force=True)
        self.assertEqual(failed['percent'], 20)
        self.assertTrue(failed['error'])
        refreshed = self.cache.snapshot('scope-a', fetch, force=True)
        self.assertEqual(refreshed['percent'], 40)
        self.assertFalse(refreshed['error'])
        self.assertEqual(fetch.call_count, 3)

    def test_refresh_failure_keeps_old_value_and_original_update_time(self):
        first = self.cache.snapshot('scope-a', lambda: 25.5)
        self.elapsed = 300
        self.now = datetime(2026, 11, 24, 7, 5, 0, tzinfo=timezone.utc)
        fetch = Mock(side_effect=RuntimeError('provider secret = private-test-marker'))
        failed = self.cache.snapshot('scope-a', fetch)
        self.assertEqual(failed, dict(first, error=True))
        self.elapsed = 329
        self.assertEqual(self.cache.snapshot('scope-a', fetch), failed)
        fetch.assert_called_once()
        self.assertNotIn('private-test-marker', repr(self.cache.__dict__))
        self.elapsed = 330
        self.cache.snapshot('scope-a', fetch)
        self.assertEqual(fetch.call_count, 2)

    def test_initial_failure_is_unknown_and_cached_only_for_thirty_seconds(self):
        fetch = Mock(side_effect=[RuntimeError('not-for-display'), 18])
        failure = self.cache.snapshot('scope-a', fetch)
        self.assertEqual(failure, {'percent': None, 'updated_at': '', 'error': True})
        self.elapsed = 29
        self.assertEqual(self.cache.snapshot('scope-a', fetch), failure)
        fetch.assert_called_once()
        self.elapsed = 30
        self.assertEqual(self.cache.snapshot('scope-a', fetch)['percent'], 18)
        self.assertEqual(fetch.call_count, 2)

    def test_invalid_values_never_turn_into_a_displayed_balance(self):
        invalid = (True, False, None, '', 'USD 5', 'abc', {}, object(),
                   float('nan'), float('inf'), float('-inf'),
                   Decimal('NaN'), Decimal('Infinity'), '1e1000000')
        for value in invalid:
            with self.subTest(value=type(value).__name__):
                result = self.cache.snapshot('invalid', lambda: value, force=True)
                self.assertEqual(result, {'percent': None, 'updated_at': '', 'error': True})

    def test_zero_negative_and_above_full_scale_keep_correct_semantics(self):
        for value, expected in ((0, 0), (Decimal('-5.7'), 0), ('123.45', 123.45)):
            with self.subTest(value=value):
                result = self.cache.snapshot('scope-a', lambda: value, force=True)
                self.assertEqual(result['percent'], expected)
                self.assertFalse(result['error'])

    def test_timestamp_uses_shanghai_timezone_including_date_rollover(self):
        self.now = datetime(2026, 11, 24, 20, 4, 5, tzinfo=timezone.utc)
        result = self.cache.snapshot('scope-a', lambda: 7)
        self.assertEqual(result['updated_at'], '2026-11-25 04:04:05')
        self.now = datetime(2026, 11, 25, 10, 2, 3)
        result = self.cache.snapshot('scope-a', lambda: 8, force=True)
        self.assertEqual(result['updated_at'], '2026-11-25 10:02:03')

    def test_scopes_are_isolated_and_least_recently_used_is_evicted_after_eight(self):
        fetches = [Mock(return_value=i) for i in range(9)]
        for i in range(8):
            self.cache.snapshot(f'scope-{i}', fetches[i])
        self.cache.snapshot('scope-0', fetches[0])
        self.cache.snapshot('scope-8', fetches[8])
        self.assertEqual(self.cache.snapshot('scope-0', fetches[0])['percent'], 0)
        fetches[0].assert_called_once()
        self.cache.snapshot('scope-1', fetches[1])
        self.assertEqual(fetches[1].call_count, 2)
        self.assertLessEqual(len(self.cache._entries), 8)

    def test_mutating_public_snapshot_cannot_change_cached_value(self):
        fetch = Mock(return_value=30)
        first = self.cache.snapshot('scope-a', fetch)
        first.update(percent=999, error=True, raw='do-not-store')
        second = self.cache.snapshot('scope-a', fetch)
        self.assertEqual(second, {'percent': 30, 'updated_at': '2026-11-24 15:00:00', 'error': False})

    def test_cancelled_fetch_does_not_leave_scope_locked(self):
        class Cancelled(BaseException):
            pass

        with self.assertRaises(Cancelled):
            self.cache.snapshot('scope-a', Mock(side_effect=Cancelled))
        self.assertNotIn('scope-a', self.cache._inflight)
        result = self.cache.snapshot('scope-a', lambda: 27, force=True)
        self.assertEqual(result['percent'], 27)
        self.assertFalse(result['error'])

    def test_concurrent_refreshes_share_one_fetch_and_safe_result(self):
        entered, release = threading.Event(), threading.Event()

        def fetch():
            entered.set()
            if not release.wait(2):
                raise RuntimeError('test release timeout')
            return Decimal('33.3')

        callback = Mock(side_effect=fetch)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.cache.snapshot, 'scope-a', callback)
            self.assertTrue(entered.wait(1))
            second = pool.submit(self.cache.snapshot, 'scope-a', callback, True)
            try:
                with self.assertRaises(TimeoutError):
                    second.result(timeout=.05)
            finally:
                release.set()
            first_result, second_result = first.result(timeout=1), second.result(timeout=1)
        callback.assert_called_once()
        self.assertEqual(first_result, second_result)
        self.assertEqual(first_result['percent'], 33.3)
        self.assertEqual(set(first_result), {'percent', 'updated_at', 'error'})


if __name__ == '__main__':
    unittest.main()
