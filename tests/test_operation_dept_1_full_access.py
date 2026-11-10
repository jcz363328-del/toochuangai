import unittest

from permission_seed_data import CORE_USER_OVERRIDES, EXTRA_PERMISSION_ROWS


class OperationDept1FullAccessTests(unittest.TestCase):
    def test_guo_ting_has_every_operation_one_feature_permission(self):
        self.assertIn("郭婷", CORE_USER_OVERRIDES["operation_dept_1"])
        self.assertEqual(CORE_USER_OVERRIDES["review_analysis"], "郭婷")
        self.assertEqual(CORE_USER_OVERRIDES["amazon_reply_agent"], "郭婷")

        rows = {row["gongneng"]: row for row in EXTRA_PERMISSION_ROWS}
        for function_name in ("business_analysis", "operation_fba_shipping", "tk_dashboard_90"):
            self.assertIn("郭婷", rows[function_name]["yonghu"], function_name)

        self.assertIn("曹园园", rows["operation_fba_shipping"]["yonghu"])
        self.assertIn("曹园园", CORE_USER_OVERRIDES["operation_dept_1"])


if __name__ == "__main__":
    unittest.main()
