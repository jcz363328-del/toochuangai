import unittest
from datetime import datetime
from pathlib import Path

from tk_customer_service_reminder import (
    TkCustomerServiceTrackingReminder,
    build_tracking_messages,
    group_tracking_records_by_importer,
    load_yesterday_tracking_records,
)


NOW = datetime(2026, 7, 29, 11, 30, 0)


def _tracking_rows(_sql):
    return [
        (
            "SKU-1",
            "83",
            101,
            "robot@张三",
            datetime(2026, 7, 28, 9, 0, 0),
            "ORDER-1",
            "TRACK-1",
            datetime(2026, 7, 28, 18, 0, 0),
            "备注一",
        ),
        (
            "SKU-2",
            "88",
            102,
            "张三",
            datetime(2026, 7, 28, 10, 0, 0),
            "ORDER-2",
            "TRACK-2",
            None,
            "",
        ),
        (
            "SKU-3",
            "90",
            103,
            "李四",
            datetime(2026, 7, 28, 11, 0, 0),
            "ORDER-3",
            "TRACK-3",
            None,
            "",
        ),
    ]


class FakeMessageService:
    def __init__(self):
        self.messages = []
        self.last_send_result = {}

    def send_message(self, recipient, message):
        self.messages.append((recipient, message))
        return True


class TkCustomerServiceReminderTests(unittest.TestCase):
    def test_reminder_is_started_with_the_flask_application(self):
        app_source = (
            Path(__file__).resolve().parents[1] / "app.py"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "from tk_customer_service_reminder import "
            "tk_customer_service_tracking_reminder",
            app_source,
        )
        self.assertIn("tk_customer_service_tracking_reminder.start()", app_source)

    def test_query_selects_previous_day_records_with_tracking_numbers(self):
        captured = []

        def query(sql):
            captured.append(sql)
            return _tracking_rows(sql)

        records = load_yesterday_tracking_records(now_dt=NOW, query_fn=query)

        self.assertEqual(len(records), 3)
        self.assertEqual(records[0]["DaoRuRen"], "张三")
        self.assertIn("2026-07-28", captured[0])
        self.assertIn("2026-07-29", captured[0])
        self.assertIn("GenZongHao", captured[0])
        self.assertIn("<> ''", captured[0])
        self.assertIn("dd_exact.GenZongHao", captured[0])
        self.assertIn("dd_order.GenZongHao", captured[0])
        self.assertIn("HAVING COUNT(DISTINCT", captured[0])
        self.assertIn("hz.DaoRuShiJian >=", captured[0])
        self.assertIn("hz.DaoRuShiJian <", captured[0])

    def test_records_are_grouped_by_normalized_importer_name(self):
        records = load_yesterday_tracking_records(
            now_dt=NOW,
            query_fn=_tracking_rows,
        )
        grouped = group_tracking_records_by_importer(records)

        self.assertEqual(list(grouped), ["张三", "李四"])
        self.assertEqual(len(grouped["张三"]), 2)
        self.assertEqual(len(grouped["李四"]), 1)

    def test_long_importer_messages_are_split_into_safe_batches(self):
        records = [
            {
                "FaYangDingDanHao": f"ORDER-{index}",
                "SKU": "SKU",
                "dian": "83",
                "GenZongHao": f"TRACK-{index}",
                "fahuoshijian": "",
                "kefubeizhu": "",
            }
            for index in range(41)
        ]

        messages = build_tracking_messages(
            "张三",
            records,
            NOW.date(),
            batch_size=40,
        )

        self.assertEqual(len(messages), 2)
        self.assertIn("第 1/2 批", messages[0])
        self.assertIn("第 2/2 批", messages[1])
        self.assertIn("ORDER-40", messages[1])

    def test_daily_run_sends_one_grouped_message_to_each_importer(self):
        service = FakeMessageService()
        reminder = TkCustomerServiceTrackingReminder(
            query_fn=_tracking_rows,
            service_factory=lambda: service,
            enabled=False,
        )

        result = reminder.run_once(
            now_dt=NOW,
            send_messages=True,
            include_message_details=True,
        )

        self.assertEqual(result["target_date"], "2026-07-28")
        self.assertEqual(result["record_count"], 3)
        self.assertEqual(result["importer_count"], 2)
        self.assertEqual(result["success_count"], 2)
        self.assertEqual(
            [recipient for recipient, _message in service.messages],
            ["张三", "李四"],
        )
        self.assertIn("ORDER-1", service.messages[0][1])
        self.assertIn("ORDER-2", service.messages[0][1])
        self.assertIn("TRACK-3", service.messages[1][1])

        second_result = reminder.run_once(now_dt=NOW, send_messages=True)
        self.assertEqual(second_result["skipped_count"], 2)
        self.assertEqual(len(service.messages), 2)

    def test_reminder_becomes_due_at_1130(self):
        reminder = TkCustomerServiceTrackingReminder(enabled=False)

        self.assertFalse(reminder.is_due(datetime(2026, 7, 29, 11, 29, 59)))
        self.assertTrue(reminder.is_due(datetime(2026, 7, 29, 11, 30, 0)))
        self.assertTrue(reminder.is_due(datetime(2026, 7, 29, 15, 0, 0)))


if __name__ == "__main__":
    unittest.main()
