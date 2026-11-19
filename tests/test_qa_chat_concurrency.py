import tempfile
import threading
import unittest
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from 图片.qa_chat import ChatStore, refresh_turn_status, submit_turn


class ChatConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = ChatStore(self.tmp.name)
        self.chat = self.store.create("alice")

    def test_parallel_sessions_cannot_insert_two_active_turns(self):
        stores = [ChatStore(self.tmp.name) for _ in range(10)]
        barrier = threading.Barrier(10)

        def add(store):
            barrier.wait()
            try:
                return store.add("alice", self.chat, "generate", [], "model")
            except ValueError:
                return None

        with ThreadPoolExecutor(max_workers=10) as clients:
            results = list(clients.map(add, stores))
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(len(self.store.turns("alice", self.chat)), 1)
        with self.store.connect() as db:
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "wal")

    def test_distinct_chats_and_accounts_write_without_losing_results(self):
        chats = [self.store.create(f"account-{i}") for i in range(12)]
        barrier = threading.Barrier(12)

        def write(i):
            store = ChatStore(self.tmp.name)
            barrier.wait()
            turn = store.add(f"account-{i}", chats[i], "generate", [], "model")
            store.update(f"account-{i}", turn, status="completed", images=[f"image-{i}"])

        with ThreadPoolExecutor(max_workers=12) as clients:
            list(clients.map(write, range(12)))
        for i, chat in enumerate(chats):
            turns = self.store.turns(f"account-{i}", chat)
            self.assertEqual(turns[0]["images"], [f"image-{i}"])
            self.assertEqual(turns[0]["status"], "completed")

    def test_job_id_is_persisted_before_runtime_submission_and_rejection_unblocks_chat(self):
        site = Mock()
        site.get_feature_by_key.return_value = {"key": "ai_qa_image"}
        site.build_prompt.return_value = "prompt"

        def reject(feature, context):
            row = self.store.turns("alice", self.chat)[0]
            self.assertEqual(row["job"], context["job_id"])
            self.assertEqual(row["status"], "queued")
            raise RuntimeError("queue full")

        site.submit_feature_job.side_effect = reject
        with self.assertRaisesRegex(RuntimeError, "queue full"):
            submit_turn(site, self.store, "alice", self.chat, "test", [], "model", 1, "1:1")
        self.assertEqual(self.store.turns("alice", self.chat)[0]["status"], "error")
        self.store.add("alice", self.chat, "next", [], "model")

    def test_recovery_waits_for_submit_gap_and_never_recommends_blind_retry(self):
        turn_id = self.store.add("alice", self.chat, "test", [], "model", job="id")
        runtime = Mock()
        runtime.get_generation_queue_state.return_value = {"state": "missing"}
        site = SimpleNamespace(get_task_runtime=lambda: runtime)
        row = self.store.turns("alice", self.chat)[0]
        row, _ = refresh_turn_status(site, self.store, "alice", self.chat, row)
        self.assertEqual(row["status"], "queued")
        with self.store.connect() as db:
            db.execute("UPDATE turns SET created=datetime('now','-2 minutes') WHERE id=?", (turn_id,))
        row, _ = refresh_turn_status(site, self.store, "alice", self.chat, row)
        self.assertEqual(row["status"], "error")
        self.assertIn("系统未自动重新提交", row["error"])
        self.assertNotIn("请重新生成", row["error"])

    def test_completed_database_result_wins_over_missing_memory_state(self):
        turn_id = self.store.add("alice", self.chat, "test", [], "model", job="id")
        stale = self.store.turns("alice", self.chat)[0]
        self.store.update("alice", turn_id, status="completed", images=["result"])
        runtime = Mock()
        runtime.get_generation_queue_state.return_value = {"state": "missing"}
        row, _ = refresh_turn_status(SimpleNamespace(get_task_runtime=lambda: runtime), self.store, "alice", self.chat, stale)
        self.assertEqual(row["status"], "completed")
        self.assertEqual(row["images"], ["result"])

    def test_late_recovery_error_cannot_overwrite_completed_result(self):
        turn = self.store.add("alice", self.chat, "test", [], "model", job="id")
        self.store.update("alice", turn, status="completed", images=["result"])
        self.store.update("alice", turn, status="error", error="stale recovery", only_active=True)
        row = self.store.turns("alice", self.chat)[0]
        self.assertEqual(row["status"], "completed")
        self.assertEqual(row["error"], "")

    def test_canceled_queue_job_does_not_leave_chat_busy(self):
        self.store.add("alice", self.chat, "test", [], "model", job="id")
        runtime = Mock()
        runtime.get_generation_queue_state.return_value = {"state": "canceled"}
        row, _ = refresh_turn_status(SimpleNamespace(get_task_runtime=lambda: runtime), self.store, "alice", self.chat,
                                    self.store.turns("alice", self.chat)[0])
        self.assertEqual(row["status"], "error")
        self.assertIn("未向图片服务提交", row["error"])

    def test_simultaneous_image_saves_leave_complete_content_and_no_temp_files(self):
        content = b"test-content" * 10000
        site = Mock()
        site.load_image_bytes_from_url.return_value = (content, "image/png")
        with ThreadPoolExecutor(max_workers=8) as workers:
            paths = list(workers.map(lambda _: self.store.save_image(site, "alice", "image"), range(16)))
        self.assertEqual(len(set(paths)), 1)
        self.assertEqual(Path(paths[0]).read_bytes(), content)
        self.assertEqual(list(Path(paths[0]).parent.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
