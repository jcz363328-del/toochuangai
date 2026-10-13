import json
import tempfile
import unittest
from pathlib import Path

from business_analysis_key_tasks import KeyTaskStore, KeyTaskStoreError


def task(department="运营一部", title="完成试点", owner="负责人"):
    return {
        "department": department,
        "project": "product-pilot",
        "task": title,
        "owner": owner,
        "output": "已确认范围",
        "nextCheckpoint": "下周评审",
        "risk": "",
        "status": "started",
    }


class BusinessAnalysisKeyTaskStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "key-tasks.json"
        self.store = KeyTaskStore(self.path)
        self.owner_scope = {
            "role": "business_owner",
            "department": None,
            "userName": "周俊成",
        }

    def tearDown(self):
        self.temporary.cleanup()

    def test_owner_can_create_list_update_delete_and_json_is_persisted(self):
        created = self.store.create(task(), self.owner_scope)["created"][0]
        self.assertEqual(self.store.list(self.owner_scope)["tasks"][0]["id"], created["id"])
        self.assertTrue(self.store.list(self.owner_scope)["meta"]["scope"]["canEditAll"])

        updated_input = task(title="完成试点复盘")
        updated_input["status"] = "completed"
        updated = self.store.update(created["id"], updated_input, self.owner_scope)["task"]
        self.assertEqual(updated["status"], "completed")
        self.assertEqual(updated["updatedBy"], "周俊成")

        persisted = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["tasks"][0]["task"], "完成试点复盘")

        removed = self.store.remove(created["id"], self.owner_scope)["removed"]
        self.assertEqual(removed["id"], created["id"])
        self.assertEqual(self.store.list(self.owner_scope)["tasks"], [])

    def test_department_leader_sees_department_and_member_only_sees_self(self):
        first = self.store.create(task("运营一部", "本人任务", "成员"), self.owner_scope)["created"][0]
        colleague = self.store.create(task("运营一部", "同事任务", "同事"), self.owner_scope)["created"][0]
        self.store.create(task("运营二部", "二部任务", "其他人"), self.owner_scope)
        member_scope = {"role": "member", "department": "运营一部", "userName": "成员"}
        leader_scope = {"role": "department_leader", "department": "运营一部", "userName": "周雪"}

        self.assertEqual([row["task"] for row in self.store.list(leader_scope)["tasks"]], ["本人任务", "同事任务"])
        self.assertEqual([row["task"] for row in self.store.list(member_scope)["tasks"]], ["本人任务"])
        self.store.update(first["id"], task("运营一部", "本人更新", "成员"), member_scope)
        with self.assertRaises(KeyTaskStoreError) as raised:
            self.store.update(colleague["id"], task("运营一部", "越权更新", "成员"), member_scope)
        self.assertEqual(raised.exception.status, 403)
        with self.assertRaises(KeyTaskStoreError) as raised:
            self.store.create(task("运营二部", "越权任务", "成员"), member_scope)
        self.assertEqual(raised.exception.status, 403)
        with self.assertRaises(KeyTaskStoreError) as raised:
            self.store.create(task("运营一部", "代建任务", "同事"), member_scope)
        self.assertEqual(raised.exception.status, 403)

    def test_ratio_viewer_is_read_only(self):
        self.store.create(task(), self.owner_scope)
        scope = {"role": "ratio_viewer", "department": None, "userName": "只读用户"}

        self.assertEqual(len(self.store.list(scope)["tasks"]), 1)
        self.assertFalse(self.store.list(scope)["meta"]["scope"]["canEditAll"])
        with self.assertRaises(KeyTaskStoreError) as raised:
            self.store.create(task(), scope)
        self.assertEqual(raised.exception.status, 403)


if __name__ == "__main__":
    unittest.main()
