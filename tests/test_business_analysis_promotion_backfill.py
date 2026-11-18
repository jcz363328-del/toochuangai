from datetime import date
import unittest
from unittest.mock import Mock, patch

import business_analysis_promotion_backfill as module
from innovation.message_service import MessageService


class FakeConnection:
    def __init__(self):
        self.status = '发送失败'
        self.attempts = {}
        self.result = []
        self.released = False

    def __enter__(self): return self
    def __exit__(self, *args): pass
    def cursor(self): return self
    def commit(self): pass
    def fetchone(self): return self.result[0] if self.result else None
    def fetchall(self): return self.result

    def execute(self, sql, params=()):
        self.result = []
        if 'sp_getapplock' in sql: self.result = [(0,)]
        elif 'sp_releaseapplock' in sql: self.released = True
        elif sql.startswith('SELECT RiQi,DianPu'): self.result = [(date(2026, 11, 4), 33)]
        elif sql.startswith('SELECT XuHao'):
            self.result = [(415, 33, date(2026, 11, 4), '银4', '金1', '赵羽姝', self.status, None, None)]
        elif sql.startswith('SELECT Recipient'):
            self.result = [(n, r[0], r[1]) for n, r in self.attempts.items()]
        elif sql.startswith('SELECT FeiShu_ID'): self.result = [('ou_' + params[0],)]
        elif sql.startswith('INSERT INTO dbo.DianPuJinJiRecipientSend'): self.attempts[params[1]] = ('发送中', None)
        elif sql.startswith('UPDATE dbo.DianPuJinJiRecipientSend'):
            self.attempts[params[4]] = (params[0], params[1])
        elif sql.startswith('UPDATE dbo.DianPuJinJi SET'): self.status = params[1]


class PromotionBackfillTests(unittest.TestCase):
    def test_successful_notification_is_never_resent(self):
        self.assertEqual(module.pending_recipients('已发送', None, {}), [])

    def test_partial_failure_only_retries_unsuccessful_recipients(self):
        targets = module.pending_recipients('部分失败', None, {
            module.DEFAULT_RECIPIENTS[0]: {'status': '已发送'},
            module.DEFAULT_RECIPIENTS[1]: {'status': '发送失败'},
        })
        self.assertEqual(targets, list(module.DEFAULT_RECIPIENTS[1:]))

    def test_ambiguous_delivery_is_blocked(self):
        cases = [('部分失败', {}), ('发送中', {}),
            ('部分失败', {'蔡晶': {'status': '待核实'}}),
            ('部分失败', {'蔡晶': {'status': '发送中'}})]
        for status, attempts in cases:
            with self.subTest(status=status, attempts=attempts), self.assertRaises(ValueError):
                module.pending_recipients(status, None, attempts)

    def test_historical_message_does_not_claim_current_level(self):
        message = module.message_for({'store': 33, 'operator': '赵羽姝',
            'previousTier': '银4', 'tier': '金1', 'date': date(2026, 11, 4)})
        self.assertIn('银4 → 金1', message)
        self.assertIn('2026-11-04', message)
        self.assertIn('不代表当前等级', message)
        self.assertNotIn('30天', message)

    def test_send_records_success_and_second_click_sends_nothing(self):
        conn = FakeConnection()
        post = Mock(return_value=Mock(json=lambda: {'code': 0, 'data': {'message_id': 'om_test'}}))
        with patch.object(module, '_connect', return_value=conn), patch.object(MessageService, '_get_access_token', return_value='test-token'), patch.object(module.requests, 'post', post):
            self.assertEqual(module.send_backfill(415), {'sent': 6, 'failed': 0, 'status': '已发送'})
            self.assertTrue(conn.released)
            self.assertEqual(post.call_count, 6)
            self.assertEqual(module.send_backfill(415)['sent'], 0)
            self.assertEqual(post.call_count, 6)

    def test_timeout_is_not_retried_on_next_click(self):
        conn = FakeConnection()
        post = Mock(side_effect=TimeoutError)
        with patch.object(module, '_connect', return_value=conn), patch.object(MessageService, '_get_access_token', return_value='test-token'), patch.object(module.requests, 'post', post):
            self.assertEqual(module.send_backfill(415)['failed'], 6)
            with self.assertRaisesRegex(ValueError, '待核实'):
                module.send_backfill(415)
            self.assertEqual(post.call_count, 6)


class PartialRetryTests(unittest.TestCase):
    def test_explicit_failure_retries_only_failed_recipient(self):
        conn = FakeConnection()
        success = Mock(json=lambda: {'code': 0, 'data': {'message_id': 'om_test'}})
        failure = Mock(json=lambda: {'code': 999, 'msg': 'rejected'})
        post = Mock(side_effect=[failure] + [success] * 6)
        with patch.object(module, '_connect', return_value=conn), patch.object(MessageService, '_get_access_token', return_value='test-token'), patch.object(module.requests, 'post', post):
            self.assertEqual(module.send_backfill(415)['failed'], 1)
            self.assertEqual(module.send_backfill(415), {'sent': 1, 'failed': 0, 'status': '已发送'})
            self.assertEqual(post.call_count, 7)


if __name__ == '__main__':
    unittest.main()
