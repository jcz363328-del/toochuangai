import unittest

from business_analysis_access import (
    force_business_analysis_query_params,
    prepare_business_analysis_payload,
    resolve_business_analysis_scope,
)


class BusinessAnalysisAccessTests(unittest.TestCase):
    def test_department_leader_and_member_scopes(self):
        department = [{"department_id": "od-op1", "name": "运营一部", "status": "active"}]

        leader = resolve_business_analysis_scope("ou-leader", "周雪", department)
        member = resolve_business_analysis_scope("ou-member", "张三", department)

        self.assertEqual(leader["role"], "department_leader")
        self.assertTrue(leader["canViewAmounts"])
        self.assertIsNone(leader["operator"])
        self.assertEqual(member["role"], "member")
        self.assertFalse(member["canViewAmounts"])
        self.assertEqual(member["operator"], "张三")

    def test_dynamic_leader_and_operation_seven_alias(self):
        department = [{"department_id": "od-op7", "name": "运营七部", "status": "active"}]

        dynamic = resolve_business_analysis_scope(
            "ou-dynamic",
            "其他姓名",
            department,
            leader_id_getter=lambda department_id: "ou-dynamic",
        )
        alias = resolve_business_analysis_scope("ou-alias", "侯瑞欣", department)

        self.assertEqual(dynamic["role"], "department_leader")
        self.assertEqual(alias["role"], "department_leader")

    def test_query_scope_cannot_be_overridden_by_browser(self):
        scope = {"department": "运营二部", "operator": "李四"}
        params = force_business_analysis_query_params(
            [("period", "2026-08"), ("department", "运营一部"), ("operator", "别人")],
            scope,
        )

        self.assertEqual(
            params,
            [("period", "2026-08"), ("department", "运营二部"), ("operator", "李四")],
        )

    def test_non_operation_user_gets_ratio_only_scope(self):
        scope = resolve_business_analysis_scope(
            "ou-ai",
            "AI用户",
            [{"department_id": "od-ai", "name": "AI部", "status": "active"}],
        )

        self.assertEqual(scope["role"], "ratio_viewer")
        self.assertFalse(scope["canViewAmounts"])
        self.assertEqual(
            force_business_analysis_query_params([("period", "2026-08")], scope),
            [("period", "2026-08"), ("department", "__ratio_only__")],
        )

    def test_payload_is_row_scoped_and_category_amounts_are_redacted(self):
        payload = {
            "data": {
                "meta": {
                    "sourceTotals": {"sales": 999},
                    "curatedTotals": {"sales": 999},
                    "reconciliation": {"sales": {"source": 999}},
                },
                "performance": {
                    "stores": [
                        {"store": 1, "department": "运营一部", "operator": "张三"},
                        {"store": 2, "department": "运营一部", "operator": "别人"},
                    ],
                    "periodRows": [
                        {"store": 1, "department": "运营一部", "operator": "张三"},
                        {"store": 2, "department": "运营一部", "operator": "别人"},
                    ],
                    "departments": [{"name": "运营一部"}, {"name": "运营二部"}],
                },
                "slowMoving": [
                    {"store": 1, "department": "运营一部", "operator": "张三"},
                    {"store": 2, "department": "运营一部", "operator": "别人"},
                ],
                "shipping": [],
                "newProductOrders": [],
                "unshipped": [],
                "magnetDaily": [{"date": "2026-08-01", "sales": 100}],
                "categorySegmentsByPeriod": {"2026-08": {"categories": []}},
                "categorySegments": {
                    "categories": [{
                        "company": {
                            "current": {"sales": 300, "usSales": 120},
                            "previous": {"sales": 200, "usSales": 50},
                        },
                        "industry": {},
                        "shareDaily": [],
                        "departments": [
                            {
                                "department": "运营一部",
                                "currentSales": 100,
                                "previousSales": 80,
                                "currentUsSales": 40,
                                "previousUsSales": 20,
                            },
                            {
                                "department": "运营二部",
                                "currentSales": 200,
                                "previousSales": 120,
                                "currentUsSales": 80,
                                "previousUsSales": 30,
                            },
                        ],
                    }],
                },
            },
            "formulas": [],
        }
        scope = {
            "role": "member",
            "department": "运营一部",
            "operator": "张三",
            "userName": "张三",
            "canViewAmounts": False,
        }

        result = prepare_business_analysis_payload(payload, scope, "2026-08")
        data = result["data"]
        category = data["categorySegments"]["categories"][0]

        self.assertEqual([row["store"] for row in data["performance"]["stores"]], [1])
        self.assertEqual([row["store"] for row in data["slowMoving"]], [1])
        self.assertEqual(data["magnetDaily"], [])
        self.assertNotIn("categorySegmentsByPeriod", data)
        self.assertNotIn("sourceTotals", data["meta"])
        self.assertEqual(category["company"]["current"]["sales"], 0)
        self.assertEqual(category["departments"][0]["currentSales"], 0)
        self.assertAlmostEqual(category["ratios"]["company"]["currentUsShare"], 0.4)
        self.assertAlmostEqual(category["ratios"]["departments"][0]["currentShare"], 1 / 3)
        self.assertEqual(data["meta"]["accessScope"]["role"], "member")


if __name__ == "__main__":
    unittest.main()
