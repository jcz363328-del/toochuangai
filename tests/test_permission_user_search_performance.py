import unittest
from unittest.mock import Mock, patch

from department_permissions import FeishuPermissionManager


class PermissionUserSearchPerformanceTests(unittest.TestCase):
    @patch("department_permissions.pytds.connect")
    def test_chinese_name_uses_local_mapping_before_feishu(self, connect):
        cursor = Mock()
        cursor.fetchone.return_value = ("ou_test_user", "蔡晶")
        connection = Mock()
        connection.cursor.return_value = cursor
        connect.return_value = connection

        manager = FeishuPermissionManager()
        manager.get_user_info_by_user_id = Mock(
            side_effect=AssertionError("中文姓名不应先请求飞书用户详情")
        )
        manager.get_user_departments = Mock(
            return_value=[{"name": "AI部"}]
        )

        result = manager.search_user_by_id_or_email("蔡晶")

        self.assertEqual(result["user_id"], "ou_test_user")
        self.assertEqual(result["name"], "蔡晶")
        self.assertEqual(result["departments"], ["AI部"])
        manager.get_user_info_by_user_id.assert_not_called()
        manager.get_user_departments.assert_called_once_with("ou_test_user")
        connection.close.assert_called_once()

    @patch("department_permissions.requests.request")
    def test_feishu_requests_have_a_default_timeout(self, request):
        request.return_value = Mock()
        manager = FeishuPermissionManager()

        manager._feishu_request("GET", "https://open.feishu.cn/test")

        request.assert_called_once_with(
            method="GET",
            url="https://open.feishu.cn/test",
            timeout=8,
        )


if __name__ == "__main__":
    unittest.main()
