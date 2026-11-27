from __future__ import annotations

import io
import tempfile
import unittest
import zipfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from xml.sax.saxutils import escape

import sellfox_ads_bulk_report as bulk


def column_name(index: int) -> str:
    value = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        value = chr(65 + remainder) + value
    return value


def report_values(report_type: str, shop: str = "Shop A") -> dict[str, str]:
    mapping = (
        bulk.CAMPAIGN_HEADERS
        if report_type == bulk.CAMPAIGN_REPORT
        else bulk.TARGETING_HEADERS
    )
    values: dict[str, str] = {}
    serial = (date(2026, 8, 4) - date(1899, 12, 30)).days
    for source, target in mapping.items():
        if target == "shop_name":
            values[source] = shop
        elif target == "report_date":
            values[source] = str(serial)
        elif target in bulk.DECIMAL_FIELDS:
            values[source] = "1.25"
        elif target == "campaign_start_date":
            values[source] = "2026-01-02"
        elif target == "campaign_end_date":
            values[source] = "无结束日期"
        elif target == "campaign_id":
            values[source] = "9.87654321012345E+14"
        elif target == "portfolio_id":
            values[source] = ""
        elif target == "ad_group_id":
            values[source] = "000456"
        elif target == "target_id":
            values[source] = "000123"
        elif target == "campaign_name":
            values[source] = "Campaign A"
        elif target == "target_text":
            values[source] = "keyword-a"
        else:
            values[source] = "enabled"
    return values


def make_xlsx(report_type: str, shop: str = "Shop A") -> bytes:
    mapping = (
        bulk.CAMPAIGN_HEADERS
        if report_type == bulk.CAMPAIGN_REPORT
        else bulk.TARGETING_HEADERS
    )
    headers = list(mapping)
    values = report_values(report_type, shop)
    shared = "".join(f"<si><t>{escape(header)}</t></si>" for header in headers)
    header_cells = "".join(
        f'<c r="{column_name(index)}1" t="s"><v>{index - 1}</v></c>'
        for index in range(1, len(headers) + 1)
    )
    value_cells = []
    numeric_targets = bulk.DECIMAL_FIELDS | {"report_date", "campaign_id"}
    for index, header in enumerate(headers, start=1):
        value = values[header]
        reference = f"{column_name(index)}2"
        if mapping[header] in numeric_targets:
            value_cells.append(f'<c r="{reference}"><v>{escape(value)}</v></c>')
        else:
            value_cells.append(
                f'<c r="{reference}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
            )
    sheet = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData><row r="1">{header_cells}</row>'
        f'<row r="2">{"".join(value_cells)}</row></sheetData></worksheet>'
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Report" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    relationships = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/></Relationships>'
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", relationships)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
        archive.writestr(
            "xl/sharedStrings.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            f'count="{len(headers)}" uniqueCount="{len(headers)}">{shared}</sst>',
        )
    return buffer.getvalue()


class FakeResponse:
    def __init__(self, body: bytes, status_code: int = 200):
        self.body = body
        self.status_code = status_code
        self.headers = {"Content-Length": str(len(body))}
        self.closed = False

    def iter_content(self, chunk_size: int):
        for offset in range(0, len(self.body), chunk_size):
            yield self.body[offset : offset + chunk_size]

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, body: bytes):
        self.body = body
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse(self.body)


class FakeClient:
    def __init__(self, handler, body: bytes | None = None):
        self.handler = handler
        self.calls = []
        self.session = FakeSession(body or b"")

    def post_data(self, path, body, purpose):
        self.calls.append((path, body, purpose))
        return self.handler(path, body)


class XlsxParsingTests(unittest.TestCase):
    def test_parses_shared_inline_numeric_and_normalizes_campaign(self):
        headers, rows = bulk.parse_first_sheet_xlsx(
            make_xlsx(bulk.CAMPAIGN_REPORT)
        )
        parsed = bulk.normalize_report_rows(headers, rows, "活动日报")

        self.assertEqual(len(headers), 26)
        self.assertEqual(parsed[0]["shop_name"], "Shop A")
        self.assertEqual(parsed[0]["report_date"], "2026-08-04")
        self.assertEqual(parsed[0]["campaign_end_date"], "无结束日期")
        self.assertEqual(parsed[0]["campaign_id"], "9.87654321012345E+14")
        self.assertEqual(parsed[0]["spend"], Decimal("1.25"))

    def test_targeting_requires_every_official_column(self):
        headers, rows = bulk.parse_first_sheet_xlsx(
            make_xlsx(bulk.TARGETING_REPORT)
        )
        headers.remove("广告投放ID")
        with self.assertRaisesRegex(bulk.BulkReportError, "target_id"):
            bulk.normalize_report_rows(headers, rows, bulk.TARGETING_REPORT)

    def test_invalid_archive_fails(self):
        with self.assertRaises(bulk.BulkReportError):
            bulk.parse_first_sheet_xlsx(b"not an xlsx")


