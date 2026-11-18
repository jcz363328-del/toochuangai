import tempfile
import io
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from streamlit.testing.v1 import AppTest
from PIL import Image
from 图片 import openrouter_image_site as site
from 图片.qa_chat import ChatStore, build_context, submit_turn, run_chat_job


class ChatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = ChatStore(self.tmp.name)
        self.chat = self.store.create("alice")

    def test_account_isolation_and_recovery(self):
        turn = self.store.add("alice", self.chat, "画一朵花", [], "model")
        self.store.update("bob", turn, status="completed", images=["wrong"])
        self.assertEqual(self.store.list("bob"), [])
        self.assertEqual(self.store.turns("bob", self.chat), [])
        self.assertEqual(ChatStore(self.tmp.name).turns("alice", self.chat)[0]["status"], "queued")
        with self.assertRaises(ValueError):
            self.store.add("bob", self.chat, "bad", [], "model")
        with self.assertRaises(ValueError):
            self.store.add("alice", self.chat, "duplicate", [], "model")

    def test_follow_up_uses_latest_successful_image_and_new_refs_override(self):
        turns = [{"status": "completed", "prompt": "画花", "images": ["flower.png"]},
                 {"status": "error", "prompt": "失败", "images": []}]
        refs, prompt = build_context(turns, "改成红色", [])
        self.assertEqual(refs, ["flower.png"])
        self.assertIn("画花", prompt)
        self.assertIn("改成红色", prompt)
        self.assertEqual(build_context(turns, "改蓝色", ["new.png"])[0], ["new.png"])

    def test_submit_failure_does_not_leave_chat_busy(self):
        with patch.object(site, "submit_feature_job", side_effect=RuntimeError("queue failed")):
            with self.assertRaisesRegex(RuntimeError, "queue failed"):
                submit_turn(site, self.store, "alice", self.chat, "画花", [], site.DEFAULT_MODEL, 2, site.DEFAULT_ASPECT_RATIO)
        self.assertEqual(self.store.turns("alice", self.chat)[0]["status"], "error")

    def test_worker_persists_result_without_frontend_polling(self):
        turn = self.store.add("alice", self.chat, "画花", [], "model")
        fake = Mock()
        fake.load_image_bytes_from_url.return_value = (b"image-content", "image/png")
        context = dict(qa_chat_root=self.tmp.name, account_name="alice", qa_turn_id=turn, job_id="job1")
        run_chat_job(fake, context, lambda c: {"images": ["remote-image"]})
        saved = ChatStore(self.tmp.name).turns("alice", self.chat)[0]
        self.assertEqual(saved["status"], "completed")
        self.assertEqual(Path(saved["images"][0]).read_bytes(), b"image-content")

    def test_worker_failure_is_saved(self):
        turn = self.store.add("alice", self.chat, "画花", [], "model")
        context = dict(qa_chat_root=self.tmp.name, account_name="alice", qa_turn_id=turn)
        with self.assertRaisesRegex(RuntimeError, "未返回图片"):
            run_chat_job(Mock(), context, lambda c: {"images": []})
        self.assertEqual(self.store.turns("alice", self.chat)[0]["status"], "error")

    def test_ui_new_conversation_and_text_only_submission(self):
        with patch.object(site, "HISTORY_DIR", Path(self.tmp.name)), patch.object(
                site, "submit_feature_job", return_value={"job_id": "test-job"}) as submit:
            app = AppTest.from_string('''
from 图片 import openrouter_image_site as site
site.ensure_state()
site.st.session_state.auth_username = "alice"
site.render_openrouter_feature(site.get_feature_by_key("ai_qa_image"), site.DEFAULT_MODEL, site.DEFAULT_ASPECT_RATIO)
''', default_timeout=30).run()
            self.assertFalse(list(app.exception))
            app.chat_input[0].set_value("生成一朵红色的花").run()
            self.assertFalse(list(app.exception), [e.message for e in app.exception])
            self.assertEqual(submit.call_args.args[1]["uploaded_files"], [])
            self.assertIn("生成一朵红色的花", submit.call_args.args[1]["prompt"])
            app.button(key="qa_new_chat").click().run()
            self.assertFalse(list(app.exception))
            self.assertEqual(len(ChatStore(self.tmp.name).list("alice")), 2)

    def test_completed_ui_restores_preview_and_follow_up_request(self):
        image = io.BytesIO()
        Image.new("RGB", (32, 32), "red").save(image, format="PNG")
        source = Path(self.tmp.name) / "red.png"
        source.write_bytes(image.getvalue())
        turn = self.store.add("alice", self.chat, "画红色背景", [], site.DEFAULT_MODEL, 2, "1:1")
        self.store.update("alice", turn, status="completed", images=[str(source)])
        with patch.object(site, "HISTORY_DIR", Path(self.tmp.name)), patch.object(
                site, "submit_feature_job", return_value={"job_id": "test-job"}) as submit:
            app = AppTest.from_string('''
from 图片 import openrouter_image_site as site
site.ensure_state()
site.st.session_state.auth_username = "alice"
site.render_openrouter_feature(site.get_feature_by_key("ai_qa_image"), site.DEFAULT_MODEL, site.DEFAULT_ASPECT_RATIO)
''', default_timeout=30).run()
            self.assertFalse(list(app.exception), [e.message for e in app.exception])
            self.assertTrue(any(b.label == "重新生成" for b in app.button))
            app.chat_input[0].set_value("改成蓝色").run()
            self.assertFalse(list(app.exception))
            context = submit.call_args.args[1]
            self.assertEqual(len(context["uploaded_files"]), 1)
            self.assertIn("上一轮生成结果", context["prompt"])
            self.assertIn("画红色背景", context["prompt"])


if __name__ == "__main__":
    unittest.main()
