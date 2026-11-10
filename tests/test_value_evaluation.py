import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch

import app as app_module
import value_evaluation as module
from openpyxl import Workbook, load_workbook
from werkzeug.datastructures import FileStorage


class ValueEvaluationTests(unittest.TestCase):
    def test_same_level_relationship_is_normalized_as_peer(self):
        self.assertEqual("平级", module.normalize_relationship_group("同级"))
        self.assertEqual("平级", module.normalize_relationship_group("同级同事"))

    def test_notification_uses_requested_public_evaluation_url(self):
        self.assertEqual(
            "http://223.78.73.100:8000/ai/value-evaluation",
            module.EVALUATION_PUBLIC_URL,
        )

    @patch.object(module, "load_evaluation_weights")
    @patch.object(module.pytds, "connect")
    def test_comprehensive_score_applies_item_and_relationship_weights(self, connect, load_weights):
        load_weights.return_value = {
            "criteria": [
                {"code": "1-01", "weight": 1, "relationship_weights": {"上级": 45, "平级": 20, "下级": 35, "自评": 0}},
                {"code": "1-02", "weight": 1, "relationship_weights": {"上级": 40, "平级": 25, "下级": 35, "自评": 0}},
            ],
            "relationships": [{"name": name} for name in ("上级", "平级", "下级", "自评")],
        }
        cursor = Mock()
        cursor.fetchone.return_value = ("20261013",)
        cursor.fetchall.side_effect = [
            [("张三", "领导甲", "上级"), ("张三", "同事乙", "同事")],
            [
                ("张三", "领导甲", "1-01", 5), ("张三", "领导甲", "1-02", 1),
                ("张三", "同事乙", "1-01", 3), ("张三", "同事乙", "1-02", 3),
            ],
        ]
        connection = Mock()
        connection.cursor.return_value = cursor
        connect.return_value = connection

        result = module.calculate_comprehensive_scores()

        self.assertEqual("20261013", result["batch_no"])
        self.assertEqual(3.08, result["scores"][0]["score"])
        self.assertEqual(3.08, result["scores"][0]["module_scores"]["品德素养"])
        self.assertEqual(2, result["scores"][0]["submitted_count"])
        self.assertEqual(2, result["scores"][0]["assigned_count"])
        self.assertEqual(["a", "b"], [item["evaluator_alias"] for item in result["scores"][0]["evaluator_details"]])
        self.assertEqual(3.0, result["scores"][0]["evaluator_details"][0]["score"])
        self.assertNotIn("evaluator", result["scores"][0]["evaluator_details"][0])
        self.assertEqual("1-01", result["detail_criteria"][0]["code"])

    def test_admin_page_contains_weight_and_score_sections(self):
        template = (Path(app_module.app.root_path) / "templates" / "value_evaluation_admin.html").read_text(encoding="utf-8")
        self.assertIn("评价权重设置", template)
        self.assertIn("关系权重", template)
        self.assertIn("综合得分", template)
        self.assertIn("一键通知待评价人", template)
        self.assertIn("评价人得分明细", template)
        self.assertIn("evaluator_alias", template)
        self.assertIn("/api/ai/value-evaluation/admin/notify", template)
        self.assertIn("一键导出", template)

    def test_score_export_uses_anonymous_evaluator_aliases(self):
        payload = module.build_comprehensive_scores_workbook({
            "batch_no": "20261020",
            "detail_criteria": [{"code": "1-01", "item": "用户为本"}],
            "scores": [{
                "person": "被评价人甲",
                "score": 4.5,
                "module_scores": {"品德素养": 4.5},
                "submitted_count": 1,
                "assigned_count": 1,
                "evaluator_details": [{
                    "evaluator_alias": "a",
                    "score": 4.5,
                    "scores": {"1-01": 5},
                    "submitted": True,
                }],
            }],
        })
        workbook = load_workbook(payload, read_only=True, data_only=True)
        self.assertEqual(["综合得分", "评价人明细"], workbook.sheetnames)
        detail_rows = list(workbook["评价人明细"].iter_rows(values_only=True))
        self.assertEqual("a", detail_rows[1][1])
        self.assertNotIn("评价人真实姓名", str(detail_rows))

    @patch.object(module, "load_criteria")
    @patch.object(module.pytds, "connect")
    def test_notification_only_sends_to_evaluators_with_pending_people(self, connect, load_criteria):
        load_criteria.return_value = [{"code": "1-01"}]
        cursor = Mock()
        cursor.fetchone.return_value = ("20261015",)
        cursor.fetchall.side_effect = [
            [("张三", "评价人甲"), ("李四", "评价人甲"), ("王五", "评价人乙")],
            [("张三", "评价人甲", "1-01"), ("王五", "评价人乙", "1-01")],
        ]
        connection = Mock()
        connection.cursor.return_value = cursor
        connect.return_value = connection
        sent = []

        result = module.send_evaluation_notifications(
            "https://example.com/ai/value-evaluation",
            sender=lambda name, message: sent.append((name, message)) or True,
        )

        self.assertEqual(1, result["notified"])
        self.assertEqual(1, result["skipped"])
        self.assertEqual("评价人甲", sent[0][0])
        self.assertIn("李四", sent[0][1])
        self.assertNotIn("张三", sent[0][1])
        self.assertIn("https://example.com/ai/value-evaluation", sent[0][1])

    @patch.object(module.pytds, "connect")
    def test_submission_uses_actual_score_table_timestamp_column(self, connect):
        cursor = Mock()
        cursor.fetchone.return_value = (1,)
        connection = Mock()
        connection.cursor.return_value = cursor
        connect.return_value = connection

        module._save_submission(
            "20261013",
            "被评价人",
            "评价人",
            [{"code": "1-1", "score": 4, "remark": ""}],
        )

        insert_sql = cursor.executemany.call_args.args[0]
        self.assertIn("PingJiaShiJian", insert_sql)
        self.assertNotIn(",RiQi)", insert_sql)
        connection.commit.assert_called_once()

    def test_score_control_is_a_dropdown(self):
        template = (Path(app_module.app.root_path) / "templates" / "value_evaluation.html").read_text(encoding="utf-8")
        self.assertIn('class="score-select"', template)
        self.assertIn("请选择分数", template)
        self.assertNotIn('type="radio"', template)

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
        ]
        payload = {"answers": [
            {"code": f"1-{i}", "score": 4 if i < 6 else 3, "remark": ""}
            for i in range(1, 7)
        ]}
        self.assertEqual(6, len(module.validate_submission(payload, criteria)))

        payload["answers"][0] = {"code": "1-1", "score": 1, "remark": ""}
        with self.assertRaisesRegex(ValueError, "原因不能少于 20 个字"):
            module.validate_submission(payload, criteria)
        payload["answers"][0]["remark"] = "该项表现与岗位要求存在明显差距，需要持续跟进并尽快改善"
        payload["answers"][1] = {"code": "1-2", "score": 5, "remark": "该项表现持续超出岗位预期，并对团队产生了显著积极影响"}
        self.assertEqual(6, len(module.validate_submission(payload, criteria)))

        for answer in payload["answers"][:6]:
            answer["score"] = 4
        with self.assertRaisesRegex(ValueError, "不能全部相同"):
            module.validate_submission(payload, criteria)

    def test_criterion_description_splits_and_recombines_score_points(self):
        original = "总体说明\n5 分：五分内容\n4分: 四分内容\n3 分：三分内容\n2 分：二分内容\n1 分：一分内容"
        base, scores = module.split_criterion_description(original)
        self.assertEqual("总体说明", base)
        self.assertEqual("五分内容", scores["5"])
        self.assertEqual("一分内容", scores["1"])
        combined = module.compose_criterion_description(base, scores)
        self.assertEqual(
            "总体说明\n5 分：五分内容\n4 分：四分内容\n3 分：三分内容\n2 分：二分内容\n1 分：一分内容",
            combined,
        )

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

    def test_assignment_upload_preview_accepts_required_headers(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["被评价人", "评价人", "关系", "匿名"])
        sheet.append(["张三", "李四", "同部门同事", "N"])
        payload = BytesIO()
        workbook.save(payload)
        payload.seek(0)
        result = module.parse_assignment_upload(
            FileStorage(stream=payload, filename="安排.xlsx"),
            default_batch_no="20261013",
        )
        self.assertEqual(1, result["count"])
        self.assertEqual("李四", result["rows"][0]["evaluator"])
        self.assertEqual([], result["errors"])

    def test_admin_page_uses_quanxian_permission(self):
        client = app_module.app.test_client()
        def check_permission(_user_id, function_name):
            return function_name != "value_evaluation_admin", "test"

        with patch.object(app_module.permission_manager, "check_user_permission", side_effect=check_permission):
            with client.session_transaction() as flask_session:
                flask_session["feishu_user_id"] = "dev_test"
                flask_session["feishu_user_name"] = "其他用户"
            self.assertEqual(403, client.get("/ai/value-evaluation/admin").status_code)

        with patch.object(app_module.permission_manager, "check_user_permission", return_value=(True, "ok")):
            with client.session_transaction() as flask_session:
                flask_session["feishu_user_name"] = "数据库已授权用户"
            response = client.get("/ai/value-evaluation/admin")
        self.assertEqual(200, response.status_code)
        body = response.get_data(as_text=True)
        self.assertIn("上传评价安排明细", body)
        self.assertIn("下载导入模板", body)
        self.assertTrue((Path(app_module.app.root_path) / "static" / "templates" / "360价值评价导入模板.xlsx").is_file())

    def test_admin_saves_only_requested_criterion(self):
        client = app_module.app.test_client()
        with client.session_transaction() as flask_session:
            flask_session["feishu_user_id"] = "dev_test"
            flask_session["feishu_user_name"] = "周俊成"
        payload = {"category": "责任", "item": "责任心", "description": "单项内容"}
        with (
            patch.object(app_module.permission_manager, "check_user_permission", return_value=(True, "ok")),
            patch.object(module, "save_one_criterion", return_value="1-3") as save_one,
        ):
            response = client.patch("/api/ai/value-evaluation/admin/criteria/1-3", json=payload)
        self.assertEqual(200, response.status_code)
        save_one.assert_called_once()
        submitted = save_one.call_args.args[0]
        self.assertEqual("1-3", submitted["code"])
        self.assertEqual("单项内容", submitted["description"])


if __name__ == "__main__":
    unittest.main()
