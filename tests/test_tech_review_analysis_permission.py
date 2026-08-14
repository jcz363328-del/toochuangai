import unittest

from department_permissions import FeishuPermissionManager, PERMISSION_CONFIG


class TechReviewAnalysisPermissionTests(unittest.TestCase):
    def setUp(self):
        self.manager = FeishuPermissionManager()
        self.manager.is_developer = lambda user_id=None, email=None: False
        self.manager._get_extra_allowed_functions = lambda user_id: []
        self.manager._resolve_effective_departments = (
            lambda departments, function_name: (departments, False)
        )
        self.manager._department_matches_root_name = (
            lambda department_id, root_name: False
        )
        self.manager.get_user_departments = lambda user_id: [
            {
                "department_id": "od-bca4e38e980226d367f7c501b3697e5a",
                "name": "技术部",
                "status": "valid",
            }
        ]

    def test_review_analysis_config_includes_tech_department(self):
        self.assertIn(
            "技术部",
            PERMISSION_CONFIG["review_analysis"]["allowed_departments"],
        )

    def test_tech_department_can_access_review_analysis(self):
        allowed, reason = self.manager.check_user_permission(
            "tech-user",
            "review_analysis",
        )

        self.assertTrue(allowed, reason)
        self.assertIn("技术部", reason)


if __name__ == "__main__":
    unittest.main()
