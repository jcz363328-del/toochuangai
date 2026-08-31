import unittest
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from department_permissions import FeishuPermissionManager, PERMISSION_CONFIG


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")
DASHBOARD_SOURCE = (ROOT / "templates" / "dashboard.html").read_text(encoding="utf-8")
REVIEW_TEMPLATE_SOURCE = (ROOT / "templates" / "review_analysis.html").read_text(encoding="utf-8")


class RdReviewAnalysisPermissionTests(unittest.TestCase):
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
                "department_id": "od-364835a9f7cc1ad050046cd995f886e4",
                "name": "研发部",
                "status": "valid",
            }
        ]

    def test_review_analysis_config_includes_rd_department(self):
        self.assertIn(
            "研发部",
            PERMISSION_CONFIG["review_analysis"]["allowed_departments"],
        )

    def test_rd_department_can_access_review_analysis(self):
        allowed, reason = self.manager.check_user_permission(
            "rd-user",
            "review_analysis",
        )

        self.assertTrue(allowed, reason)
        self.assertIn("研发部", reason)

    def test_rd_card_links_to_department_page(self):
        self.assertIn("@app.route('/rd_dept')", APP_SOURCE)
        self.assertIn("@require_permission('rd_dept')", APP_SOURCE)
        self.assertIn("url_for('rd_dept')", APP_SOURCE)
        self.assertIn("fname == 'rd_dept'", DASHBOARD_SOURCE)
        self.assertIn("url_for('rd_dept')", DASHBOARD_SOURCE)

    def test_rd_page_contains_review_analysis_entry(self):
        environment = Environment(loader=FileSystemLoader(ROOT / "templates"))
        environment.globals["url_for"] = (
            lambda endpoint, **values: f"/{endpoint}"
        )
        template = environment.get_template("operation_dept.html")
        html = template.render(
            user_name="研发测试用户",
            user_id="rd-user",
            dept_name="研发部",
            dept_id="rd_dept",
            can_view_review_analysis=True,
            can_view_amazon_reply=False,
        )

        self.assertIn("研发部功能中心", html)
        self.assertIn("差评分析系统", html)
        self.assertIn("/review_analysis.review_analysis", html)

    def test_review_page_includes_echarts_dashboard(self):
        self.assertIn("echarts@5.5.1", REVIEW_TEMPLATE_SOURCE)
        self.assertIn('id="reviewRatingChart"', REVIEW_TEMPLATE_SOURCE)
        self.assertIn('id="reviewTrendChart"', REVIEW_TEMPLATE_SOURCE)
        self.assertIn('id="reviewShopChart"', REVIEW_TEMPLATE_SOURCE)
        self.assertIn("renderReviewDashboard", REVIEW_TEMPLATE_SOURCE)


if __name__ == "__main__":
    unittest.main()
