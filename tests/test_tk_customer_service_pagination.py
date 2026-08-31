from __future__ import annotations

import ast
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, jsonify, request


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"
TEMPLATE_PATH = ROOT / "templates" / "tk_customer_service.html"


def _load_query_helpers(fake_sf_db):
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    helper_names = {
        "_tk_customer_service_join_key",
        "_tk_customer_service_fill_complete_tracking_numbers",
        "_tk_customer_service_filter_sql",
        "_tk_customer_service_query_total",
        "_tk_customer_service_query_shops",
        "_tk_customer_service_query_rows",
    }
    selected_nodes = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(
                isinstance(target, ast.Name)
                and target.id == "_TK_CUSTOMER_SERVICE_PAGE_SIZE"
                for target in node.targets
            ):
                selected_nodes.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in helper_names:
            selected_nodes.append(node)
    module = ast.Module(body=selected_nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {"sf_db": fake_sf_db, "datetime": datetime}
    exec(compile(module, str(APP_PATH), "exec"), namespace)
    return namespace


def _load_list_endpoint(namespace):
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    endpoint_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "api_tk_customer_service_list"
    )
    endpoint_node.decorator_list = []
    module = ast.Module(body=[endpoint_node], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(APP_PATH), "exec"), namespace)
    return namespace["api_tk_customer_service_list"]


def _load_export_row_builder(namespace):
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    helper_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_tk_customer_service_build_export_rows"
    )
    module = ast.Module(body=[helper_node], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(APP_PATH), "exec"), namespace)
    return namespace["_tk_customer_service_build_export_rows"]


