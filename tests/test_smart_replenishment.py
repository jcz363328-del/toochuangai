import unittest
from unittest.mock import patch

import smart_replenishment as smart

HEADERS = (
    "运营", "店铺", "分类", "SKU", "总库存", "FBA可售量", "待到货", "销量", "日均销量",
    "K值", "可售量对应的可售天数", "不含待到货量的可售天数", "含待到货量的可售天数",
    "订货量", "订货后可售天数", "到FBA仓日期", "工厂", "备注", "类别", "AB品", "站点",
)


def make_row(*, store="11", category="A", sku="SKU-A", total=100, fba=20, pending=10,
             daily=10, k=None, available=60, remark=None, ab=None):
    values = [None] * len(HEADERS)
    values[1] = store
    values[2] = category
    values[3] = sku
    values[4] = total
    values[5] = fba
    values[6] = pending
    values[8] = daily
    values[9] = k
    values[12] = available
    values[13] = 0
    values[14] = available
    values[17] = remark
    values[19] = ab
    return {"row_number": 2, "values": values}


def empty_context(**overrides):
    context = {
        "history": {},
        "sites": {},
        "margins": {},
        "clearance": set(),
        "ocean": set(),
        "store_cxb": {},
        "company_cxb": 0.0,
        "latest_sales": {},
        "window_days": 15,
        "params": dict(smart.DEFAULT_PARAMS),
    }
    context.update(overrides)
    return context


class SmartReplenishmentTests(unittest.TestCase):
    def test_main_gap_uses_target_days_and_rounds_to_tier(self):
        rows = [make_row(available=60, daily=10)]
        result = smart.suggest(rows, empty_context())["SKU-A"]
        self.assertEqual(200, result["qty"])
        self.assertIn("规则1", result["order_reason"])
        self.assertIn("规则2:计算200->规范200", result["order_reason"])

    def test_sufficient_days_blocks_order(self):
        rows = [make_row(available=100)]
        result = smart.suggest(rows, empty_context())["SKU-A"]
        self.assertEqual(0, result["qty"])
        self.assertIn("综合可售天数充足", result["no_order_reason"])

    def test_low_sales_rule14_zeroes_quantity(self):
        rows = [make_row(available=60, daily=2)]
        history = {"SKU-A": [(None, 2.0), (None, 2.0), (None, 2.0)]}
        result = smart.suggest(rows, empty_context(history=history))["SKU-A"]
        self.assertEqual(0, result["qty"])
        self.assertIn("规则14", result["no_order_reason"])

    def test_public_inventory_remark_blocks_order(self):
        rows = [make_row(remark="【【【不用下单】】】")]
        result = smart.suggest(rows, empty_context())["SKU-A"]
        self.assertEqual(0, result["qty"])
        self.assertIn("规则6", result["no_order_reason"])

    def test_clearance_sku_blocks_order(self):
        rows = [make_row()]
        result = smart.suggest(rows, empty_context(clearance={"SKU-A"}))["SKU-A"]
        self.assertEqual(0, result["qty"])
        self.assertIn("规则7", result["no_order_reason"])

    def test_site_gap_replaces_main_quantity(self):
        rows = [make_row(available=60, daily=10)]
        sites = {"SKU-A": [{"country": "美国", "fba_days": 20.0, "fba_sales": 5.0, "local_inv": 0}]}
        result = smart.suggest(rows, empty_context(sites=sites))["SKU-A"]
        self.assertEqual(300, result["qty"])
        self.assertIn("规则8", result["order_reason"])
        self.assertIn("(辅助)", result["order_reason"])

    def test_small_site_gaps_are_merged_and_need_min_gap(self):
        rows = [make_row(available=60, daily=10)]
        sites = {"SKU-A": [
            {"country": "美国", "fba_days": 60.0, "fba_sales": 10.0, "local_inv": 0},
            {"country": "英国", "fba_days": 64.0, "fba_sales": 2.0, "local_inv": 0},
        ]}
        result = smart.suggest(rows, empty_context(sites=sites))["SKU-A"]
        # 美国缺口 (65-60)*10=50、英国 (65-64)*2=2，合计 52 < 70 → 不下单
        self.assertEqual(0, result["qty"])
        self.assertIn("不足起补缺口", result["no_order_reason"])

    def test_main_gap_below_min_gap_blocks_order(self):
        rows = [make_row(available=70, daily=1.2)]
        history = {"SKU-A": [(None, 6.0)] * 3}  # 日均 6 → 缺口 (80-70)*6=60 <70
        result = smart.suggest(rows, empty_context(history=history))["SKU-A"]
        self.assertEqual(0, result["qty"])
        self.assertIn("主盘面基础缺口", result["no_order_reason"])

    def test_unknown_category_blocks_order(self):
        rows = [make_row(category="D")]
        result = smart.suggest(rows, empty_context())["SKU-A"]
        self.assertEqual(0, result["qty"])
        self.assertIn("未定义补货规则", result["no_order_reason"])

    def test_ab_sufficiency_blocks_b_product(self):
        rows = [
            make_row(sku="SKU-A1", ab="59-1", total=400, fba=100, pending=0, daily=10),
            make_row(sku="SKU-B1", ab="59-2", available=30),
        ]
        results = smart.suggest(rows, empty_context())
        # A 款自身不受规则 5 影响，按主盘面缺口正常补货
        self.assertEqual(200, results["SKU-A1"]["qty"])
        # B 款被同组 A 款拦截
        self.assertEqual(0, results["SKU-B1"]["qty"])
        self.assertIn("规则5", results["SKU-B1"]["no_order_reason"])

    def test_attach_suggestions_writes_quantity_and_days(self):
        rows = [make_row(available=60, daily=10, total=100, pending=10)]
        with patch.object(smart, "build_context", return_value=empty_context()):
            results = smart.attach_suggestions({"recent_days": 15}, rows)
        self.assertEqual(200, results["SKU-A"]["qty"])
        self.assertEqual(200, rows[0]["values"][13])
        self.assertEqual(31, rows[0]["values"][14])  # (100+10+200)/10

    def test_order_comment_explains_zero_and_non_zero(self):
        rows = [make_row(available=60, daily=10)]
        result = smart.suggest(rows, empty_context())["SKU-A"]
        comment = smart.order_comment(result)
        self.assertIn("智能补货建议：200 件", comment)
        blocked = smart.suggest([make_row(available=200)], empty_context())["SKU-A"]
        self.assertIn("不下单原因", smart.order_comment(blocked))


if __name__ == "__main__":
    unittest.main()
