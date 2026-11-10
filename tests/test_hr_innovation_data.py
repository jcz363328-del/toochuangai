from __future__ import annotations

import ast
import unittest
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")
TEMPLATE_SOURCE = (ROOT / "templates" / "hr_innovation_data.html").read_text(encoding="utf-8")


def _load_helper(name: str, initial_namespace: dict[str, object] | None = None):
    module = ast.parse(APP_SOURCE)
    helper = next(
        node
        for node in module.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    )
    namespace: dict[str, object] = dict(initial_namespace or {})
    exec(compile(ast.Module(body=[helper], type_ignores=[]), "app.py", "exec"), namespace)
    return namespace[name]


class HrInnovationDataTests(unittest.TestCase):
    def test_filter_supports_multiple_months_and_department(self) -> None:
        filter_data = _load_helper("_filter_hr_innovation_data")
        data = {
            "monthly_total": [
                {"月份": "2026-05", "数量": 9},
                {"月份": "2026-06", "数量": 12},
                {"月份": "2026-07", "数量": 15},
            ],
            "monthly_department_total": [
                {"月份": "2026-05", "部门": "AI部", "数量": 4},
                {"月份": "2026-06", "部门": "AI部", "数量": 5},
                {"月份": "2026-06", "部门": "人力行政部", "数量": 7},
                {"月份": "2026-07", "部门": "AI部", "数量": 6},
            ],
        }

        result = filter_data(data, months=["2026-05", "2026-07"], department="AI部")

        self.assertEqual(result["monthly_department_total"], [
            {"月份": "2026-05", "部门": "AI部", "数量": 4},
            {"月份": "2026-07", "部门": "AI部", "数量": 6},
        ])
        self.assertEqual(result["monthly_total"], [
            {"月份": "2026-05", "数量": 4},
            {"月份": "2026-07", "数量": 6},
        ])

    def test_filter_distinguishes_all_months_from_empty_selection(self) -> None:
        filter_data = _load_helper("_filter_hr_innovation_data")
        data = {"monthly_total": [{"月份": "2026-07", "数量": 3}]}

        self.assertEqual(filter_data(data, months=None)["monthly_total"], data["monthly_total"])
        self.assertEqual(filter_data(data, months=[])["monthly_total"], [])

    def test_excel_values_neutralize_formulas(self) -> None:
        excel_value = _load_helper("_hr_innovation_excel_value")

        self.assertTrue(excel_value("=HYPERLINK(\"https://example.com\")").startswith("'="))
        self.assertEqual(excel_value("+1+1"), "'+1+1")
        self.assertEqual(excel_value(12), 12)

    def test_people_chart_shows_participation_rate(self) -> None:
        self.assertIn("部门参与率", TEMPLATE_SOURCE)
        self.assertIn("peopleRateByDepartment", TEMPLATE_SOURCE)
        self.assertIn("participantDenominator", TEMPLATE_SOURCE)
        self.assertNotIn("renderRankChart('peopleChart'", TEMPLATE_SOURCE)

    def test_month_queries_avoid_clr_format_function(self) -> None:
        loader_section = APP_SOURCE.split("def _load_hr_innovation_data", 1)[1].split(
            "def _filter_hr_innovation_data", 1
        )[0]
        self.assertNotIn("FORMAT(", loader_section)
        self.assertIn("CONVERT(VARCHAR(7)", loader_section)

    def test_template_has_multiselect_echarts_and_export(self) -> None:
        self.assertIn("echarts@5.5.1", TEMPLATE_SOURCE)
        self.assertIn('id="monthFilterTrigger"', TEMPLATE_SOURCE)
        self.assertIn('id="monthOptions"', TEMPLATE_SOURCE)
        self.assertIn('id="selectAllMonths"', TEMPLATE_SOURCE)
        self.assertIn('id="clearMonths"', TEMPLATE_SOURCE)
        self.assertIn('id="exportBtn"', TEMPLATE_SOURCE)
        self.assertIn("/api/hr/innovation_data/export", TEMPLATE_SOURCE)
        for chart_id in (
            "monthlyChart",
            "deptChart",
            "validChart",
            "peopleChart",
            "scoreChart",
            "categoryChart",
        ):
            self.assertIn(f'id="{chart_id}"', TEMPLATE_SOURCE)

    def test_export_creates_a_multi_sheet_workbook(self) -> None:
        self.assertIn("@app.route('/api/hr/innovation_data/export')", APP_SOURCE)
        excel_value = _load_helper("_hr_innovation_excel_value")
        build_workbook = _load_helper(
            "_build_hr_innovation_workbook",
            {"datetime": datetime, "_hr_innovation_excel_value": excel_value},
        )
        data = {
            "monthly_total": [{"月份": "2026-07", "数量": 3}],
            "monthly_department_total": [{"月份": "2026-07", "部门": "AI部", "数量": 3}],
            "valid_department_total": [{"月份": "2026-07", "部门": "AI部", "有效提案数量": 2}],
            "monthly_people": [{"月份": "2026-07", "部门": "AI部", "发起人": "测试用户"}],
            "score_distribution": [{"月份": "2026-07", "部门": "AI部", "分数": 20, "数量": 2}],
            "category_distribution": [{"月份": "2026-07", "部门": "AI部", "创新类别": "=测试", "数量": 1}],
        }

        workbook = load_workbook(build_workbook(data, "2026-07", "AI部", "测试"))

        expected_sheets = [
            "数据概览",
            "月度提案总量",
            "部门提案数量",
            "部门有效提案",
            "月度发起人",
            "分数分布",
            "创新类别",
        ]
        self.assertEqual(workbook.sheetnames, expected_sheets)
        self.assertEqual(workbook["数据概览"]["B3"].value, "2026-07")
        self.assertEqual(workbook["数据概览"]["B6"].value, 3)
        self.assertEqual(workbook["创新类别"]["C2"].value, "'=测试")


if __name__ == "__main__":
    unittest.main()
