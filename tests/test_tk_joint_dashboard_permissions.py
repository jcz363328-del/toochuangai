import copy
from datetime import date, timedelta
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from flask import Flask

os.environ.setdefault("TK_DASHBOARD_DISABLE_BACKGROUND_CACHE", "1")

import tk_total_dashboard as dashboard_module
from permission_seed_data import JOINT_SHOP_USERS


ROOT = Path(__file__).resolve().parents[1]


class TkJointDashboardPermissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.backend = (ROOT / "tk_total_dashboard.py").read_text(encoding="utf-8")
        cls.app = (ROOT / "app.py").read_text(encoding="utf-8")
        cls.dashboard_template = (
            ROOT / "templates" / "tk_total_dashboard.html"
        ).read_text(encoding="utf-8")
        cls.project_template = (
            ROOT / "templates" / "tk_project.html"
        ).read_text(encoding="utf-8")

    def test_all_requested_shop_user_bindings_are_configured(self):
        expected_bindings = {
            "82": "侯梁",
            "88": "刘俊霞",
            "90": "孙洁",
            "87": "刘蓉蓉",
            "89": "柳琳",
            "91": "叶雨菲",
            "92": "刘星辰",
            "93": "赵璐华",
            "95": "杨明月",
            "96": "周雪",
            "106": "李娜",
            "97": "郭婷",
            "101": "侯瑞昕",
            "84": "大张雯",
            "107": "郭鑫",
            "108": "张彦微",
            "109": "王钰媛",
        }
        for shop, user_name in expected_bindings.items():
            with self.subTest(shop=shop, user_name=user_name):
                self.assertEqual(user_name, JOINT_SHOP_USERS[shop])

    def test_page_and_entry_use_joint_dashboard_name(self):
        self.assertIn("page_title='联营店铺看板'", self.backend)
        self.assertIn("mini_card('联营店铺看板'", self.project_template)
        self.assertNotIn("内容生产工厂订单维度看板", self.project_template)

    def test_shop_list_and_metrics_share_server_side_scope(self):
        self.assertIn("def get_joint_dashboard_allowed_shops", self.backend)
        self.assertIn("@tk_dashboard_bp.route('/tk/joint_shops'", self.backend)
        self.assertIn("const shopsUrl = RESTRICT_LIKE_82 ? '/tk/joint_shops'", self.dashboard_template)
        self.assertIn("unauthorized_shops = [shop for shop in shops if shop not in allowed_shop_set]", self.backend)

    def test_named_users_can_see_entry_without_total_dashboard_permission(self):
        self.assertIn("get_joint_dashboard_allowed_shops", self.app)
        self.assertIn("can_view_joint_dashboard=bool(get_joint_dashboard_allowed_shops())", self.app)
        self.assertIn("{% if can_view_joint_dashboard %}", self.project_template)

    def test_manual_refresh_uses_user_independent_shared_cache(self):
        self.assertIn("def _joint_shared_metrics_cache_key", self.backend)
        self.assertIn("'joint-dashboard:shared:' + PARTIAL_DASHBOARD_SALES_SOURCE", self.backend)
        self.assertIn("def _load_joint_shared_metrics_payload", self.backend)
        self.assertIn("def _save_joint_shared_metrics_payload", self.backend)
        self.assertIn("if sales_source == PARTIAL_DASHBOARD_SALES_SOURCE and not force_refresh", self.backend)
        self.assertIn("JOINT_SHARED_CACHE_TTL = 10 * 365 * 24 * 60 * 60", self.backend)

    def test_admin_refresh_is_reused_by_authorized_shop_user(self):
        flask_app = Flask(__name__, template_folder=str(ROOT / "templates"))
        flask_app.secret_key = "joint-cache-test"
        flask_app.register_blueprint(dashboard_module.tk_dashboard_bp)
        client = flask_app.test_client()
        persistent_store = {}

        def fake_save(cache_key, payload, ttl=None):
            persistent_store[cache_key] = copy.deepcopy(payload)
            return True

        def fake_load(cache_key):
            payload = persistent_store.get(cache_key)
            return copy.deepcopy(payload), bool(payload)

        def fake_permission(user_id, function_name):
            if user_id == "ou_admin":
                return function_name in {"tk_dashboard_full", "tk_joint_dashboard_all"}, "test"
            if user_id == "ou_shop_82":
                return function_name == "tk_joint_shop_82", "test"
            return False, "test"

        request_body = {
            "start_date": "2026-08-01",
            "end_date": "2026-08-11",
            "shops": ["82"],
            "sales_source": dashboard_module.PARTIAL_DASHBOARD_SALES_SOURCE,
        }
        calculated_payload = {
            "success": True,
            "total_sales": 321.0,
            "sales_source": dashboard_module.PARTIAL_DASHBOARD_SALES_SOURCE,
        }

        with patch.object(
            dashboard_module,
            "_get_cached_metrics_payload",
            return_value=calculated_payload,
        ) as compute_mock, patch.object(
            dashboard_module,
            "_promote_manual_refresh_to_standard_cache",
        ), patch.object(
            dashboard_module,
            "_save_persistent_metrics_payload",
            side_effect=fake_save,
        ), patch.object(
            dashboard_module,
            "_load_persistent_metrics_payload",
            side_effect=fake_load,
        ), patch.object(
            dashboard_module.permission_manager,
            "check_user_permission",
            side_effect=fake_permission,
        ):
            with client.session_transaction() as session_data:
                session_data["feishu_user_id"] = "ou_admin"
                session_data["feishu_user_name"] = "周俊成"
            refresh_response = client.post(
                "/tk/metrics",
                json={**request_body, "force_refresh": True},
            )
            self.assertEqual(refresh_response.status_code, 200)
            self.assertEqual(
                refresh_response.get_json()["shared_cache"]["scope"],
                "joint_dashboard",
            )

            with client.session_transaction() as session_data:
                session_data["feishu_user_id"] = "ou_shop_82"
                session_data["feishu_user_name"] = "侯梁"
            reuse_response = client.post(
                "/tk/metrics",
                json={**request_body, "force_refresh": False},
            )

        self.assertEqual(reuse_response.status_code, 200)
        self.assertEqual(reuse_response.get_json()["total_sales"], 321.0)
        self.assertEqual(compute_mock.call_count, 1)

    def test_overall_yesterday_order_sales_endpoint_uses_tk_order_gmv(self):
        flask_app = Flask(__name__, template_folder=str(ROOT / "templates"))
        flask_app.secret_key = "overall-order-sales-test"
        flask_app.register_blueprint(dashboard_module.tk_dashboard_bp)
        client = flask_app.test_client()

        def fake_permission(user_id, function_name):
            return function_name == "tk_dashboard_full", "test"

        with patch.object(
            dashboard_module,
            "_get_tk_order_gmv_sales",
            return_value={"previous": 456.78, "selected": 456.78, "yesterday": 456.78},
        ) as order_sales_mock, patch.object(
            dashboard_module.permission_manager,
            "check_user_permission",
            side_effect=fake_permission,
        ):
            with client.session_transaction() as session_data:
                session_data["feishu_user_id"] = "ou_admin"
            response = client.post(
                "/tk/yesterday_order_sales",
                json={"shops": ["86"]},
            )

        today = date.today()
        start_dt = date(today.year, today.month, 1)
        prev_month = today.month - 1 or 12
        prev_year = today.year - 1 if today.month == 1 else today.year
        prev_start = date(prev_year, prev_month, 1)
        if prev_month == 12:
            next_month = date(prev_year + 1, 1, 1)
        else:
            next_month = date(prev_year, prev_month + 1, 1)
        prev_end = next_month - timedelta(days=1)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["total_order_sales"], 456.78)
        self.assertEqual(response.get_json()["previous_order_sales"], 456.78)
        self.assertEqual(response.get_json()["selected_order_sales"], 456.78)
        order_sales_mock.assert_called_once_with(
            start_dt,
            today,
            prev_start,
            prev_end,
            ["86"],
        )


if __name__ == "__main__":
    unittest.main()
