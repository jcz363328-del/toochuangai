import unittest
from unittest.mock import MagicMock, patch

import business_analysis_usage as usage
import app as app_module


class BusinessAnalysisUsageTests(unittest.TestCase):
    @patch.object(usage.pytds, "connect")
    def test_records_identity_and_request_metadata(self, connect):
        connection = MagicMock()
        connection.autocommit = False
        connect.return_value = connection

        usage.record_business_analysis_usage(
            user_id="ou_test",
            user_name="测试用户",
            access_path="/ai/business-analysis",
            client_ip="127.0.0.1",
            user_agent="test-agent",
        )

        connection.cursor.return_value.execute.assert_called_once_with(
            usage.INSERT_USAGE_SQL,
            (
                "ou_test",
                "测试用户",
                "/ai/business-analysis",
                "127.0.0.1",
                "test-agent",
                "测试用户",
            ),
        )
        connection.commit.assert_called_once_with()
        connection.close.assert_called_once_with()

    def test_successful_page_entry_is_recorded(self):
        app_module.app.config.update(TESTING=True)
        client = app_module.app.test_client()
        with client.session_transaction() as flask_session:
            flask_session["feishu_user_id"] = "ou_test"
            flask_session["feishu_user_name"] = "测试用户"
            flask_session["feishu_user_access_token"] = "test-token"

        with patch.object(
            app_module.permission_manager,
            "check_user_permission",
            return_value=(True, "test"),
        ), patch.object(app_module, "record_business_analysis_usage") as recorder:
            response = client.get(
                "/ai/business-analysis",
                headers={"User-Agent": "test-agent", "X-Forwarded-For": "10.0.0.8"},
            )

        self.assertEqual(response.status_code, 200)
        recorder.assert_called_once_with(
            user_id="ou_test",
            user_name="测试用户",
            access_path="/ai/business-analysis",
            client_ip="10.0.0.8",
            user_agent="test-agent",
        )


if __name__ == "__main__":
    unittest.main()
