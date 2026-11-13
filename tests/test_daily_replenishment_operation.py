import tempfile
import time
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from openpyxl import load_workbook

import app as app_module
import daily_replenishment as base
import daily_replenishment_operation as operation
from tests.test_daily_replenishment import build_sample_dataset


class DailyReplenishmentOperationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_dir = app_module.app.config.get("DAILY_REPLENISHMENT_OPERATION_OUTPUT_DIR")
        app_module.app.config.update(
            TESTING=True,
            DAILY_REPLENISHMENT_OPERATION_OUTPUT_DIR=self.temp_dir.name,
        )
        self.client = app_module.app.test_client()
        with self.client.session_transaction() as session:
            session["feishu_user_id"] = "dev_operation_test_user"
            session["feishu_user_name"] = "测试用户"

    def tearDown(self):
        if self.old_dir is None:
            app_module.app.config.pop("DAILY_REPLENISHMENT_OPERATION_OUTPUT_DIR", None)
        else:
            app_module.app.config["DAILY_REPLENISHMENT_OPERATION_OUTPUT_DIR"] = self.old_dir
        self.temp_dir.cleanup()

    def request(self, method, path, **kwargs):
        with patch.object(app_module.permission_manager, "check_user_permission", return_value=(True, "test")):
            access = {"read_stores": {"1"}, "write_stores": {"1"}, "can_write": True}
            with patch.object(operation, "scoped_query_executor", return_value=(lambda sql: [], access)):
                return self.client.open(path, method=method, **kwargs)

    def test_page_is_independent_from_daily_replenishment(self):
        response = self.request("GET", "/ai/daily-replenishment-operation")
        self.assertEqual(200, response.status_code)
        html = response.get_data(as_text=True)
        self.assertIn("智能补货中心-运营", html)
        self.assertIn("/api/ai/daily-replenishment-operation/refresh", html)

    def test_all_column_filters_support_multiple_values(self):
        response = self.request("GET", "/ai/daily-replenishment-operation")
        self.assertEqual(200, response.status_code)
        html = response.get_data(as_text=True)
        self.assertIn('class="filter-option"', html)
        self.assertIn('type="checkbox"', html)
        self.assertIn("selected.includes(String(x.row[i]??''))", html)
        self.assertIn("已选 ${selected.length} 项", html)
        self.assertNotIn('<select class="column-filter', html)

    def test_complete_sheet_chain_is_generated_and_saved(self):
        def fake_query(sql):
            if "daily_replenishment:core" in sql:
                return []
            return []

        with app_module.app.app_context():
            with patch.object(operation, "_settings", return_value=base.get_generation_settings(as_of_date=date(2026, 9, 17))):
                dataset = operation.generate_operation_dataset(query_executor=fake_query)
            dataset["main"] = build_sample_dataset()
            path = Path(self.temp_dir.name) / "operation.xlsx"
            operation.save_operation_workbook(dataset, path)

        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            self.assertEqual(list(operation.SHEET_ORDER), workbook.sheetnames[:7])
        finally:
            workbook.close()

    def test_permission_is_separate(self):
        with patch.object(app_module.permission_manager, "check_user_permission", return_value=(False, "denied")) as check:
            response = self.client.get("/ai/daily-replenishment-operation")
        self.assertEqual(302, response.status_code)
        check.assert_called_once_with("dev_operation_test_user", "daily_replenishment_operation")

    def test_operator_store_lookup_uses_feishu_name(self):
        def fake_query(sql):
            self.assertIn("DianQuanXian", sql)
            self.assertIn("YunYing", sql)
            self.assertIn("测试用户", sql)
            return [(12, 2), (18, 1)]

        self.assertEqual({"12", "18"}, operation.get_operator_stores("测试用户", query_executor=fake_query))

    def test_scoped_executor_filters_store_and_sku_sheets(self):
        def fake_query(sql):
            if "store_permissions" in sql:
                return [(12, 2)]
            if "visible_skus" in sql:
                return [("SKU-A",)]
            if "daily_replenishment:core" in sql:
                return [("甲", 12, "C", "SKU-A"), ("乙", 18, "D", "SKU-B")]
            if "sheet_inventory_detail" in sql:
                return [("LOC", "SKU-A", 3), ("LOC", "SKU-B", 4)]
            return []

        execute, access = operation.scoped_query_executor("测试用户", query_executor=fake_query)

        self.assertEqual({"12"}, access["read_stores"])
        self.assertFalse(access["can_write"])
        self.assertEqual(1, len(execute("/* daily_replenishment:core */")))
        self.assertEqual(1, len(execute("/* daily_replenishment:sheet_inventory_detail */")))

    def test_current_user_name_falls_back_to_open_id_mapping(self):
        with self.client.session_transaction() as flask_session:
            flask_session.pop("feishu_user_name", None)
            flask_session["feishu_user_id"] = "ou_test_operator"
        with app_module.app.test_request_context("/"):
            operation.session["feishu_user_id"] = "ou_test_operator"
            name = operation._current_user_name(query_executor=lambda sql: [("张三",)])

        self.assertEqual("张三", name)

    def test_switched_identity_takes_priority_over_real_login_name(self):
        with app_module.app.test_request_context("/"):
            operation.session["feishu_user_name"] = "周俊成"
            operation.session["permission_debug_user_name"] = "李筱"

            name = operation._current_user_name(query_executor=lambda sql: [])

        self.assertEqual("李筱", name)

    def test_cookie_request_identity_takes_priority_over_session_identity(self):
        with app_module.app.test_request_context("/"):
            operation.session["feishu_user_name"] = "周俊成"
            operation.session["permission_debug_user_name"] = "李筱"
            operation.g.permission_debug_state = {
                "user_name": "孙洁",
                "user_open_id": "ou_sunjie",
                "departments": ["运营一部"],
            }

            name = operation._current_user_name(query_executor=lambda sql: [])

        self.assertEqual("孙洁", name)

    def test_operator_without_stores_gets_empty_scope_instead_of_forbidden(self):
        execute, access = operation.scoped_query_executor("无店铺运营", query_executor=lambda sql: [])

        self.assertEqual(set(), access["read_stores"])
        self.assertEqual([], execute("/* daily_replenishment:core */ SELECT 1"))

    def test_zhou_juncheng_permissions_come_from_dianquanxian(self):
        captured = []

        def fake_query(sql):
            captured.append(sql)
            return [(2, 1), (2, 2), (3, 2), (4, 1)]

        access = operation.get_store_permissions("周俊成", query_executor=fake_query)

        self.assertEqual({"2", "3", "4"}, access["read_stores"])
        self.assertEqual({"2", "4"}, access["write_stores"])
        self.assertTrue(access["can_write"])
        self.assertIn("DianQuanXian", captured[0])
        self.assertIn("YunYing", captured[0])

    def test_read_only_user_cannot_refresh(self):
        access = {"read_stores": {"12"}, "write_stores": set(), "can_write": False}
        with patch.object(app_module.permission_manager, "check_user_permission", return_value=(True, "test")):
            with patch.object(operation, "scoped_query_executor", return_value=(lambda sql: [], access)):
                response = self.client.post("/api/ai/daily-replenishment-operation/refresh")

        self.assertEqual(403, response.status_code)
        self.assertIn("只有阅读权限", response.get_json()["message"])

    def test_refresh_job_runs_in_background_thread_with_app_context(self):
        with patch.object(base, "resolve_source_path", return_value=None):
            response = self.request("POST", "/api/ai/daily-replenishment-operation/refresh")

        self.assertEqual(202, response.status_code)
        job_id = response.get_json()["jobId"]

        payload = None
        deadline = time.time() + 20
        while time.time() < deadline:
            status = self.request("GET", f"/api/ai/daily-replenishment-operation/refresh/{job_id}")
            body = status.get_json()
            if body.get("status") == "failed":
                self.fail(f"刷新任务在后台线程失败：{body.get('message')}")
            # 任务完成时该接口直接返回 payload 本身，没有 status 字段
            if body.get("generation") and body.get("sheets"):
                payload = body
                break
            time.sleep(0.05)

        self.assertIsNotNone(payload, "刷新任务未在超时时间内完成")
        self.assertTrue(payload.get("success"))
        self.assertIn("FBA发货", payload["sheets"])

    def test_main_sheet_payload_preserves_excel_comments(self):
        main = build_sample_dataset()
        main["header_comments"] = {"4": "库存表头批注"}
        main["rows"][0]["comments"] = {"4": "本地：10\nFBA：20"}
        dataset = {"main": main, "sheets": {}, "generation": main["generation"]}

        payload = operation._sheet_payload(dataset)
        sheet = payload["sheets"][base.SHEET_NAME]

        self.assertEqual("库存表头批注", sheet["header_comments"]["4"])
        self.assertEqual("本地：10\nFBA：20", sheet["comments"]["0"]["4"])


    def test_shared_snapshot_payload_is_filtered_for_current_operator(self):
        payload = {
            "sheets": {
                base.SHEET_NAME: {
                    "rows": [["甲", "12", "A", "SKU-A"], ["乙", "18", "B", "SKU-B"]],
                    "comments": {"0": {"4": "A"}, "1": {"4": "B"}},
                },
                "库存明细": {"rows": [["LOC", "SKU-A", 1], ["LOC", "SKU-B", 2]], "comments": {}},
            }
        }
        access = {"read_stores": {"12"}, "visible_skus": {"SKU-A"}}

        scoped = operation._scope_snapshot_payload(payload, access)

        self.assertEqual(1, len(scoped["sheets"][base.SHEET_NAME]["rows"]))
        self.assertEqual("12", scoped["sheets"][base.SHEET_NAME]["rows"][0][1])
        self.assertEqual([["LOC", "SKU-A", 1]], scoped["sheets"]["库存明细"]["rows"])
        self.assertEqual({"0": {"4": "A"}}, scoped["sheets"][base.SHEET_NAME]["comments"])

    def test_shared_snapshot_fallback_prefers_full_scope_snapshot(self):
        snapshot_root = Path(self.temp_dir.name) / "_每日快照"
        snapshot_root.joinpath("operator-a").mkdir(parents=True)
        snapshot_root.joinpath("operator-b").mkdir(parents=True)
        smaller = snapshot_root / "operator-a" / f"{date.today():%Y%m%d}日常补货运营.xlsx"
        larger = snapshot_root / "operator-b" / f"{date.today():%Y%m%d}日常补货运营.xlsx"
        smaller.write_bytes(b"small operator snapshot")
        larger.write_bytes(b"full scope snapshot with more rows")

        with app_module.app.app_context():
            selected = operation.get_shared_today_snapshot()

        self.assertEqual(larger, selected)

    def test_own_snapshot_is_still_filtered_for_current_operator(self):
        payload = {
            "sheets": {
                base.SHEET_NAME: {
                    "columns": ["运营", "店铺", "站点", "SKU"],
                    "rows": [["周雪", "12", "A", "SKU-A"], ["其他运营", "18", "B", "SKU-B"]],
                    "comments": {},
                },
            },
            "generation": {},
        }
        access = {
            "read_stores": {"12"},
            "write_stores": set(),
            "visible_skus": {"SKU-A"},
            "can_write": False,
        }

        with patch.object(app_module.permission_manager, "check_user_permission", return_value=(True, "test")):
            with patch.object(operation, "_current_user_name", return_value="周雪"):
                with patch.object(operation, "scoped_query_executor", return_value=(lambda sql: [], access)):
                    with patch.object(operation, "_resolve_snapshot_for_user", return_value=(Path("own.xlsx"), False)):
                        with patch.object(operation, "load_snapshot_cached", return_value=payload):
                            with patch.object(operation, "_snapshot_payload", return_value={"available": True}):
                                response = self.client.get("/api/ai/daily-replenishment-operation/data")

        self.assertEqual(200, response.status_code)
        rows = response.get_json()["sheets"][base.SHEET_NAME]["rows"]
        self.assertEqual([["周雪", "12", "A", "SKU-A"]], rows)


    def test_sales_trend_returns_daily_series_for_visible_sku(self):
        access = {"read_stores": {"12"}, "write_stores": set(), "can_write": False, "visible_skus": {"SKU-A"}}
        with patch.object(app_module.permission_manager, "check_user_permission", return_value=(True, "test")):
            with patch.object(
                operation,
                "scoped_query_executor",
                return_value=(
                    lambda sql: [
                        ("SKU-A", date(2026, 9, 1), 3),
                        ("SKU-A", date(2026, 9, 2), 5),
                        ("SKU-B", date(2026, 9, 2), 7),
                    ],
                    access,
                ),
            ):
                with patch.object(
                    operation,
                    "_settings",
                    return_value={
                        "sales_start": date(2026, 9, 1),
                        "sales_end": date(2026, 9, 10),
                        "sales_source": "付款",
                        "recent_days": 15,
                    },
                ):
                    response = self.client.get(
                        "/api/ai/daily-replenishment-operation/sales-trend?sku=SKU-A&start=2026-09-01&end=2026-09-03"
                    )

        self.assertEqual(200, response.status_code)
        body = response.get_json()
        self.assertEqual(["2026-09-01", "2026-09-02", "2026-09-03"], [item["date"] for item in body["days"]])
        self.assertEqual([3, 5, 0], [item["qty"] for item in body["days"]])
        self.assertEqual(8, body["sum"])

    def test_sales_trend_returns_series_for_multiple_skus(self):
        access = {"read_stores": {"12"}, "write_stores": set(), "can_write": False, "visible_skus": {"SKU-A", "SKU-B"}}
        with patch.object(app_module.permission_manager, "check_user_permission", return_value=(True, "test")):
            with patch.object(
                operation,
                "scoped_query_executor",
                return_value=(
                    lambda sql: [
                        ("SKU-A", date(2026, 9, 1), 3),
                        ("SKU-B", date(2026, 9, 2), 7),
                    ],
                    access,
                ),
            ):
                with patch.object(
                    operation,
                    "_settings",
                    return_value={
                        "sales_start": date(2026, 9, 1),
                        "sales_end": date(2026, 9, 10),
                        "sales_source": "付款",
                        "recent_days": 15,
                    },
                ):
                    response = self.client.get(
                        "/api/ai/daily-replenishment-operation/sales-trend"
                        "?skus=SKU-A,SKU-B&start=2026-09-01&end=2026-09-02"
                    )

        self.assertEqual(200, response.status_code)
        series = response.get_json()["series"]
        self.assertEqual({"SKU-A", "SKU-B"}, set(series))
        self.assertEqual([3, 0], [item["qty"] for item in series["SKU-A"]])
        self.assertEqual([0, 7], [item["qty"] for item in series["SKU-B"]])

    def test_sales_trend_rejects_sku_outside_scope(self):
        access = {"read_stores": {"12"}, "write_stores": set(), "can_write": False, "visible_skus": {"SKU-A"}}
        with patch.object(app_module.permission_manager, "check_user_permission", return_value=(True, "test")):
            with patch.object(operation, "scoped_query_executor", return_value=(lambda sql: [], access)):
                response = self.client.get("/api/ai/daily-replenishment-operation/sales-trend?sku=SKU-B")

        self.assertEqual(403, response.status_code)
        self.assertIn("店铺权限", response.get_json()["message"])

    def test_sales_trend_rejects_bad_date_range(self):
        access = {"read_stores": {"12"}, "write_stores": set(), "can_write": False, "visible_skus": {"SKU-A"}}
        with patch.object(app_module.permission_manager, "check_user_permission", return_value=(True, "test")):
            with patch.object(operation, "scoped_query_executor", return_value=(lambda sql: [], access)):
                with patch.object(
                    operation,
                    "_settings",
                    return_value={
                        "sales_start": date(2026, 9, 1),
                        "sales_end": date(2026, 9, 10),
                        "sales_source": "付款",
                        "recent_days": 15,
                    },
                ):
                    response = self.client.get(
                        "/api/ai/daily-replenishment-operation/sales-trend?sku=SKU-A&start=2026-01-01&end=2026-03-01"
                    )

        self.assertEqual(400, response.status_code)


if __name__ == "__main__":
    unittest.main()
