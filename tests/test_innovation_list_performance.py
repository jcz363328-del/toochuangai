import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB_APP_SOURCE = (ROOT / "innovation" / "web_app.py").read_text(encoding="utf-8")
MANAGE_SOURCE = (ROOT / "innovation" / "templates" / "manage.html").read_text(encoding="utf-8")


class InnovationListPerformanceTests(unittest.TestCase):
    def test_current_page_flow_data_is_loaded_in_one_batch(self):
        endpoint = WEB_APP_SOURCE.split(
            "def get_innovations():", 1
        )[1].split("@app.route('/api/toggle_favorite'", 1)[0]
        self.assertIn("flow_rows_by_project = {}", endpoint)
        self.assertIn("latest_committee_row_by_project = {}", endpoint)
        self.assertIn("WHERE 项目编号 IN ({project_id_clause})", endpoint)

        project_loop = endpoint.split(
            "for i, project in enumerate(projects_data):", 1
        )[1].split("# 计算总页数", 1)[0]
        self.assertNotIn("sf_db(", project_loop)
        self.assertIn("flow_rows_by_project.get", project_loop)
        self.assertIn("latest_committee_row_by_project.get", project_loop)

    def test_project_column_metadata_is_cached(self):
        helper = WEB_APP_SOURCE.split(
            "def _get_innovation_project_columns():", 1
        )[1].split("def _database_upload_path", 1)[0]
        self.assertIn("_INNOVATION_PROJECT_COLUMNS_CACHE", helper)
        self.assertIn("INFORMATION_SCHEMA.COLUMNS", helper)

    def test_page_load_has_no_artificial_initial_delay(self):
        initialization = MANAGE_SOURCE.split(
            "document.addEventListener('DOMContentLoaded', function()", 1
        )[1].split("// 监听选项卡切换事件", 1)[0]
        self.assertIn("loadInnovations(1);", initialization)
        self.assertNotIn("setTimeout", initialization)


if __name__ == "__main__":
    unittest.main()
