import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from innovation_blueprint import innovation_bp
from innovation import web_app as innovation_module


class InnovationProposalNoteTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.secret_key = "innovation-note-test"
        self.app.add_url_rule("/feishu-auth", endpoint="feishu_auth", view_func=lambda: "auth")
        self.app.register_blueprint(innovation_bp)
        self.client = self.app.test_client()

    def login(self, name="测试用户"):
        with self.client.session_transaction() as flask_session:
            flask_session["feishu_user_id"] = "ou_test"
            flask_session["feishu_user_name"] = name

    def test_ai_department_and_han_yajun_are_editors(self):
        with self.app.test_request_context("/"):
            innovation_module.session["feishu_user_id"] = "ou_ai"
            innovation_module.session["feishu_user_name"] = "AI测试"
            with patch.object(
                innovation_module.permission_manager,
                "get_user_departments",
                return_value=[{"name": "AI部", "status": "active"}],
            ):
                self.assertTrue(innovation_module._can_manage_chuangxinxing_proposal_notes())

        with self.app.test_request_context("/"):
            innovation_module.session["feishu_user_id"] = "ou_han"
            innovation_module.session["feishu_user_name"] = "韩雅俊"
            with patch.object(innovation_module.permission_manager, "get_user_departments", return_value=[]):
                self.assertTrue(innovation_module._can_manage_chuangxinxing_proposal_notes())

    def test_unauthorized_post_is_blocked_before_database_write(self):
        self.login()
        with (
            patch.object(innovation_module.permission_manager, "get_user_departments", return_value=[]),
            patch.object(innovation_module, "dui_db") as write_db,
        ):
            response = self.client.post(
                "/innovation/api/chuangxinxing/proposal-note",
                data={"proposal_id": "1001", "note": "不应保存"},
            )

        self.assertEqual(response.status_code, 302)
        self.assertIn("note_error=", response.headers["Location"])
        write_db.assert_not_called()

    def test_authorized_post_upserts_note(self):
        self.login("韩雅俊")
        with (
            patch.object(innovation_module, "sf_db", return_value=1),
            patch.object(innovation_module, "_ensure_chuangxinxing_proposal_storage"),
            patch.object(innovation_module, "dui_db") as write_db,
        ):
            response = self.client.post(
                "/innovation/api/chuangxinxing/proposal-note",
                data={"proposal_id": "1001", "note": "提案价值说明"},
            )

        self.assertEqual(response.status_code, 302)
        self.assertIn("note_saved=1001", response.headers["Location"])
        sql = write_db.call_args.args[0]
        self.assertIn("dbo.ChuangXinXing", sql)
        self.assertIn("TiAnBianHao", sql)
        self.assertIn("创新星鉴", sql)

    def test_template_uses_compact_side_button_and_modal(self):
        root = Path(__file__).resolve().parents[1]
        template = (root / "innovation" / "templates" / "excellent_cases.html").read_text(encoding="utf-8")
        source = (root / "innovation" / "web_app.py").read_text(encoding="utf-8")

        self.assertIn("case-summary-side", template)
        self.assertIn("proposal-note-modal", template)
        self.assertIn("暂无描述", template)
        self.assertIn("WHERE ISNULL(LeiXing, N'') <> N'创新星鉴'", source)


if __name__ == "__main__":
    unittest.main()
