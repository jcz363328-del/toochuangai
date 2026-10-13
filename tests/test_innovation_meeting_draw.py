import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB_SOURCE = (ROOT / "innovation" / "web_app.py").read_text(encoding="utf-8")
MANAGE_SOURCE = (ROOT / "innovation" / "templates" / "manage.html").read_text(encoding="utf-8")
BLUEPRINT_SOURCE = (ROOT / "innovation_blueprint.py").read_text(encoding="utf-8")


class InnovationMeetingDrawTests(unittest.TestCase):
    def test_all_fourteen_departments_are_configured(self):
        tree = ast.parse(WEB_SOURCE)
        assignment = next(
            node for node in tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "INNOVATION_MEETING_DEPARTMENTS"
                    for target in node.targets)
        )
        departments = ast.literal_eval(assignment.value)
        self.assertEqual(len(departments), 14)
        self.assertEqual(len(set(departments)), 14)
        self.assertIn("内容生产工厂", departments)
        self.assertIn("运营七部", departments)

    def test_meetings_keep_independent_round_history(self):
        self.assertIn("WHERE meeting_type = {_sql_nvarchar(meeting_type)} AND round_number", WEB_SOURCE)
        self.assertIn("excluded = set(_innovation_meeting_selected(meeting_type, round_number))", WEB_SOURCE)
        self.assertIn("if meeting_type == 'review':", WEB_SOURCE)
        self.assertIn("excluded.update(_innovation_meeting_latest_group_departments())", WEB_SOURCE)

    def test_management_page_contains_draw_controls(self):
        self.assertIn('id="meeting-draw-tab"', MANAGE_SOURCE)
        self.assertIn("随机抽取两个部门", MANAGE_SOURCE)
        self.assertIn("开启新一轮", MANAGE_SOURCE)
        self.assertIn("取消该会议最近一次抽签", MANAGE_SOURCE)
        self.assertIn("/innovation/api/meeting_draw/cancel", MANAGE_SOURCE)
        self.assertIn("info.latest_result", MANAGE_SOURCE)
        self.assertIn("setTimeout(resolve, 3000)", MANAGE_SOURCE)
        self.assertIn("meetingDrawShimmer", MANAGE_SOURCE)
        self.assertIn("抽签中 ${secondsLeft}s", MANAGE_SOURCE)
        self.assertIn("meetingSelectionHistory(info.selected_details)", MANAGE_SOURCE)
        self.assertIn("selected_at", WEB_SOURCE)
        self.assertIn("'历史导入' if selected_by == '历史导入'", WEB_SOURCE)
        self.assertIn("两个会议候选池相互独立", MANAGE_SOURCE)
        self.assertIn("/innovation/api/meeting_draw/draw", MANAGE_SOURCE)

    def test_draw_apis_are_exposed_by_main_blueprint(self):
        self.assertIn("innovation_meeting_draw_state", BLUEPRINT_SOURCE)
        self.assertIn("@innovation_bp.route('/api/meeting_draw/state'", BLUEPRINT_SOURCE)
        self.assertIn("@innovation_bp.route('/api/meeting_draw/draw'", BLUEPRINT_SOURCE)
        self.assertIn("@innovation_bp.route('/api/meeting_draw/new_round'", BLUEPRINT_SOURCE)
        self.assertIn("@innovation_bp.route('/api/meeting_draw/cancel'", BLUEPRINT_SOURCE)


if __name__ == "__main__":
    unittest.main()
