import unittest

from streamlit.testing.v1 import AppTest


SCRIPT = '''
from types import SimpleNamespace
import streamlit as st
from 图片.balance_view import render_balance_management

def load_snapshot(force=False):
    st.session_state.setdefault("load_calls", []).append(force)
    if st.session_state.get("raise_loader"):
        raise RuntimeError("provider balance $987.65 USD secret-test-value")
    if force and "refreshed_snapshot" in st.session_state:
        return st.session_state["refreshed_snapshot"]
    return st.session_state["snapshot"]

render_balance_management(SimpleNamespace(st=st), load_snapshot)
'''


class BalanceViewTests(unittest.TestCase):
    def app(self, percent=64.5, error=False, updated_at='2026-11-24 14:00:00', **extra):
        app = AppTest.from_string(SCRIPT)
        app.session_state['snapshot'] = {
            'percent': percent, 'updated_at': updated_at, 'error': error, **extra,
        }
        app.run()
        self.assertFalse(list(app.exception))
        return app

    @staticmethod
    def rendered_text(app):
        fields = ('body', 'label', 'help', 'text', 'delta', 'description')
        return '\n'.join(
            str(getattr(element.proto, field))
            for element in app if getattr(element, 'proto', None) is not None
            for field in fields if hasattr(element.proto, field)
        )

    def test_normal_balance_shows_only_percentage_status_and_update(self):
        app = self.app()
        self.assertEqual(app.metric[0].value, '64.5%')
        self.assertEqual(app.metric[1].value, '充足')
        self.assertEqual(app.get('progress')[0].proto.value, 64)
        self.assertEqual(app.caption[0].value, '上次更新：2026-11-24 14:00:00')
        self.assertEqual(app.session_state['load_calls'], [False])
        self.assertTrue(any('余额管理' in item.value for item in app.markdown))

    def test_zero_is_valid_and_does_not_show_unavailable(self):
        app = self.app(percent=0)
        self.assertEqual(app.metric[0].value, '0%')
        self.assertEqual(app.metric[1].value, '偏低')
        self.assertEqual(app.get('progress')[0].proto.value, 0)
        self.assertFalse(list(app.error))

    def test_status_thresholds_are_inclusive(self):
        for percent, expected in ((10, '偏低'), (10.1, '留意'), (20, '留意'), (20.1, '充足')):
            with self.subTest(percent=percent):
                self.assertEqual(self.app(percent=percent).metric[1].value, expected)

    def test_above_full_scale_keeps_percentage_and_caps_progress(self):
        app = self.app(percent=135.6)
        self.assertEqual(app.metric[0].value, '135.6%')
        self.assertEqual(app.get('progress')[0].proto.value, 100)

    def test_initial_failure_does_not_fabricate_zero(self):
        app = self.app(percent=None, error=True, updated_at='')
        self.assertEqual(app.error[0].value, '暂时无法获取余额，请稍后刷新')
        self.assertFalse(list(app.metric))
        self.assertFalse(list(app.get('progress')))
        self.assertFalse(list(app.caption))

    def test_failed_refresh_preserves_prior_value_and_timestamp(self):
        app = self.app(percent=42.3, error=True)
        self.assertEqual(app.metric[0].value, '42.3%')
        self.assertEqual(app.warning[0].value, '部分用量暂未核对，当前显示已核对余额，请稍后刷新。')
        self.assertEqual(app.caption[0].value, '上次更新：2026-11-24 14:00:00')
        self.assertFalse(list(app.error))

    def test_manual_refresh_requests_fresh_snapshot_once(self):
        app = self.app(percent=42.3)
        app.session_state['refreshed_snapshot'] = {
            'percent': 55, 'updated_at': '2026-11-24 14:05:00', 'error': False,
        }
        app.button(key='balance_management_refresh').click().run()
        self.assertFalse(list(app.exception))
        self.assertEqual(app.session_state['load_calls'], [False, True])
        self.assertEqual(app.metric[0].value, '55%')
        self.assertEqual(app.caption[0].value, '上次更新：2026-11-24 14:05:00')
        app.run()
        self.assertEqual(app.session_state['load_calls'], [False, True, False])

    def test_nonfinite_snapshot_is_unavailable_instead_of_zero_or_progress_error(self):
        for percent in (float('nan'), float('inf')):
            with self.subTest(percent=percent):
                app = self.app(percent=percent)
                self.assertFalse(list(app.metric))
                self.assertEqual(app.error[0].value, '暂时无法获取余额，请稍后刷新')

    def test_ui_never_renders_provider_fields_or_currency(self):
        app = self.app(raw={'balance': 987.65, 'secret': 'secret-test-value'}, currency='USD')
        text = self.rendered_text(app)
        for forbidden in ('美元', '$', 'USD', '987.65', 'secret-test-value', '100美元'):
            self.assertNotIn(forbidden, text)
        app.session_state['raise_loader'] = True
        app.run()
        self.assertFalse(list(app.exception))
        self.assertEqual(app.error[0].value, '暂时无法获取余额，请稍后刷新')
        text = self.rendered_text(app)
        for forbidden in ('美元', '$', 'USD', '987.65', 'secret-test-value', '100美元'):
            self.assertNotIn(forbidden, text)

    def test_baseline_precision_and_reconciliation_source_are_clear(self):
        app = self.app(percent=42.86)
        self.assertEqual(app.metric[0].value, '42.86%')
        self.assertTrue(any('充值或使用其他密钥后，需要重新校准' in item.value for item in app.caption))

    def test_per_call_table_shows_percent_and_pending_without_exposing_amounts(self):
        app = self.app(pending_calls=1, active_calls=1, calls=[
            {'call_id': 'call-a', 'task_id': 'task-123456789012345', 'model': 'nano-banana',
             'resolution': '2K', 'channel': 2, 'cost_percent': .029, 'status': 'settled',
             'outcome': 'success', 'created_at': '2026-11-24 15:10:00', 'raw_usd': 987.65},
            {'call_id': 'call-b', 'task_id': '', 'model': 'nano-banana', 'resolution': '4K',
             'channel': 3, 'cost_percent': None, 'status': 'pending', 'outcome': 'uncertain'},
        ])
        frame = app.dataframe[0].value
        self.assertEqual(frame.iloc[0]['消耗比例'], '0.029%')
        self.assertEqual(frame.iloc[0]['通道'], '通道 2')
        self.assertEqual(frame.iloc[0]['任务'], 'task-1234567…')
        self.assertEqual(frame.iloc[1]['消耗比例'], '待核对')
        self.assertIn('1 次调用费用待核对', app.info[0].value)
        self.assertNotIn('987.65', frame.to_string())

    def test_tiny_verified_cost_is_not_rounded_to_free(self):
        app = self.app(calls=[{'call_id': 'call-a', 'model': 'text-model', 'channel': 1,
                              'cost_percent': .00000001, 'status': 'settled', 'outcome': 'success'}])
        self.assertEqual(app.dataframe[0].value.iloc[0]['消耗比例'], '<0.000001%')

    def test_failed_refunded_task_shows_zero_net_cost_and_verified_return(self):
        app = self.app(percent=42.774, calls=[{
            'call_id': 'refunded-call', 'model': 'nano-banana', 'channel': 1,
            'cost_percent': 0, 'refund_percent': .039, 'refunded': True,
            'status': 'settled', 'outcome': 'failed',
        }])
        row = app.dataframe[0].value.iloc[0]
        self.assertEqual(row['状态'], '失败·已退款')
        self.assertEqual(row['消耗比例'], '0%')
        self.assertEqual(row['退回比例'], '0.039%')
        self.assertFalse(list(app.warning))

    def test_failed_confirmed_zero_without_observed_refund_does_not_claim_return(self):
        app = self.app(calls=[{'call_id': 'rejected', 'model': 'nano-banana', 'channel': 1,
                              'cost_percent': 0, 'status': 'settled', 'outcome': 'failed'}])
        row = app.dataframe[0].value.iloc[0]
        self.assertEqual(row['状态'], '失败·未扣费')
        self.assertEqual(row['退回比例'], '—')


if __name__ == '__main__':
    unittest.main()
