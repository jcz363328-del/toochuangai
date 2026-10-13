import unittest
from unittest.mock import patch

import app as app_module
import value_evaluation as module


class ValueEvaluationTests(unittest.TestCase):
    def test_state_uses_feishu_user_name_and_never_computer_name(self):
        sql_seen = []

        def query(sql):
            sql_seen.append(sql)
            if "MAX(DanHao)" in sql:
                return [20260624]
            if "FROM JiaZhiGuan_AnPai" in sql:
                return [("张三", "同部门同事")]
            if "DISTINCT BeiPingJiaRen" in sql:
                return []
            return [("1-1", "价值", "责任心", "说明")]

        result = module.load_evaluation_state("任真民", query_fn=query)
        combined = "\n".join(sql_seen)
        self.assertEqual("任真民", result["user_name"])
        self.assertIn("PingJiaRen=N'任真民'", combined)
        self.assertNotIn("ComputerName", combined)
        self.assertNotIn("cname", combined.lower())

    def test_validation_matches_workbook_rules(self):
        criteria = [
            {"code": f"1-{i}", "item": f"项目{i}", "description": ""}
            for i in range(1, 7)
        ] + [
            {"code": "2-1", "item": "优点", "description": "最看重哪方面"},
            {"code": "2-2", "item": "提升", "description": "哪些方面需提升"},
        ]
        payload = {"answers": [
            {"code": f"1-{i}", "score": 4 if i < 6 else 3, "remark": ""}
            for i in range(1, 7)
        ] + [
            {"code": "2-1", "remark": "沟通能力"},
            {"code": "2-2", "remark": "独立担当"},
        ]}
        self.assertEqual(8, len(module.validate_submission(payload, criteria)))

        for answer in payload["answers"][:6]:
            answer["score"] = 4
        with self.assertRaisesRegex(ValueError, "不能全部相同"):
            module.validate_submission(payload, criteria)

    def test_page_requires_feishu_name(self):
        client = app_module.app.test_client()
        with client.session_transaction() as flask_session:
            flask_session["feishu_user_id"] = "dev_test"
        with patch.object(app_module.permission_manager, "check_user_permission", return_value=(True, "ok")):
            response = client.get("/ai/value-evaluation")
        self.assertEqual(401, response.status_code)

    def test_page_displays_authenticated_feishu_name(self):
        client = app_module.app.test_client()
        with client.session_transaction() as flask_session:
            flask_session["feishu_user_id"] = "dev_test"
            flask_session["feishu_user_name"] = "飞书测试用户"
        with patch.object(app_module.permission_manager, "check_user_permission", return_value=(True, "ok")):
            response = client.get("/ai/value-evaluation")
        self.assertEqual(200, response.status_code)
        body = response.get_data(as_text=True)
        self.assertIn("360价值评价", body)
        self.assertIn("当前飞书用户：飞书测试用户", body)


if __name__ == "__main__":
    unittest.main()
