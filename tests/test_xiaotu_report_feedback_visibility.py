from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"
HISTORY_TEMPLATE_PATH = ROOT / "templates" / "xiaotu_report_history.html"


def _app_function_source(function_name: str) -> str:
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            start_line = min(
                [node.lineno]
                + [decorator.lineno for decorator in node.decorator_list]
            )
            return "\n".join(source.splitlines()[start_line - 1 : node.end_lineno])
    raise AssertionError(f"missing function: {function_name}")


def _load_visibility_helper(namespace: dict):
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    helper_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_xiaotu_report_history_is_visible_to_user"
    )
    helper_module = ast.Module(body=[helper_node], type_ignores=[])
    ast.fix_missing_locations(helper_module)
    exec(compile(helper_module, str(APP_PATH), "exec"), namespace)
    return namespace["_xiaotu_report_history_is_visible_to_user"]


class XiaotuReportFeedbackVisibilityTests(unittest.TestCase):
    def test_history_page_allows_comments_for_both_visible_lists(self) -> None:
        template = HISTORY_TEMPLATE_PATH.read_text(encoding="utf-8")

        self.assertIn(
            "const canComment = (source === 'received' || source === 'uploaded') && action === 'comment';",
            template,
        )
        self.assertIn(
            "if (source === 'received' || source === 'uploaded') {",
            template,
        )

    def test_feedback_endpoints_enforce_history_visibility(self) -> None:
        api_source = _app_function_source("api_xiaotu_report_feedback")
        page_source = _app_function_source("xiaotu_report_comment_page")

        guard = "_xiaotu_report_history_is_visible_to_user(wendangid, actor_name)"
        self.assertIn(guard, api_source)
        self.assertIn(guard, page_source)
        self.assertIn("@require_permission('xiaotu_qa')", page_source)

    def test_visibility_helper_combines_uploaded_and_received_scope(self) -> None:
        captured = {}

        def fake_context(_args, user_name):
            self.assertEqual(user_name, "测试用户")
            return {
                "uploaded_where_sql": "b.XingMing = N'测试用户'",
                "received_where_sql": "b.JieShouRen LIKE N'%测试用户%'",
            }

        def fake_query(sql):
            captured["sql"] = sql
            return [{"WenDangID": "report-1"}]

        helper = _load_visibility_helper(
            {
                "_xiaotu_build_report_history_export_context": fake_context,
                "_xiaotu_sql_escape": lambda value: str(value).replace("'", "''"),
                "sf_db": fake_query,
            }
        )

        self.assertTrue(helper("report-'1", "测试用户"))
        self.assertIn("b.XingMing = N'测试用户'", captured["sql"])
        self.assertIn("b.JieShouRen LIKE N'%测试用户%'", captured["sql"])
        self.assertIn("report-''1", captured["sql"])

    def test_visibility_helper_fails_closed_for_missing_identity_or_row(self) -> None:
        helper = _load_visibility_helper(
            {
                "_xiaotu_build_report_history_export_context": lambda _args, _name: {
                    "uploaded_where_sql": "1=1",
                    "received_where_sql": "1=1",
                },
                "_xiaotu_sql_escape": str,
                "sf_db": lambda _sql: [],
            }
        )

        self.assertFalse(helper("", "测试用户"))
        self.assertFalse(helper("report-1", ""))
        self.assertFalse(helper("report-1", "测试用户"))


if __name__ == "__main__":
    unittest.main()
