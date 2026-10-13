import unittest

from permission_seed_data import EXTRA_PERMISSION_ROWS


class BusinessAnalysisPermissionSeedTests(unittest.TestCase):
    def test_business_analysis_permissions_are_seeded(self):
        rows = {row["gongneng"]: row for row in EXTRA_PERMISSION_ROWS}

        access = rows["business_analysis"]
        self.assertEqual(access["fujigongneng"], "ai_dept")
        self.assertIn("AI部", access["bumen"])
        self.assertIn("运营一部", access["bumen"])
        self.assertIn("王丰慧", access["yonghu"])

        full_access = rows["business_analysis_all"]
        self.assertEqual(full_access["fujigongneng"], "business_analysis")
        self.assertEqual(full_access["yonghu"], "周俊成；王丰慧；蔡晶；侯梁；孙洁；刘蓉蓉")
        self.assertEqual(full_access["bumen"], "AI部；总经办")

    def test_wang_fenghui_matches_zhou_juncheng_business_analysis_permissions(self):
        rows = {row["gongneng"]: row for row in EXTRA_PERMISSION_ROWS}
        users = {
            item.strip()
            for item in rows["business_analysis_all"]["yonghu"].split("；")
            if item.strip()
        }
        self.assertIn("周俊成", users)
        self.assertIn("王丰慧", users)

    def test_cai_jing_mirrors_every_seeded_zhou_juncheng_permission(self):
        for row in EXTRA_PERMISSION_ROWS:
            users = {
                item.strip()
                for item in str(row.get("yonghu") or "").split("；")
                if item.strip()
            }
            if "周俊成" in users:
                self.assertIn("蔡晶", users, row["gongneng"])


if __name__ == "__main__":
    unittest.main()
