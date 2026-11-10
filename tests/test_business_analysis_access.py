import unittest

from business_analysis_access import (
    force_business_analysis_query_params,
    merge_business_analysis_store_tier_snapshot,
    prepare_business_analysis_payload,
    resolve_business_analysis_scope,
)


class BusinessAnalysisAccessTests(unittest.TestCase):
    def test_snapshot_rows_can_use_leader_as_department_fallback(self):
        payload = {
            "data": {
                "meta": {},
                "performance": {
                    "stores": [{"store": 4, "leader": "大张雯", "operator": "刘蓉蓉"}],
                    "periodRows": [{"store": 4, "leader": "大张雯", "operator": "刘蓉蓉"}],
                    "departments": [],
                },
                "storeTiers": [{"store": 4, "leader": "大张雯", "operator": "刘蓉蓉", "tier": "钻3"}],
                "slowMoving": [],
                "shipping": [],
                "newProductOrders": [],
                "unshipped": [],
                "magnetDaily": [],
                "categorySegments": {"categories": []},
            },
            "formulas": [],
        }
        scope = {
            "role": "department_leader",
            "department": "运营三部",
            "operator": None,
            "userName": "大张雯",
            "canViewAmounts": True,
        }

        result = prepare_business_analysis_payload(payload, scope, "2026-08")

        self.assertEqual([row["store"] for row in result["data"]["performance"]["stores"]], [4])
        self.assertEqual([row["store"] for row in result["data"]["performance"]["periodRows"]], [4])
        self.assertEqual([row["store"] for row in result["data"]["storeTiers"]], [4])

    def test_store_tier_snapshot_merge_hydrates_rows_stores_and_meta(self):
        data = {
            "performance": {
                "stores": [
                    {"store": 4, "tier": None},
                    {"store": 99, "tier": None},
                ]
            },
            "meta": {"rowCounts": {"stores": 2}},
        }
        snapshot = {
            "effectiveDate": "2026-09-20",
            "rows": [
                {
                    "store": 4,
                    "department": "大张雯",
                    "operator": "刘蓉蓉",
                    "tier": "钻3",
                },
                {
                    "store": 21,
                    "department": "王钰媛",
                    "operator": "李娜",
                    "tier": "金9",
                },
            ],
        }

        result = merge_business_analysis_store_tier_snapshot(
            data,
            snapshot,
            warning="NODE_API_STARTING",
        )

        self.assertNotIn("storeTiers", data)
        self.assertEqual(
            [
                (row["store"], row["department"], row["tier"], row["tierRank"], row["effectiveDate"])
                for row in result["storeTiers"]
            ],
            [
                (4, "运营三部", "钻3", 19, "2026-09-20"),
                (21, "运营二部", "金9", 16, "2026-09-20"),
            ],
        )
        self.assertEqual(result["performance"]["stores"][0]["tier"], "钻3")
        self.assertEqual(result["performance"]["stores"][0]["tierRank"], 19)
        self.assertIsNone(result["performance"]["stores"][1]["tier"])
        self.assertEqual(result["meta"]["rowCounts"]["storeTiers"], 2)
        self.assertEqual(
            result["meta"]["storeTier"],
            {
                "effectiveDate": "2026-09-20",
                "updatedAt": "2026-09-20T00:00:00+08:00",
                "source": "workbook-snapshot",
                "stale": True,
                "warning": "NODE_API_STARTING",
            },
        )

    def test_zhou_juncheng_has_full_business_analysis_scope(self):
        scope = resolve_business_analysis_scope(
            "ou-zhou-juncheng",
            "周俊成",
            [{"department_id": "od-ai", "name": "AI部", "status": "active"}],
            full_access=True,
        )

        self.assertEqual(scope["role"], "business_owner")
        self.assertTrue(scope["canViewAmounts"])
        self.assertIsNone(scope["department"])
        self.assertEqual(
            force_business_analysis_query_params(
                [("period", "2026-08"), ("department", "运营一部"), ("operator", "别人")],
                scope,
            ),
            [("period", "2026-08")],
        )

    def test_full_scope_requires_database_permission_flag(self):
        scope = resolve_business_analysis_scope(
            "ou-zhou-juncheng",
            "周俊成",
            [{"department_id": "od-ai", "name": "AI部", "status": "active"}],
        )

        self.assertEqual(scope["role"], "ratio_viewer")
        self.assertFalse(scope["canViewAmounts"])

    def test_guo_ting_has_operation_one_leader_scope_without_company_wide_access(self):
        scope = resolve_business_analysis_scope(
            "ou-guo-ting",
            "郭婷",
            [{"department_id": "od-operation-1", "name": "运营一部", "status": "active"}],
        )

        self.assertEqual(scope["role"], "department_leader")
        self.assertEqual(scope["department"], "运营一部")
        self.assertIsNone(scope["operator"])
        self.assertTrue(scope["canViewAmounts"])
        self.assertEqual(
            force_business_analysis_query_params(
                [("period", "2026-09"), ("department", "运营二部"), ("operator", "别人")],
                scope,
            ),
            [("period", "2026-09"), ("department", "运营一部")],
        )

    def test_full_owner_payload_keeps_rows_amounts_and_audit_meta(self):
        payload = {
            "data": {
                "meta": {"sourceTotals": {"sales": 300}},
                "performance": {
                    "stores": [
                        {"store": 1, "department": "运营一部", "operator": "甲", "sales": 100},
                        {"store": 2, "department": "运营二部", "operator": "乙", "sales": 200},
                    ]
                },
                "categorySegments": {
                    "categories": [{
                        "company": {
                            "current": {"sales": 300, "usSales": 120},
                            "previous": {"sales": 200, "usSales": 60},
                            "yearAgo": {"sales": 150, "usSales": 45},
                        },
                        "departments": [],
                    }]
                },
            },
            "formulas": [{"unit": "CNY", "value": 300}],
        }
        scope = {
            "role": "business_owner",
            "department": None,
            "operator": None,
            "userName": "周俊成",
            "canViewAmounts": True,
        }

        result = prepare_business_analysis_payload(payload, scope, "2026-08")

        self.assertEqual(len(result["data"]["performance"]["stores"]), 2)
        self.assertEqual(result["data"]["categorySegments"]["categories"][0]["company"]["current"]["sales"], 300)
        company_ratios = result["data"]["categorySegments"]["categories"][0]["ratios"]["company"]
        self.assertAlmostEqual(company_ratios["dailyMom"], 0.5)
        self.assertAlmostEqual(company_ratios["dailyYoy"], 1.0)
        self.assertAlmostEqual(company_ratios["currentUsShare"], 0.4)
        self.assertEqual(result["formulas"][0]["value"], 300)
        self.assertEqual(result["data"]["meta"]["sourceTotals"]["sales"], 300)
        self.assertEqual(result["data"]["meta"]["accessScope"]["role"], "business_owner")

    def test_legacy_live_category_payload_uses_same_period_year_ago_snapshot(self):
        payload = {
            "data": {
                "meta": {},
                "categorySegments": {"categories": [{
                    "key": "paired",
                    "company": {
                        "current": {"sales": 310, "usSales": 155},
                        "previous": {"sales": 300, "usSales": 150},
                    },
                    "departments": [{
                        "department": "运营一部",
                        "currentSales": 310,
                        "previousSales": 300,
                        "currentUsSales": 155,
                        "previousUsSales": 150,
                    }],
                }]},
            },
            "formulas": [],
        }
        fallback = {"categories": [{
            "key": "paired",
            "company": {"yearAgo": {"sales": 248, "usSales": 124}},
            "departments": [{
                "department": "运营一部",
                "yearAgoSales": 248,
                "yearAgoUsSales": 124,
            }],
        }]}
        scope = {
            "role": "business_owner",
            "department": None,
            "operator": None,
            "userName": "周俊成",
            "canViewAmounts": True,
        }

        result = prepare_business_analysis_payload(
            payload,
            scope,
            "2026-08",
            category_fallback=fallback,
        )
        category = result["data"]["categorySegments"]["categories"][0]

        self.assertEqual(category["company"]["yearAgo"]["sales"], 248)
        self.assertEqual(category["departments"][0]["yearAgoSales"], 248)
        self.assertAlmostEqual(category["ratios"]["company"]["dailyYoy"], 0.25)
        self.assertAlmostEqual(category["ratios"]["company"]["yearAgoUsShare"], 0.5)

    def test_requested_period_selects_matching_category_snapshot(self):
        payload = {
            "data": {
                "meta": {},
                "categorySegments": {"categories": []},
                "categorySegmentsByPeriod": {
                    "2026-08": {"categories": [{
                        "key": "paired",
                        "company": {
                            "current": {"sales": 310, "usSales": 155},
                            "previous": {"sales": 300, "usSales": 150},
                            "yearAgo": {"sales": 248, "usSales": 124},
                        },
                        "departments": [],
                    }]},
                },
            },
            "formulas": [],
        }
        scope = {
            "role": "business_owner",
            "department": None,
            "operator": None,
            "userName": "周俊成",
            "canViewAmounts": True,
        }

        result = prepare_business_analysis_payload(payload, scope, "2026-08")

        self.assertEqual(result["data"]["categorySegments"]["categories"][0]["company"]["yearAgo"]["sales"], 248)
        self.assertNotIn("categorySegmentsByPeriod", result["data"])

    def test_department_leader_and_member_scopes(self):
        department = [{"department_id": "od-op1", "name": "运营一部", "status": "active"}]

        leader = resolve_business_analysis_scope("ou-leader", "周雪", department)
        member = resolve_business_analysis_scope("ou-member", "张三", department)

        self.assertEqual(leader["role"], "department_leader")
        self.assertTrue(leader["canViewAmounts"])
        self.assertIsNone(leader["operator"])
        self.assertEqual(member["role"], "member")
        self.assertTrue(member["canViewAmounts"])
        self.assertEqual(member["operator"], "张三")

    def test_member_can_view_amounts_only_for_own_stores(self):
        payload = {
            "data": {
                "meta": {},
                "performance": {
                    "stores": [
                        {"store": 1, "department": "运营一部", "operator": "张三", "sales": 1200},
                        {"store": 2, "department": "运营一部", "operator": "别人", "sales": 9800},
                    ],
                    "periodRows": [],
                    "departments": [],
                },
                "slowMoving": [], "shipping": [], "newProductOrders": [], "unshipped": [],
                "storeTiers": [], "magnetDaily": [],
                "categorySegments": {"categories": [{
                    "company": {
                        "current": {"sales": 11000, "usSales": 5000},
                        "previous": {"sales": 10000, "usSales": 4000},
                        "yearAgo": {"sales": 9000, "usSales": 3000},
                    },
                    "departments": [], "industry": {}, "shareDaily": [],
                }]},
            },
            "formulas": [],
        }
        scope = {
            "role": "member", "department": "运营一部", "operator": "张三",
            "userName": "张三", "canViewAmounts": True,
        }

        result = prepare_business_analysis_payload(payload, scope, "2026-08")
        stores = result["data"]["performance"]["stores"]
        category = result["data"]["categorySegments"]["categories"][0]

        self.assertEqual(stores, [{"store": 1, "department": "运营一部", "operator": "张三", "sales": 1200}])
        self.assertTrue(result["data"]["meta"]["accessScope"]["canViewAmounts"])
        self.assertIsNone(category["ratios"]["company"]["currentSales"])
        self.assertEqual(category["company"]["current"]["sales"], 0)

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

    def test_rotation_leaders_use_delegated_department_leader_scope(self):
        cases = {
            "郭婷": "运营一部",
            "王淑雯": "运营二部",
            "柳琳": "运营三部",
            "刘星辰": "运营六部",
            "张彦微": "运营七部",
        }
        for name, expected_department in cases.items():
            with self.subTest(name=name):
                scope = resolve_business_analysis_scope(
                    f"ou-{name}", name,
                    [{"department_id": "od-ai", "name": "AI部", "status": "active"}],
                )
                self.assertEqual(scope["role"], "department_leader")
                self.assertEqual(scope["department"], expected_department)
                self.assertIsNone(scope["operator"])
                self.assertTrue(scope["canViewAmounts"])

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
                "storeTiers": [
                    {"store": 1, "department": "运营一部", "operator": "张三", "tier": "金1"},
                    {"store": 2, "department": "运营一部", "operator": "别人", "tier": "银1"},
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

        self.assertEqual([row["store"] for row in data["performance"]["stores"]], [1])
        self.assertEqual(data["performance"]["departments"], [])
        self.assertEqual([row["store"] for row in data["slowMoving"]], [1])
        self.assertEqual([(row["store"], row["tier"]) for row in data["storeTiers"]], [(1, "金1")])
        self.assertEqual(data["magnetDaily"], [])
        self.assertNotIn("categorySegmentsByPeriod", data)
        self.assertNotIn("sourceTotals", data["meta"])
        self.assertEqual(data["categorySegments"]["categories"], [])
        self.assertEqual(data["meta"]["accessScope"]["role"], "member")

    def test_department_leader_keeps_five_department_category_ratio_denominator(self):
        payload = {
            "data": {
                "meta": {},
                "performance": {
                    "stores": [
                        {"store": 1, "department": "运营一部", "operator": "成员甲"},
                        {"store": 3, "department": "运营一部", "operator": "成员丙"},
                        {"store": 2, "department": "运营二部", "operator": "成员乙"},
                    ],
                    "periodRows": [],
                    "departments": [
                        {"name": "整体", "isTotal": True},
                        {"name": "运营一部"},
                        {"name": "运营二部"},
                    ],
                },
                "slowMoving": [], "shipping": [], "newProductOrders": [], "unshipped": [],
                "categorySegments": {"categories": [{
                    "company": {
                        "current": {"sales": 300, "usSales": 120},
                        "previous": {"sales": 200, "usSales": 50},
                    },
                    "industry": {}, "shareDaily": [],
                    "departments": [
                        {"department": "运营一部", "currentSales": 100, "previousSales": 80, "currentUsSales": 40, "previousUsSales": 20},
                        {"department": "运营二部", "currentSales": 200, "previousSales": 120, "currentUsSales": 80, "previousUsSales": 30},
                    ],
                }]},
            },
            "formulas": [],
        }
        scope = {
            "role": "department_leader",
            "department": "运营一部",
            "operator": None,
            "userName": "周雪",
            "canViewAmounts": True,
        }

        result = prepare_business_analysis_payload(payload, scope, "2026-08")
        data = result["data"]
        category = data["categorySegments"]["categories"][0]

        self.assertEqual([row["store"] for row in data["performance"]["stores"]], [1, 3])
        self.assertEqual(
            [row["operator"] for row in data["performance"]["stores"]],
            ["成员甲", "成员丙"],
        )
        self.assertEqual([row["name"] for row in data["performance"]["departments"]], ["运营一部"])
        self.assertEqual(
            [row["department"] for row in category["departments"]],
            ["运营一部", "运营二部"],
        )
        self.assertEqual(category["company"]["current"]["sales"], 0)
        self.assertAlmostEqual(category["ratios"]["company"]["currentUsShare"], 0.4)
        self.assertEqual(category["ratios"]["company"]["currentSales"], 300)
        self.assertAlmostEqual(category["ratios"]["company"]["currentDailySales"], 300 / 31)
        department_ratios = category["ratios"]["departments"]
        self.assertAlmostEqual(department_ratios[0]["currentShare"], 1 / 3)
        self.assertAlmostEqual(department_ratios[1]["currentShare"], 2 / 3)
        self.assertEqual(department_ratios[0]["currentSales"], 100)
        self.assertAlmostEqual(department_ratios[0]["currentDailySales"], 100 / 31)
        self.assertIsNone(department_ratios[1]["currentSales"])
        self.assertIsNone(department_ratios[1]["currentDailySales"])


if __name__ == "__main__":
    unittest.main()
