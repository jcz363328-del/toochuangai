import unittest

import app as app_module


class BusinessAnalysisStoreTierScopeTests(unittest.TestCase):
    def test_department_leader_sees_all_department_owner_names(self):
        condition = app_module._business_analysis_store_tier_scope_condition({
            "role": "department_leader",
            "department": "运营一部",
            "operator": None,
        })

        self.assertIn("dp.BuMen", condition)
        self.assertIn("周雪", condition)
        self.assertIn("郭婷", condition)
        self.assertNotIn("dp.YunYing", condition)

    def test_member_only_sees_own_stores(self):
        condition = app_module._business_analysis_store_tier_scope_condition({
            "role": "member",
            "department": "运营一部",
            "operator": "刘俊霞",
        })

        self.assertEqual(condition, "LTRIM(RTRIM(dp.YunYing)) = N'刘俊霞'")

    def test_owner_has_no_scope_filter(self):
        self.assertEqual(
            app_module._business_analysis_store_tier_scope_condition({"role": "business_owner"}),
            "",
        )


if __name__ == "__main__":
    unittest.main()
