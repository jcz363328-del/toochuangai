from io import BytesIO

from openpyxl import Workbook
from werkzeug.datastructures import FileStorage

from tk_gmv_authorization import _parse_revenue, process_uploaded_workbooks


def _workbook_file(filename, rows):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sheet1"
    sheet.append(["Video ID", "Gross revenue", "Other"])
    for row in rows:
        sheet.append([row[0], row[1], "x"])
    payload = BytesIO()
    workbook.save(payload)
    payload.seek(0)
    return FileStorage(stream=payload, filename=filename)


class _FakeMessageService:
    def __init__(self, sent_messages):
        self.sent_messages = sent_messages

    def send_message(self, receive_id, message):
        self.sent_messages.append((receive_id, message))
        return True


def test_process_multiple_workbooks_deduplicates_and_groups_notifications():
    files = [
        _workbook_file("one.xlsx", [
            ("1001", "10.5"),
            ("1002", "0"),
            ("1003", "-2"),
            ("", "3"),
            ("1001", "2"),
        ]),
        _workbook_file("two.xlsx", [
            ("1001", "1"),
            ("1004", "not-a-number"),
            ("1005", "4"),
        ]),
    ]
    queried_ids = []

    def mapping_loader(video_ids):
        queried_ids.extend(video_ids)
        return {
            "1001": [{"dian": "83", "fuzeren": "负责人甲", "feishu_id": "ou_owner_a"}],
            "1003": [{"dian": "82", "fuzeren": "负责人甲", "feishu_id": "ou_owner_a"}],
            "1005": [{"dian": "88", "fuzeren": "负责人乙", "feishu_id": ""}],
        }

    sent_messages = []
    result = process_uploaded_workbooks(
        files,
        mapping_loader=mapping_loader,
        message_service_factory=lambda: _FakeMessageService(sent_messages),
    )

    assert queried_ids == ["1001", "1003", "1005"]
    assert result["summary"]["files_processed"] == 2
    assert result["summary"]["revenue_rows"] == 6
    assert result["summary"]["unique_videos"] == 3
    assert result["summary"]["database_matched_videos"] == 3
    assert result["summary"]["notifications_sent"] == 2
    assert result["summary"]["unresolved_items"] == 2

    assert len(sent_messages) == 1
    receive_id, message = sent_messages[0]
    assert receive_id == "ou_owner_a"
    assert "店铺：83\n视频ID：1001" in message
    assert "店铺：82\n视频ID：1003" in message
    assert message.count("视频ID：1001") == 1
    assert "该视频有GMV但是未授权，请在对应店铺广告后台绑定授权码" in message
    assert result["messages"] == [{
        "batch_number": 1,
        "fuzeren": "负责人甲",
        "video_count": 2,
        "video_ids": ["1001", "1003"],
        "content": message,
        "status": "sent",
        "status_text": "飞书推送成功",
    }]

    video_1001 = next(item for item in result["items"] if item["video_id"] == "1001")
    assert video_1001["gross_revenue"] == "10.5、2、1"
    assert video_1001["source_count"] == 3
    assert video_1001["status"] == "sent"
    assert video_1001["message_batch"] == 1
    video_1005 = next(item for item in result["items"] if item["video_id"] == "1005")
    assert video_1005["status"] == "no_feishu"
    assert any(item["status"] == "skipped" and not item["video_id"] for item in result["items"])


def test_missing_required_columns_is_rejected():
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Video ID", "Cost"])
    sheet.append(["1001", "12"])
    payload = BytesIO()
    workbook.save(payload)
    payload.seek(0)
    file = FileStorage(stream=payload, filename="missing.xlsx")

    try:
        process_uploaded_workbooks(
            [file],
            mapping_loader=lambda _: {},
            message_service_factory=lambda: _FakeMessageService([]),
        )
    except ValueError as exc:
        assert "Video ID 和 Gross revenue" in str(exc)
    else:
        raise AssertionError("missing Gross revenue column should fail")


def test_revenue_parser_handles_currency_and_accounting_negative():
    assert _parse_revenue("$1,234.50") == _parse_revenue("1234.5")
    assert _parse_revenue("(12.30)") == _parse_revenue("-12.3")
    assert _parse_revenue("--") == 0
    assert _parse_revenue("not-a-number") is None
