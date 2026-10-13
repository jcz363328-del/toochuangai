import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AiUpdateIntegrationTests(unittest.TestCase):
    def test_ai_department_has_update_card(self):
        page = (ROOT / "templates" / "ai_modules.html").read_text(encoding="utf-8")

        self.assertIn("<h3>更新</h3>", page)
        self.assertIn("url_for('ai_update')", page)

    def test_update_page_uses_requested_query_and_full_ai_permission(self):
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        page = (ROOT / "templates" / "ai_update.html").read_text(encoding="utf-8")

        self.assertIn("@app.route('/ai/update')", app_source)
        self.assertIn("@require_permission('admin_functions')\ndef ai_update", app_source)
        self.assertIn(
            '_AI_UPDATE_QUERY = "select * from gengxin where riqi=convert(date, getdate())"',
            app_source,
        )
        self.assertNotIn("{{ query_sql }}", page)
        self.assertIn("{% for column in columns %}", page)
        self.assertIn("{% for row in rows %}", page)


if __name__ == "__main__":
    unittest.main()