class TkCustomerServicePaginationTests(unittest.TestCase):
    def test_complete_tracking_numbers_prefer_exact_sku_and_list_all_fallbacks(self):
        source_rows = [
            ("ORDER-1", "SKU-A", "TRACK-1"),
            ("ORDER-1", "SKU-A", "TRACK-2"),
            ("ORDER-1", "SKU-B", "TRACK-OTHER-SKU"),
            ("ORDER-2", "SOURCE-SKU", "TRACK-FALLBACK-1"),
            ("ORDER-2", "SOURCE-SKU", "TRACK-FALLBACK-2"),
            ("ORDER-2", "SOURCE-SKU", "track-fallback-2"),
        ]
        helpers = _load_query_helpers(lambda _sql: source_rows)
        items = [
            {
                "FaYangDingDanHao": "order-1",
                "SKU": "sku-a",
                "GenZongHao": "TRACK-2",
            },
            {
                "FaYangDingDanHao": "ORDER-2",
                "SKU": "DIFFERENT-SKU",
                "GenZongHao": "",
            },
        ]

        helpers["_tk_customer_service_fill_complete_tracking_numbers"](items)

        self.assertEqual(items[0]["GenZongHao"], "TRACK-1 / TRACK-2")
        self.assertEqual(
            items[1]["GenZongHao"],
            "TRACK-FALLBACK-1 / TRACK-FALLBACK-2",
        )

    def test_list_query_pages_at_database_layer_in_fixed_batches(self):
        captured = []

        def fake_sf_db(sql):
            captured.append(sql)
            return []

        helpers = _load_query_helpers(fake_sf_db)
        helpers["_tk_customer_service_query_rows"](
            "2026-07-01",
            "2026-07-29",
            page=2,
        )

        sql = captured[-1]
        self.assertIn("WITH page_rows AS", sql)
        self.assertIn("OFFSET 100 ROWS FETCH NEXT 100 ROWS ONLY", sql)
        self.assertIn("FROM page_rows", sql)
        self.assertIn("LEFT JOIN (", sql)
        self.assertIn("WHERE EXISTS", sql)

    def test_export_query_stays_unpaged(self):
        captured = []

        def fake_sf_db(sql):
            captured.append(sql)
            return []

        helpers = _load_query_helpers(fake_sf_db)
        helpers["_tk_customer_service_query_rows"](
            "2026-07-01",
            "2026-07-29",
        )

        sql = captured[-1]
        self.assertNotIn("OFFSET", sql)
        self.assertNotIn("FETCH NEXT", sql)
        self.assertIn("FROM TK_WangHong_HeZuo hz", sql)

    def test_export_keeps_invalid_address_rows_in_primary_sheet(self):
        def fake_parse(raw_address):
            return {"receiver": "" if raw_address == "bad" else "Alice"}

        def fake_prepare(raw_address, _parsed):
            return {
                "receiver": "" if raw_address == "bad" else "Alice",
                "address1": "" if raw_address == "bad" else "1 Main St",
                "city": "" if raw_address == "bad" else "Boston",
                "state": "MA",
                "country": "US",
                "zipcode": "" if raw_address == "bad" else "02108",
                "phone": "0000000000",
            }

        def fake_validate(raw_address, _parsed, _order_no):
            return ["未识别地址"] if raw_address == "bad" else []

        build_rows = _load_export_row_builder({
            "_tk_parse_wanghong_address": fake_parse,
            "_tk_prepare_export_contact_fields": fake_prepare,
            "_tk_validate_export_address": fake_validate,
        })
        items = [
            {"FaYangDingDanHao": "ORDER-1", "SKU": "SKU-1", "wanghongdizhi": "good"},
            {"FaYangDingDanHao": "ORDER-2", "SKU": "SKU-2", "wanghongdizhi": "bad"},
        ]

        export_rows, error_rows = build_rows(items)

        self.assertEqual(len(export_rows), 2)
        self.assertEqual([row["*订单号"] for row in export_rows], ["ORDER-1", "ORDER-2"])
        self.assertEqual(len(error_rows), 1)
        self.assertEqual(error_rows[0]["订单号"], "ORDER-2")

    def test_tracking_fallback_requires_one_unique_order_tracking_number(self):
        captured = []

        def fake_sf_db(sql):
            captured.append(sql)
            return []

        helpers = _load_query_helpers(fake_sf_db)
        helpers["_tk_customer_service_query_rows"](
            "2026-07-01",
            "2026-07-29",
            page=1,
        )

        sql = captured[-1]
        self.assertIn("dd_exact.GenZongHao", sql)
        self.assertIn("dd_order.GenZongHao", sql)
        self.assertIn(
            "COALESCE(NULLIF(dd_exact.GenZongHao, ''), "
            "dd_order.GenZongHao, '') AS GenZongHao",
            sql,
        )
        self.assertIn("HAVING COUNT(DISTINCT", sql)
        self.assertIn("= 1", sql)

    def test_date_filter_is_sargable_and_escapes_values(self):
        helpers = _load_query_helpers(lambda _sql: [])
        where_sql = helpers["_tk_customer_service_filter_sql"](
            "2026-07-01",
            "2026-07-29",
            shop_names=["A'店"],
        )

        self.assertIn("hz.DaoRuShiJian >=", where_sql)
        self.assertIn("hz.DaoRuShiJian <", where_sql)
        self.assertNotIn("CAST(hz.DaoRuShiJian AS date)", where_sql)
        self.assertIn("'A''店'", where_sql)

    def test_shop_lookup_uses_a_distinct_shop_query(self):
        captured = []

        def fake_sf_db(sql):
            captured.append(sql)
            return ["A店", "B店"]

        helpers = _load_query_helpers(fake_sf_db)
        shops = helpers["_tk_customer_service_query_shops"](
            "2026-07-01",
            "2026-07-29",
        )

        self.assertEqual(shops, ["A店", "B店"])
        self.assertEqual(len(captured), 1)
        self.assertIn("SELECT DISTINCT", captured[0])
        self.assertNotIn("TK_DingDan_shouhou", captured[0])

    def test_frontend_sends_page_and_renders_pagination(self):
        template = TEMPLATE_PATH.read_text(encoding="utf-8")

        self.assertIn("const PAGE_SIZE = 100;", template)
        self.assertIn("params.set('page'", template)
        self.assertIn('id="paginationMeta"', template)
        self.assertIn('id="pageNumbers"', template)
        self.assertIn("function goToPage(page)", template)

    def test_list_endpoint_returns_and_clamps_pagination_metadata(self):
        flask_app = Flask(__name__)
        captured = {}

        def fake_rows(*_args, **kwargs):
            captured.update(kwargs)
            return [{"ID": 201}]

        endpoint = _load_list_endpoint(
            {
                "datetime": datetime,
                "timedelta": timedelta,
                "request": request,
                "jsonify": jsonify,
                "_TK_CUSTOMER_SERVICE_PAGE_SIZE": 100,
                "_tk_parse_shop_names_from_request": lambda: [],
                "_tk_parse_importers_from_request": lambda: [],
                "_tk_parse_order_nos_from_request": lambda: [],
                "_tk_customer_service_query_total": lambda *_args: 201,
                "_tk_customer_service_query_rows": fake_rows,
            }
        )

        with flask_app.test_request_context(
            "/api/tk_customer_service/list"
            "?start_date=2026-07-01&end_date=2026-07-29&page=99"
        ):
            payload = endpoint().get_json()

        self.assertTrue(payload["success"])
        self.assertEqual(payload["page"], 3)
        self.assertEqual(payload["page_size"], 100)
        self.assertEqual(payload["total"], 201)
        self.assertEqual(payload["total_pages"], 3)
        self.assertEqual(captured["page"], 3)
        self.assertEqual(captured["page_size"], 100)


if __name__ == "__main__":
    unittest.main()