class ApiTaskTests(unittest.TestCase):
    def test_create_tasks_batches_and_uses_official_fields(self):
        counter = iter(("T1", "T2"))
        client = FakeClient(lambda _path, _body: {"id": next(counter)})
        tasks = bulk.create_report_tasks(
            client,
            ["S1", "S2", "S3"],
            "活动日报",
            "2026-08-01",
            "2026-08-07",
            batch_size=2,
        )

        self.assertEqual([task.task_id for task in tasks], ["T1", "T2"])
        self.assertEqual(client.calls[0][0], bulk.CREATE_TASK_PATH)
        self.assertEqual(
            client.calls[0][1],
            {
                "shopIds": ["S1", "S2"],
                "adTypeCode": "sp",
                "reportTypeCode": "adCampaignReport",
                "timeUnit": "daily",
                "reportStartDate": "2026-08-01",
                "reportEndDate": "2026-08-07",
            },
        )

    def test_polling_handles_generating_then_generated(self):
        states = iter(("生成中", "已生成"))

        def handler(_path, _body):
            state = next(states)
            row = {
                "id": "T1",
                "reportState": state,
                "reportTypeCode": bulk.CAMPAIGN_REPORT,
                "shopId": ["S1"],
                "downloadUrl": ["https://example.test/report.xlsx"] if state == "已生成" else [],
            }
            return {"rows": [row]}

        client = FakeClient(handler)
        reports = bulk.wait_for_report_tasks(
            client,
            [bulk.ReportTask("T1", ("S1",), bulk.CAMPAIGN_REPORT)],
            poll_interval_seconds=0,
        )

        self.assertEqual(len(reports), 1)
        self.assertNotIn("example.test", repr(reports[0]))
        self.assertEqual(client.calls[0][1]["taskIds"], ["T1"])

    def test_generated_task_without_url_fails(self):
        row = {
            "id": "T1",
            "reportState": "已生成",
            "reportTypeCode": bulk.CAMPAIGN_REPORT,
            "shopId": ["S1"],
            "downloadUrl": [],
        }
        client = FakeClient(lambda _path, _body: {"rows": [row]})
        with self.assertRaisesRegex(bulk.BulkReportError, "没有下载地址"):
            bulk.wait_for_report_tasks(
                client,
                [bulk.ReportTask("T1", ("S1",), bulk.CAMPAIGN_REPORT)],
                poll_interval_seconds=0,
            )

    def test_polling_timeout_fails(self):
        row = {
            "id": "T1",
            "reportState": "生成中",
            "reportTypeCode": bulk.CAMPAIGN_REPORT,
            "shopId": ["S1"],
            "downloadUrl": [],
        }
        ticks = iter((0.0, 2.0))
        client = FakeClient(lambda _path, _body: {"rows": [row]})
        with self.assertRaisesRegex(bulk.BulkReportError, "超时"):
            bulk.wait_for_report_tasks(
                client,
                [bulk.ReportTask("T1", ("S1",), bulk.CAMPAIGN_REPORT)],
                timeout_seconds=1,
                poll_interval_seconds=0,
                _clock=lambda: next(ticks),
                _sleep=lambda _seconds: None,
            )


class DownloadAndAttributionTests(unittest.TestCase):
    def test_download_uses_private_temporary_path(self):
        body = make_xlsx(bulk.CAMPAIGN_REPORT)
        client = FakeClient(lambda _path, _body: {}, body)
        ready = bulk.ReadyReport(
            "T1",
            ("S1",),
            bulk.CAMPAIGN_REPORT,
            ("https://example.test/report.xlsx",),
        )
        with bulk.downloaded_report_files(client, [ready]) as files:
            path = files[0].path
            self.assertTrue(path.exists())
            headers, _ = bulk.parse_first_sheet_xlsx(path)
            self.assertEqual(len(headers), 26)
        self.assertFalse(path.exists())

    def test_duplicate_shop_names_block_without_explicit_mapping(self):
        rows = [{"shop_name": "Same", "campaign_id": "C1"}]
        shops = {"S1": "Same", "S2": "Same"}
        with self.assertRaisesRegex(bulk.BulkReportError, "重复店铺名称"):
            bulk.attribute_rows_to_shops(rows, shops)
        result = bulk.attribute_rows_to_shops(
            rows,
            shops,
            explicit_name_to_id={"Same": "S2"},
        )
        self.assertEqual(result["S2"][0]["shop_id"], "S2")

    def test_parse_report_directory_merges_both_types(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "adCampaignReport-T1-1.xlsx").write_bytes(
                make_xlsx(bulk.CAMPAIGN_REPORT)
            )
            (root / "adTargeringReport-T2-1.xlsx").write_bytes(
                make_xlsx(bulk.TARGETING_REPORT)
            )
            result = bulk.parse_report_directory(root, {"Shop A": "S1"})

        self.assertEqual(len(result.files), 2)
        self.assertEqual(len(result.campaign_rows), 1)
        self.assertEqual(len(result.targeting_rows), 1)
        self.assertEqual(result.campaign_rows_by_shop["S1"][0]["shop_id"], "S1")


if __name__ == "__main__":
    unittest.main()
