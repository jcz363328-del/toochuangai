from datetime import datetime

from innovation.pending_reminder import (
    InnovationPendingReminder,
    build_pending_reminder_message,
    load_overdue_pending_projects,
)


NOW = datetime(2026, 7, 18, 9, 0, 0)


def _rows(_sql):
    return [
        ("1001", "AI部", datetime(2026, 7, 15, 8, 0, 0), "提案一", "提案一的内容"),
        ("1002", "AI部", datetime(2026, 7, 14, 9, 0, 0), "提案二", "提案二的内容"),
        ("1003", "技术部", datetime(2026, 7, 13, 9, 0, 0), "提案三", "提案三的内容"),
    ]


class FakeMessageService:
    def __init__(self):
        self.messages = []
        self.recipient_names = {
            "ou_ai_1": "AI用户一",
            "ou_ai_2": "AI用户二",
            "ou_tech_1": "技术用户一",
        }
        self.last_send_result = {}

    def get_department_contacts(self, assignee):
        return {
            "AI部": ["ou_ai_1", "ou_ai_2"],
            "技术部": ["ou_tech_1"],
        }.get(assignee, [])

    def send_message(self, recipient, message):
        self.messages.append((recipient, message))
        return True


def test_query_requires_every_status_to_be_pending_and_older_than_two_days():
    captured = []

    def query(sql):
        captured.append(sql)
        return _rows(sql)

    projects = load_overdue_pending_projects(now_dt=NOW, query_fn=query)
    assert len(projects) == 3
    assert "SUM(" in captured[0]
    assert "ELSE 1" in captured[0]
    assert "2026-07-16 09:00:00" in captured[0]
    assert "MIN(flow.[流转时间]) <" in captured[0]


def test_message_contains_project_content_and_elapsed_time():
    projects = load_overdue_pending_projects(now_dt=NOW, query_fn=_rows)
    message = build_pending_reminder_message("AI部", projects[:2], now_dt=NOW)
    assert "#1001" in message
    assert "提案一的内容" in message
    assert "3天1小时" in message
    assert "请尽快进入创新管理处理" in message


def test_one_grouped_message_is_sent_to_each_assignee_contact():
    service = FakeMessageService()
    reminder = InnovationPendingReminder(
        query_fn=_rows,
        service_factory=lambda: service,
        enabled=False,
    )
    result = reminder.run_once(now_dt=NOW, send_messages=True, include_message_details=True)

    assert result["overdue_count"] == 3
    assert result["assignee_count"] == 2
    assert result["recipient_count"] == 3
    assert result["success_count"] == 3
    assert len(service.messages) == 3

    ai_messages = [message for recipient, message in service.messages if recipient.startswith("ou_ai")]
    assert len(ai_messages) == 2
    assert all("#1001" in message and "#1002" in message for message in ai_messages)
    assert result["assignees"]["AI部"]["message"] == ai_messages[0]
    assert result["assignees"]["AI部"]["recipients"] == [
        {"id": "ou_ai_1", "name": "AI用户一", "success": True},
        {"id": "ou_ai_2", "name": "AI用户二", "success": True},
    ]
