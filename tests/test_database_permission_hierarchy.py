import unittest

from department_permissions import FeishuPermissionManager


class StubPermissionManager(FeishuPermissionManager):
    def __init__(self, records, departments=None, identities=None):
        super().__init__()
        self._stub_records = records
        self._stub_departments = departments or {}
        self._stub_identities = identities or {}

    def get_permission_records(self, force_refresh=False):
        return self._stub_records

    def get_user_departments(self, user_id):
        return [
            {"department_id": f"test:{name}", "name": name, "status": "active"}
            for name in self._stub_departments.get(user_id, [])
        ]

    def _permission_user_identities(self, user_id):
        return {str(user_id), *self._stub_identities.get(user_id, set())}


def row(function_name, *, users="", departments="", parent=""):
    return {
        "function_name": function_name,
        "yonghu": users,
        "bumen": departments,
        "fujigongneng": parent,
        "name": function_name,
        "description": "",
    }


class DatabasePermissionHierarchyTests(unittest.TestCase):
    def test_department_is_checked_before_personal_permission(self):
        records = {
            "feature": row(
                "feature",
                users="张三",
                departments="运营一部",
            )
        }
        manager = StubPermissionManager(
            records,
            departments={"u1": ["运营一部"]},
            identities={"u1": {"张三"}},
        )

        allowed, reason = manager.check_user_permission("u1", "feature")

        self.assertTrue(allowed)
        self.assertIn("部门权限通过", reason)

    def test_personal_permission_fills_department_gap(self):
        records = {
            "feature": row(
                "feature",
                users="张三；李四",
                departments="财务部",
            )
        }
        manager = StubPermissionManager(
            records,
            departments={"u1": ["运营一部"]},
            identities={"u1": {"张三"}},
        )

        allowed, reason = manager.check_user_permission("u1", "feature")

        self.assertTrue(allowed)
        self.assertIn("个人权限通过", reason)

    def test_child_permission_lights_parent_but_not_sibling(self):
        records = {
            "parent": row("parent"),
            "child_a": row("child_a", users="张三", parent="parent"),
            "child_b": row("child_b", users="李四", parent="parent"),
        }
        manager = StubPermissionManager(
            records,
            identities={"u1": {"张三"}},
        )

        self.assertTrue(manager.check_user_permission("u1", "child_a")[0])
        self.assertTrue(manager.check_user_permission("u1", "parent")[0])
        self.assertFalse(manager.check_user_permission("u1", "child_b")[0])

        visible = {
            item["function_name"]: item
            for item in manager.get_user_accessible_functions("u1")
        }
        self.assertEqual({"parent", "child_a"}, set(visible))
        self.assertTrue(visible["parent"]["is_parent_visibility"])
        self.assertFalse(visible["child_a"]["is_parent_visibility"])

    def test_parent_permission_does_not_open_children(self):
        records = {
            "parent": row("parent", users="张三"),
            "child_a": row("child_a", parent="parent"),
            "child_b": row("child_b", parent="parent"),
        }
        manager = StubPermissionManager(
            records,
            identities={"u1": {"张三"}},
        )

        self.assertTrue(manager.check_user_permission("u1", "parent")[0])
        self.assertFalse(manager.check_user_permission("u1", "child_a")[0])
        self.assertFalse(manager.check_user_permission("u1", "child_b")[0])


if __name__ == "__main__":
    unittest.main()
