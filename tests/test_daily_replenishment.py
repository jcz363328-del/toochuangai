import tempfile
import unittest
from datetime import date
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook, load_workbook

import app as app_module
import daily_replenishment as daily_module


HEADERS = [
    "运营",
    "店铺",
    "分类",
    "SKU",
    "总库存",
    "FBA可售量",
    "待到货",
    "销量",
    "日均销量",
    "K值",
    "可售量对应的可售天数",
    "不含待到货量的可售天数",
    "含待到货量的可售天数",
    "订货量",
    "订货后可售天数",
    "到FBA仓日期",
    "工厂",
    "备注",
    "类别",
    "AB品",
    "站点",
]


def build_sample_workbook(first_sku: str = "SKU-A") -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "日常补货"
    sheet.append(HEADERS)
    sheet.append(["王丽爽", 2, "C", first_sku, 30, 20, 0, 15, 1, 0.2, 20, 30, 30, 12, 42, None, "52", "旧备注", "簇毛", "A", "1：美国"])
    sheet.append(["李娜", 3, "D", "SKU-B", 5, 0, 0, 6, 0.4, -0.1, 0, 12, 12, -15, -3, None, "48", None, "磁铁", None, "2：英国"])
    sheet.append(["王丽爽", 2, "C", "SKU-C", 100, 80, 0, 10, 0.7, 0, 114, 142, 142, 0, 142, None, "52", None, "簇毛", None, "1：美国"])
    notes = workbook.create_sheet("下单备注")
    notes.append(["SKU", "下单备注"])
    notes.append([first_sku, "先核对供应商交期"])
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def build_sample_dataset(first_sku: str = "SKU-A") -> dict:
    return {
        "columns": list(HEADERS),
        "rows": [
            {"row_number": 2, "values": ["王丽爽", 2, "C", first_sku, 30, 20, 0, 15, 1, 0.2, 20, 30, 30, 12, 42, None, "52", "旧备注", "簇毛", "A", "1：美国"]},
            {"row_number": 3, "values": ["李娜", 3, "D", "SKU-B", 5, 0, 0, 6, 0.4, -0.1, 0, 12, 12, -15, -3, None, "48", None, "磁铁", None, "2：英国"]},
            {"row_number": 4, "values": ["王丽爽", 2, "C", "SKU-C", 100, 80, 0, 10, 0.7, 0, 114, 142, 142, 0, 142, None, "52", None, "簇毛", None, "1：美国"]},
        ],
        "order_notes": {first_sku: "先核对供应商交期"},
        "generation": {
            "generated_at": "2026-09-09 09:00:00",
            "as_of_date": "2026-09-09",
            "sales_start": "2026-08-24",
            "sales_end": "2026-09-07",
            "sales_header": "8.24-9.7销量",
            "recent_days": 15,
            "sales_source": "付款",
            "generator": "Python快照",
        },
    }


class DailyReplenishmentTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_output_dir = app_module.app.config.get("DAILY_REPLENISHMENT_OUTPUT_DIR")
        self.old_source_path = app_module.app.config.get("DAILY_REPLENISHMENT_SOURCE_PATH")
        app_module.app.config.update(
            TESTING=True,
            DAILY_REPLENISHMENT_OUTPUT_DIR=self.temp_dir.name,
            DAILY_REPLENISHMENT_SOURCE_PATH="",
        )
        self.client = app_module.app.test_client()
        with self.client.session_transaction() as flask_session:
            flask_session["feishu_user_id"] = "dev_daily_replenishment_user"
            flask_session["feishu_user_name"] = "测试用户"

    def tearDown(self):
        if self.old_output_dir is None:
            app_module.app.config.pop("DAILY_REPLENISHMENT_OUTPUT_DIR", None)
        else:
            app_module.app.config["DAILY_REPLENISHMENT_OUTPUT_DIR"] = self.old_output_dir
        if self.old_source_path is None:
            app_module.app.config.pop("DAILY_REPLENISHMENT_SOURCE_PATH", None)
        else:
            app_module.app.config["DAILY_REPLENISHMENT_SOURCE_PATH"] = self.old_source_path
        self.temp_dir.cleanup()

    def request_with_permission(self, method, path, **kwargs):
        with patch.object(
            app_module.permission_manager,
            "check_user_permission",
            return_value=(True, "test permission"),
        ):
            return self.client.open(path, method=method, **kwargs)

    def upload_sample(self, first_sku: str = "SKU-A"):
        with patch.object(
            daily_module,
            "generate_database_dataset",
            return_value=build_sample_dataset(first_sku),
        ), patch.object(daily_module, "fetch_database_remarks", return_value={}):
            return self.request_with_permission(
                "POST",
                "/api/ai/daily-replenishment/snapshot/refresh",
                data={"file": (BytesIO(build_sample_workbook(first_sku)), "260907日常补货.xlsm")},
                content_type="multipart/form-data",
            )

    def test_ai_module_card_and_page_are_available(self):
        response = self.request_with_permission("GET", "/ai_modules")
        self.assertEqual(200, response.status_code)
        self.assertIn("<h3>日常补货</h3>", response.get_data(as_text=True))

        page = self.request_with_permission("GET", "/ai/daily-replenishment")
        self.assertEqual(200, page.status_code)
        self.assertIn("no-store", page.headers.get("Cache-Control", ""))
        html = page.get_data(as_text=True)
        self.assertIn("备注保存位置", html)
        self.assertIn("批次1：上午", html)
        self.assertIn("按原表“生成”按钮规则从数据库生成", html)
        self.assertIn("生成今日补货表", html)
        self.assertNotIn('id="prevPage"', html)
        self.assertNotIn('id="nextPage"', html)
        self.assertNotIn("pageSize", html)
        self.assertIn("已一次性展示", html)
        self.assertIn("原表批注", html)
        self.assertIn("mark-clearance", html)
        self.assertIn("mark-low-stock", html)
        self.assertIn('id="fastTooltip"', html)
        self.assertIn("data-tooltip", html)
        self.assertIn("pointerover", html)

    def test_daily_replenishment_routes_require_scoped_permission(self):
        with patch.object(
            app_module.permission_manager,
            "check_user_permission",
            return_value=(False, "test permission denied"),
        ) as check_permission:
            page = self.client.get("/ai/daily-replenishment")

        self.assertEqual(302, page.status_code)
        check_permission.assert_called_once_with(
            "dev_daily_replenishment_user",
            "daily_replenishment",
        )

        with patch.object(
            app_module.permission_manager,
            "check_user_permission",
            return_value=(False, "test permission denied"),
        ) as check_permission:
            api_response = self.client.post("/api/ai/daily-replenishment/generate")

        self.assertEqual(403, api_response.status_code)
        self.assertEqual(
            "daily_replenishment",
            api_response.get_json()["required_function"],
        )
        check_permission.assert_called_once_with(
            "dev_daily_replenishment_user",
            "daily_replenishment",
        )

        with patch.object(
            app_module.permission_manager,
            "check_user_permission",
            return_value=(False, "test permission denied"),
        ) as check_permission:
            refresh_response = self.client.post(
                "/api/ai/daily-replenishment/snapshot/refresh"
            )

        self.assertEqual(403, refresh_response.status_code)
        self.assertEqual(
            "daily_replenishment",
            refresh_response.get_json()["required_function"],
        )
        check_permission.assert_called_once_with(
            "dev_daily_replenishment_user",
            "daily_replenishment",
        )

    def test_refresh_snapshot_runs_python_generator_and_reports_split_counts(self):
        response = self.upload_sample()

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertIn("no-store", response.headers.get("Cache-Control", ""))
        self.assertEqual(3, payload["summary"]["total"])
        self.assertEqual(1, payload["summary"]["morning"])
        self.assertEqual(1, payload["summary"]["afternoon"])
        self.assertEqual("SKU-A", payload["rows"][0]["values"][3])
        self.assertTrue(payload["snapshot"]["available"])
        self.assertTrue(payload["snapshot"]["can_refresh"])
        self.assertEqual("2026-09-07", payload["generation"]["sales_end"])

    def test_generate_requires_today_snapshot(self):
        response = self.request_with_permission(
            "POST",
            "/api/ai/daily-replenishment/generate",
        )

        self.assertEqual(400, response.status_code)
        self.assertIn("今日快照尚未生成", response.get_json()["message"])

    def test_snapshot_can_refresh_repeatedly_and_generate_reads_latest_snapshot(self):
        self.assertEqual(200, self.upload_sample().status_code)

        second_refresh = self.upload_sample("SKU-NEW")

        self.assertEqual(200, second_refresh.status_code)
        self.assertIn("已重新刷新", second_refresh.get_json()["message"])
        self.assertTrue(second_refresh.get_json()["snapshot"]["can_refresh"])

        generated = self.request_with_permission(
            "POST",
            "/api/ai/daily-replenishment/generate",
        )
        self.assertEqual(200, generated.status_code)
        self.assertEqual("SKU-NEW", generated.get_json()["rows"][0]["values"][3])

    def test_database_remarks_are_captured_only_when_snapshot_refreshes(self):
        with patch.object(
            daily_module,
            "generate_database_dataset",
            return_value=build_sample_dataset(),
        ), patch.object(
            daily_module,
            "fetch_database_remarks",
            return_value={"SKU-A": "快照备注"},
        ) as fetch_remarks:
            refreshed = self.request_with_permission(
                "POST",
                "/api/ai/daily-replenishment/snapshot/refresh",
                data={
                    "file": (
                        BytesIO(build_sample_workbook()),
                        "260908日常补货.xlsm",
                    )
                },
                content_type="multipart/form-data",
            )

        self.assertEqual(200, refreshed.status_code)
        self.assertEqual("快照备注", refreshed.get_json()["rows"][0]["values"][17])
        fetch_remarks.assert_called_once_with()

        with patch.object(
            daily_module,
            "fetch_database_remarks",
            side_effect=AssertionError("读取快照时不应再查数据库"),
        ):
            generated = self.request_with_permission(
                "POST",
                "/api/ai/daily-replenishment/generate",
            )

        self.assertEqual(200, generated.status_code)
        self.assertEqual("快照备注", generated.get_json()["rows"][0]["values"][17])

    def test_python_generator_uses_vba_date_window_and_calculations(self):
        queries = []

        def fake_query(sql):
            queries.append(sql)
            if "daily_replenishment:sites" in sql:
                return [("SKU-A", "美国")]
            if "daily_replenishment:comments_" in sql:
                return []
            return [
                (
                    "王丽爽",
                    2,
                    "C",
                    "SKU-A",
                    100,
                    20,
                    10,
                    40,
                    -0.125,
                    date(2026, 9, 1),
                    None,
                    date(2026, 8, 28),
                    "52",
                    "SKU-A",
                    "簇毛",
                    "3-1",
                )
            ]

        with app_module.app.app_context():
            settings = daily_module.get_generation_settings(
                as_of_date=date(2026, 9, 9),
                recent_days=15,
                sales_source="付款",
            )
            dataset = daily_module.generate_database_dataset(
                settings,
                query_executor=fake_query,
            )

        self.assertIn("RiQi BETWEEN '2026-08-24' AND '2026-09-07'", queries[0])
        self.assertIn("FROM v_XiaoShouLiang", queries[0])
        self.assertEqual("8.24-9.7销量", dataset["columns"][7])
        self.assertEqual("2026-09-07", dataset["generation"]["sales_end"])
        values = dataset["rows"][0]["values"]
        self.assertEqual(5.0, values[8])
        self.assertEqual(4, values[10])
        self.assertEqual(20, values[11])
        self.assertEqual(22, values[12])
        self.assertEqual("1：美国", values[20])

    def test_snapshot_round_trip_preserves_cell_comments(self):
        dataset = build_sample_dataset()
        dataset["header_comments"] = {"4": "总库存表头批注"}
        dataset["rows"][0]["comments"] = {
            "4": "本地：10\nFBA：20",
            "13": "最近 3 天的采购计划",
        }
        dataset["rows"][0]["styles"] = {
            "3": ["mark-only-local"],
            "4": ["mark-half-finished"],
            "13": ["mark-falling", "mark-recent-plan"],
        }
        destination = Path(self.temp_dir.name) / "批注快照.xlsx"

        with app_module.app.app_context():
            daily_module._save_dataset_workbook(dataset, destination)
            loaded = daily_module.load_daily_replenishment(destination)

        self.assertEqual("总库存表头批注", loaded["header_comments"]["4"])
        self.assertEqual("本地：10\nFBA：20", loaded["rows"][0]["comments"]["4"])
        self.assertEqual("最近 3 天的采购计划", loaded["rows"][0]["comments"]["13"])
        self.assertEqual(["mark-half-finished"], loaded["rows"][0]["styles"]["4"])
        self.assertEqual(
            ["mark-falling", "mark-recent-plan"],
            loaded["rows"][0]["styles"]["13"],
        )

        workbook = load_workbook(destination, read_only=False, data_only=True)
        try:
            self.assertEqual("总库存表头批注", workbook["日常补货"]["E1"].comment.text)
            self.assertEqual("本地：10\nFBA：20", workbook["日常补货"]["E2"].comment.text)
            self.assertIn("_单元格批注", workbook.sheetnames)
            self.assertEqual("hidden", workbook["_单元格批注"].sheet_state)
            self.assertIn("_单元格样式", workbook.sheetnames)
            self.assertEqual("hidden", workbook["_单元格样式"].sheet_state)
            self.assertEqual("00FFFF00", workbook["日常补货"]["E2"].fill.fgColor.rgb)
            self.assertEqual("00000000", workbook["日常补货"]["N2"].fill.fgColor.rgb)
            self.assertTrue(workbook["日常补货"]["N2"].font.italic)
        finally:
            workbook.close()

    def test_vba_marking_rules_are_serialized_as_cell_styles(self):
        dataset = build_sample_dataset()
        row = dataset["rows"][0]
        row["values"][8] = 5
        row["values"][9] = 0.5
        row["values"][10] = 20
        row["values"][12] = 20
        comments = {
            "SKU-A": {
                "4": "本地：30\n\n半成品：SKU-X，数量：5",
                "5": "近120天海运在途信息：\n美国，2026-09-01，50-0=50，8天",
                "6": "2026-08-20，PO-1，52，30-0=30，采购",
                "7": "此为最近 3 天的销量",
                "8": "近3天日均：6\n近7天日均：4",
                "13": "最近 3 天的采购计划：\n2026-09-09，20，JH-1\n过去15天，有 10 天K值<=0，谨慎下单",
                "14": "最近 60 天找运营下单：\n09.08，20->10",
                "15": "首次付款日期：2026-09-01",
            }
        }

        def fake_query(sql):
            if "comments_style_status" in sql:
                return [("clearance", "SKU-A"), ("ocean", "SKU-A")]
            if "comments_style_new_local" in sql:
                return [("SKU-A", date(2026, 9, 2))]
            if "comments_style_surge" in sql:
                return [("SKU-A", date(2026, 9, 7), 8, 3, 2.7)]
            return []

        with app_module.app.app_context():
            settings = daily_module.get_generation_settings(as_of_date=date(2026, 9, 9))
            styles = daily_module.generate_database_styles(
                settings,
                dataset["rows"],
                comments,
                query_executor=fake_query,
            )

        self.assertIn("mark-clearance", styles["SKU-A"]["0"])
        self.assertIn("mark-new-local", styles["SKU-A"]["0"])
        self.assertIn("mark-ocean", styles["SKU-A"]["3"])
        self.assertIn("mark-only-local", styles["SKU-A"]["3"])
        self.assertIn("mark-half-finished", styles["SKU-A"]["4"])
        self.assertIn("mark-overdue", styles["SKU-A"]["6"])
        self.assertIn("mark-recent-sales", styles["SKU-A"]["7"])
        self.assertIn("mark-sales-rise", styles["SKU-A"]["8"])
        self.assertIn("mark-surge", styles["SKU-A"]["8"])
        self.assertIn("mark-variation", styles["SKU-A"]["9"])
        self.assertIn("mark-low-stock", styles["SKU-A"]["10"])
        self.assertIn("mark-falling", styles["SKU-A"]["13"])
        self.assertIn("mark-recent-plan", styles["SKU-A"]["13"])
        self.assertIn("mark-reduced-order", styles["SKU-A"]["14"])
        self.assertIn("mark-new-product", styles["SKU-A"]["15"])

    def test_database_remarks_match_the_workbook_refresh_format(self):
        with patch.object(
            daily_module,
            "sf_db",
            side_effect=[
                [("SKU-A", "2026-09-06", "交期调整")],
                [("SKU-A", "2026-09-01", "主推款")],
            ],
        ):
            remarks = daily_module.fetch_database_remarks()

        self.assertEqual("[26-09-06]交期调整\n[26-09-01]重点品：主推款", remarks["SKU-A"])

    def test_remarks_save_capture_to_configured_directory(self):
        self.assertEqual(200, self.upload_sample().status_code)

        response = self.request_with_permission(
            "POST",
            "/api/ai/daily-replenishment/remarks",
            json={
                "edits": [
                    {
                        "row_number": 2,
                        "sku": "SKU-A",
                        "order_quantity": "18",
                        "remark": "网页备注",
                    }
                ],
            },
        )

        self.assertEqual(200, response.status_code)
        payload = response.get_json()
        saved_path = Path(payload["saved_path"])
        self.assertEqual(Path(self.temp_dir.name).resolve(), saved_path.parent.resolve())
        self.assertTrue(saved_path.is_file())
        workbook = load_workbook(saved_path, read_only=True, data_only=True)
        try:
            sheet = workbook["日常补货"]
            self.assertEqual(18, sheet["N2"].value)
            self.assertEqual("网页备注", sheet["R2"].value)
        finally:
            workbook.close()

        generated = self.request_with_permission(
            "POST",
            "/api/ai/daily-replenishment/generate",
        )
        self.assertEqual(200, generated.status_code)
        self.assertEqual(18, generated.get_json()["rows"][0]["values"][13])

    def test_split_uses_macro_batch_thresholds_and_operator_tabs(self):
        self.assertEqual(200, self.upload_sample().status_code)

        morning = self.request_with_permission(
            "POST",
            "/api/ai/daily-replenishment/split",
            json={"batch": 1, "edits": []},
        )
        self.assertEqual(200, morning.status_code)
        self.assertEqual("1", morning.headers["X-Daily-Replenishment-Rows"])
        workbook = load_workbook(BytesIO(morning.get_data()), read_only=True, data_only=True)
        try:
            self.assertIn("拆分汇总", workbook.sheetnames)
            self.assertIn("王丽爽", workbook.sheetnames)
            self.assertEqual("SKU-A", workbook["拆分汇总"]["D2"].value)
            self.assertEqual("先核对供应商交期", workbook["拆分汇总"]["Q2"].value)
        finally:
            workbook.close()

        afternoon = self.request_with_permission(
            "POST",
            "/api/ai/daily-replenishment/split",
            json={"batch": 2, "edits": []},
        )
        self.assertEqual(200, afternoon.status_code)
        workbook = load_workbook(BytesIO(afternoon.get_data()), read_only=True, data_only=True)
        try:
            self.assertIn("李娜", workbook.sheetnames)
            self.assertEqual("SKU-B", workbook["拆分汇总"]["D2"].value)
        finally:
            workbook.close()


if __name__ == "__main__":
    unittest.main()
