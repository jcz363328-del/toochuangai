import unittest
from pathlib import Path
from unittest.mock import patch

from department_permissions import FeishuPermissionManager


class PermissionOverrideTests(unittest.TestCase):
    def setUp(self):
        self.manager = FeishuPermissionManager()
        self.records = {
            "feature_a": {
                "function_name": "feature_a",
                "name": "功能A",
                "description": "A",
                "bumen": "AI部",
                "yonghu": "",
                "fujigongneng": "",
            },
            "feature_b": {
                "function_name": "feature_b",
                "name": "功能B",
                "description": "B",
                "bumen": "AI部",
                "yonghu": "",
                "fujigongneng": "",
            },
        }

    def test_explicit_deny_has_priority_over_department_permission(self):
        with (
            patch.object(self.manager, "get_permission_records", return_value=self.records),
            patch.object(
                self.manager,
                "get_user_permission_overrides",
                return_value={"feature_a": {"is_allowed": False}},
            ),
        ):
            allowed, reason = self.manager.check_user_permission("ou_test", "feature_a")

        self.assertFalse(allowed)
        self.assertEqual(reason, "用户单独禁用")

    def test_accessible_functions_merge_allow_and_deny_overrides(self):
        overrides = {
            "feature_a": {"is_allowed": True},
            "feature_b": {"is_allowed": False},
        }
        with (
            patch.object(self.manager, "get_permission_records", return_value=self.records),
            patch.object(self.manager, "get_user_permission_overrides", return_value=overrides),
            patch.object(self.manager, "_permission_context", return_value={"user_id": "ou_test"}),
            patch.object(self.manager, "_check_direct_permission_row", return_value=(True, "部门权限")),
        ):
            functions = self.manager.get_user_accessible_functions("ou_test")

        self.assertEqual([item["function_name"] for item in functions], ["feature_a"])
        self.assertEqual(functions[0]["reason"], "用户单独授权")

    def test_management_template_contains_overview_and_reset_controls(self):
        root = Path(__file__).resolve().parents[1]
        template = (root / "templates" / "permission_management.html").read_text(encoding="utf-8")
        ai_page = (root / "templates" / "ai_modules.html").read_text(encoding="utf-8")

        self.assertIn("权限概览", template)
        self.assertIn("/api/admin/permission_overview", template)
        self.assertIn("/api/admin/reset_permission", template)
        self.assertIn("全局权限管理", ai_page)


if __name__ == "__main__":
    unittest.main()
