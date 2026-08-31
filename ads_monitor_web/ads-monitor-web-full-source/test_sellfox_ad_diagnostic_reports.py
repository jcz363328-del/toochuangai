from __future__ import annotations

import tempfile
import json
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import sellfox_ad_diagnostic_reports as reports
from sellfox_ads_bulk_report import DownloadedReport


class FakeClient:
    def __init__(self):
        self.calls: list[tuple[str, dict, str]] = []

    def post_data(self, path, body, purpose):
        self.calls.append((path, body, purpose))
        return {"id": f"T{len(self.calls)}"}


def fake_download(_client, _ready, destination):
    root = Path(destination)
    downloaded = []
    for index, code in enumerate(reports.REPORT_TYPES, start=1):
        path = root / f"{code}-T{index}-{index:04d}.xlsx"
        path.write_bytes(b"xlsx")
        downloaded.append(
            DownloadedReport(f"T{index}", (reports.SHOP_ID,), code, path)
        )
    return downloaded


class ReportRefreshTests(unittest.TestCase):
    def test_search_term_index_preserves_dimensions_and_all_attribution_metrics(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report_path = root / "adSearchTermReport-T1-0001.xlsx"
            report_path.touch()
            downloaded = DownloadedReport(
                "T1", (reports.SHOP_ID,), "adSearchTermReport", report_path
            )
            rows = [
                {
                    "店铺": reports.SHOP_NAME,
                    "日期": "2026-08-19",
                    "广告活动ID": "C1",
                    "用户搜索词": "lash clusters",
                    "广告投放ID": "T100",
                    "投放": "close-match",
                    "匹配类型": "自动",
                    "广告花费": "5",
                    "广告曝光量": "100",
                    "广告点击量": "10",
                    "广告订单量": "2",
                    "广告销售额": "20",
                    "广告销量": "3",
                    "本广告产品订单量": "1",
                    "其他产品广告订单量": "1",
                    "本广告产品销售额": "12",
                    "其他产品广告销售额": "8",
                    "本广告产品销量": "2",
                    "其他产品广告销量": "1",
                }
            ]
            destination = root / reports.SEARCH_TERM_INDEX_NAME
            with patch.object(
                reports, "parse_first_sheet_xlsx", return_value=(list(rows[0]), rows)
            ):
                reports.build_search_term_index(
                    [downloaded],
                    destination,
                    start=date(2026, 8, 6),
                    end=date(2026, 8, 19),
                )

            campaign = json.loads(destination.read_text(encoding="utf-8"))["campaigns"]["C1"]
            item = campaign["conversion"][0]
            self.assertEqual(item["identity"]["广告投放ID"], "T100")
            self.assertEqual(item["units"], 3)
            self.assertEqual(item["same_orders"], 1)
            self.assertEqual(item["same_sales"], 12)
            self.assertEqual(item["other_units"], 1)
            self.assertEqual(item["latest_date"], "2026-08-19")
            self.assertEqual(campaign["conversion_summary"]["orders"], 2)
            self.assertEqual(campaign["conversion_summary"]["attention_count"], 1)
            self.assertEqual(campaign["conversion_summary"]["sample_insufficient_count"], 0)
            self.assertEqual(campaign["conversion_summary"]["max_clicks_term"]["clicks"], 10)

    def test_search_term_index_merges_all_downloaded_parts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            downloads = []
            for index in (1, 2):
                path = root / f"adSearchTermReport-T1-{index:04d}.xlsx"
                path.touch()
                downloads.append(
                    DownloadedReport(f"T{index}", (reports.SHOP_ID,), "adSearchTermReport", path)
                )
            base = {
                "店铺": reports.SHOP_NAME,
                "广告活动ID": "C1",
                "用户搜索词": "lash clusters",
                "广告投放ID": "T100",
                "投放": "close-match",
                "匹配类型": "自动",
                "广告曝光量": "10",
                "广告点击量": "2",
                "广告订单量": "1",
                "广告销售额": "10",
            }
            parts = [
                [{**base, "日期": "2026-08-18", "广告花费": "1"}],
                [{**base, "日期": "2026-08-19", "广告花费": "2"}],
            ]
            destination = root / reports.SEARCH_TERM_INDEX_NAME
            with patch.object(
                reports,
                "parse_first_sheet_xlsx",
                side_effect=[(list(parts[0][0]), parts[0]), (list(parts[1][0]), parts[1])],
            ):
                reports.build_search_term_index(
                    downloads,
                    destination,
                    start=date(2026, 8, 6),
                    end=date(2026, 8, 19),
                )

            item = json.loads(destination.read_text(encoding="utf-8"))["campaigns"]["C1"]["conversion"][0]
            self.assertEqual(item["spend"], 3)
            self.assertEqual(item["orders"], 2)
            self.assertEqual(item["data_days"], 2)
            meta = json.loads(destination.read_text(encoding="utf-8"))["meta"]
            self.assertEqual(meta["data_start_date"], "2026-08-18")
            self.assertEqual(meta["data_end_date"], "2026-08-19")
            self.assertEqual(meta["data_days"], 2)

    def test_search_term_index_rejects_missing_out_of_window_and_empty_dates(self):
        cases = (
            ("missing", [{"店铺": reports.SHOP_NAME, "日期": ""}]),
            ("malformed", [{"店铺": reports.SHOP_NAME, "日期": "not-a-date"}]),
            ("before", [{"店铺": reports.SHOP_NAME, "日期": "2026-08-05"}]),
            ("after", [{"店铺": reports.SHOP_NAME, "日期": "2026-08-20"}]),
            ("empty", []),
        )
        for label, rows in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                report_path = root / "adSearchTermReport-T1-0001.xlsx"
                report_path.touch()
                downloaded = DownloadedReport(
                    "T1", (reports.SHOP_ID,), "adSearchTermReport", report_path
                )
                destination = root / reports.SEARCH_TERM_INDEX_NAME
                with patch.object(
                    reports,
                    "parse_first_sheet_xlsx",
                    return_value=(["店铺", "日期", "广告活动ID"], rows),
                ):
                    with self.assertRaises(reports.DiagnosticReportError):
                        reports.build_search_term_index(
                            [downloaded],
                            destination,
                            start=date(2026, 8, 6),
                            end=date(2026, 8, 19),
                        )
                self.assertFalse(destination.exists())

    def test_creates_all_eight_sp_daily_report_types(self):
        client = FakeClient()
        tasks = reports.create_deep_report_tasks(
            client,
            date(2026, 8, 6),
            date(2026, 8, 19),
        )

        self.assertEqual([task.report_type_code for task in tasks], list(reports.REPORT_TYPES))
        self.assertEqual(len(client.calls), 8)
        for _, body, _ in client.calls:
            self.assertEqual(body["shopIds"], [reports.SHOP_ID])
            self.assertEqual(body["adTypeCode"], "sp")
            self.assertEqual(body["timeUnit"], "daily")

    def test_report_window_uses_d_minus_two_and_fourteen_days(self):
        start, end = reports.report_window(date(2026, 8, 21))

        self.assertEqual(start, date(2026, 8, 6))
        self.assertEqual(end, date(2026, 8, 19))

    def test_validation_failure_preserves_previous_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            destination = parent / "ad_diagnostic_reports"
            destination.mkdir()
            marker = destination / "previous.txt"
            marker.write_text("old", encoding="utf-8")
            client = FakeClient()
            parsed = (["店铺", "日期", "广告活动ID"], [{"店铺": "Other Shop"}])
            with (
                patch.object(reports, "wait_for_report_tasks", side_effect=lambda _c, tasks, **_k: tasks),
                patch.object(reports, "download_report_files_to_directory", side_effect=fake_download),
                patch.object(reports, "parse_first_sheet_xlsx", return_value=parsed),
            ):
                with self.assertRaises(reports.DiagnosticReportError):
                    reports.refresh_reports(
                        client,
                        destination,
                        as_of=date(2026, 8, 21),
                    )

            self.assertEqual(marker.read_text(encoding="utf-8"), "old")
            self.assertFalse(list(parent.glob(".ad_diagnostic_reports.staging-*")))
            self.assertFalse(list(parent.glob(".ad_diagnostic_reports.backup-*")))

    def test_success_replaces_previous_directory_after_full_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            destination = parent / "ad_diagnostic_reports"
            destination.mkdir()
            (destination / "previous.txt").write_text("old", encoding="utf-8")
            client = FakeClient()
            parsed = (
                ["店铺", "日期", "广告活动ID"],
                [{"店铺": reports.SHOP_NAME, "日期": "2026-08-19", "广告活动ID": "C1"}],
            )
            with (
                patch.object(reports, "wait_for_report_tasks", side_effect=lambda _c, tasks, **_k: tasks),
                patch.object(reports, "download_report_files_to_directory", side_effect=fake_download),
                patch.object(reports, "parse_first_sheet_xlsx", return_value=parsed),
            ):
                summary = reports.refresh_reports(
                    client,
                    destination,
                    as_of=date(2026, 8, 21),
                )

            self.assertEqual(summary["report_start_date"], "2026-08-06")
            self.assertEqual(summary["report_end_date"], "2026-08-19")
            self.assertEqual(summary["file_count"], 8)
            self.assertFalse((destination / "previous.txt").exists())
            self.assertEqual(len(list(destination.glob("*.xlsx"))), 8)
            self.assertFalse(list(parent.glob(".ad_diagnostic_reports.staging-*")))
            self.assertFalse(list(parent.glob(".ad_diagnostic_reports.backup-*")))


if __name__ == "__main__":
    unittest.main()
