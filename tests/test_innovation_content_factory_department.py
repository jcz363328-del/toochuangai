from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB_APP_SOURCE = (ROOT / "innovation" / "web_app.py").read_text(encoding="utf-8")
CONFIG_SOURCE = (ROOT / "innovation" / "config.py").read_text(encoding="utf-8")
MANAGE_SOURCE = (ROOT / "innovation" / "templates" / "manage.html").read_text(encoding="utf-8")
MANAGE_DEMO_SOURCE = (ROOT / "innovation" / "templates" / "manage_demo.html").read_text(encoding="utf-8")
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")


def _load_department_helpers():
    module = ast.parse(WEB_APP_SOURCE)
    helper_names = {
        "_normalize_innovation_department",
        "_innovation_department_filter_values",
        "_innovation_department_sql_values",
    }
    nodes = []
    for node in module.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id.startswith("CONTENT_FACTORY_DEPARTMENT")
            for target in node.targets
        ):
            nodes.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in helper_names:
            nodes.append(node)
    namespace = {}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "innovation/web_app.py", "exec"), namespace)
    return namespace


class InnovationContentFactoryDepartmentTests(unittest.TestCase):
    def test_submit_department_and_management_filters_use_content_factory(self):
        departments_source = CONFIG_SOURCE.split("DEPARTMENT_FEISHU_MAPPING", 1)[0]
        self.assertIn("'内容生产工厂'", departments_source)
        self.assertNotIn("'TK项目'", departments_source)
        self.assertIn('<option value="内容生产工厂">内容生产工厂</option>', MANAGE_SOURCE)
        self.assertIn('<option value="内容生产工厂">内容生产工厂</option>', MANAGE_DEMO_SOURCE)
        self.assertNotIn('<option value="TK项目">', MANAGE_SOURCE)
        self.assertNotIn('<option value="TK项目">', MANAGE_DEMO_SOURCE)

    def test_historical_department_names_are_normalized_and_filterable(self):
        helpers = _load_department_helpers()
        normalize = helpers["_normalize_innovation_department"]
        filter_values = helpers["_innovation_department_filter_values"]

        self.assertEqual(normalize("TK项目"), "内容生产工厂")
        self.assertEqual(normalize("TK_离职"), "内容生产工厂")
        self.assertEqual(normalize("内容生产工厂"), "内容生产工厂")
        self.assertEqual(
            filter_values("内容生产工厂"),
            ["内容生产工厂", "TK项目", "TK_离职", "Tk_离职", "TK"],
        )

    def test_hr_innovation_dashboard_uses_content_factory_display_name(self):
        self.assertIn("CASE WHEN 部门 IN ('TK_离职','TK项目')", APP_SOURCE)
        self.assertNotIn("THEN 'TK项目' ELSE 部门 END AS 部门", APP_SOURCE)
        self.assertIn("THEN '内容生产工厂' ELSE 部门 END AS 部门", APP_SOURCE)

    def test_submit_filter_and_management_outputs_all_use_normalization(self):
        self.assertIn("_normalize_innovation_department(dept)", WEB_APP_SOURCE)
        self.assertIn("WHERE 承接人 IN ({department_filter_values})", WEB_APP_SOURCE)
        self.assertIn("WHERE 部门 IN ({initiator_department_filter_values})", WEB_APP_SOURCE)
        self.assertIn("'assignee': _normalize_innovation_department(row[2])", WEB_APP_SOURCE)
        self.assertIn("'department': _normalize_innovation_department(row[1])", WEB_APP_SOURCE)


if __name__ == "__main__":
    unittest.main()
