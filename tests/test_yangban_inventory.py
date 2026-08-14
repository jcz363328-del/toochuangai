from pathlib import Path
import unittest
from unittest.mock import patch

import yangban_inventory as inventory


def _valid_sample_payload(**overrides):
    payload = {
        "YangBanBianHao": "YB-001",
        "YangBanMingCheng": "测试样板",
        "FenLei": "研发",
        "GongChang": "一号工厂",
        "DanWei": "片",
        "FuZeRen": "张三",
        "KuWei": "",
        "ZhuangTai": "ZhengChang",
        "BeiZhu": "",
        "BiaoQianList": "[]",
    }
    payload.update(overrides)
    return payload


class YangbanInventoryTests(unittest.TestCase):
    def test_dashboard_prioritizes_photo_cards_over_inbound_totals(self):
        template = (
            Path(__file__).resolve().parents[1]
            / "templates"
            / "yangban_inventory.html"
        ).read_text(encoding="utf-8")

        self.assertNotIn("累计入库量", template)
        self.assertNotIn('id="recentFlowTable"', template)
        self.assertIn("sample-card-photo-grid", template)
        self.assertLess(
            template.index('id="dashboardSampleCards"'),
            template.index("检索中心"),
        )

    def test_sample_payload_uses_factory_owner_and_fixed_category(self):
        with (
            patch.object(inventory, "_tag_rows", return_value=[]),
            patch.object(
                inventory,
                "_validate_sample_kuwei",
                side_effect=lambda value, existing=None: str(value or "").strip(),
            ),
        ):
            result = inventory._sample_payload_from_request(_valid_sample_payload())

        self.assertEqual(result["FenLei"], "研发")
        self.assertEqual(result["GongChang"], "一号工厂")
        self.assertEqual(result["FuZeRen"], "张三")
        self.assertNotIn("GuiGe", result)
        self.assertNotIn("YuJingKuCun", result)

    def test_sample_payload_rejects_categories_outside_research_and_procurement(self):
        with (
            patch.object(inventory, "_tag_rows", return_value=[]),
            patch.object(inventory, "_validate_sample_kuwei", return_value=""),
        ):
            for category in ("", "生产", "研发/采购"):
                with self.subTest(category=category):
                    with self.assertRaisesRegex(ValueError, "分类只能选择研发或采购"):
                        inventory._sample_payload_from_request(
                            _valid_sample_payload(FenLei=category)
                        )

    def test_sample_payload_keeps_long_description_for_database(self):
        description = "样品描述" * 200
        with (
            patch.object(inventory, "_tag_rows", return_value=[]),
            patch.object(inventory, "_validate_sample_kuwei", return_value=""),
        ):
            result = inventory._sample_payload_from_request(
                _valid_sample_payload(BeiZhu=description)
            )

        self.assertEqual(result["BeiZhu"], description)

    def test_sample_payload_exposes_all_semicolon_separated_images(self):
        with patch.object(
            inventory,
            "_sample_image_filename_one",
            side_effect=lambda path: path.rsplit("\\", 1)[-1],
        ):
            result = inventory._sample_to_payload(
                {"TuPian": r"D:\tuchuangai\样板图\a.jpg;D:\tuchuangai\样板图\b.png"},
                {},
            )

        self.assertEqual(
            result["TuPianUrls"],
            [
                "/procurement/yangban/image-preview/a.jpg?profile=detail",
                "/procurement/yangban/image-preview/b.png?profile=detail",
            ],
        )
        self.assertEqual(
            result["TuPianThumbnailUrls"],
            [
                "/procurement/yangban/image-preview/a.jpg?profile=thumb",
                "/procurement/yangban/image-preview/b.png?profile=thumb",
            ],
        )
        self.assertEqual(
            result["TuPianOriginalUrls"],
            [
                "/procurement/yangban/image/a.jpg",
                "/procurement/yangban/image/b.png",
            ],
        )
        self.assertEqual(
            result["TuPianUrl"],
            "/procurement/yangban/image-preview/a.jpg?profile=thumb",
        )

    def test_dashboard_uses_twelve_item_pages_and_thumbnail_urls(self):
        template = (
            Path(__file__).resolve().parents[1]
            / "templates"
            / "yangban_inventory.html"
        ).read_text(encoding="utf-8")

        self.assertIn("dashboardPageSize: 12", template)
        self.assertIn('id="dashboardPrev"', template)
        self.assertIn('id="dashboardNext"', template)
        self.assertIn("row.TuPianThumbnailUrls", template)

    def test_flow_query_hides_outbound_and_includes_new_dimensions(self):
        select_sql, count_sql, params, page, page_size = inventory._build_flow_query({})

        self.assertIn("BianDongLeiXing, N'') <> N'ChuKu'", select_sql)
        self.assertIn("y.GongChang", select_sql)
        self.assertIn("y.FuZeRen", select_sql)
        self.assertIn("y.DanWei", select_sql)
        self.assertIn("BianDongLeiXing, N'') <> N'ChuKu'", count_sql)
        self.assertEqual(params, [])
        self.assertEqual(page, 1)
        self.assertEqual(page_size, 20)

    def test_pdf_location_resolves_independent_cabinet_three(self):
        result = inventory._resolve_pdf_location("40-A3")

        self.assertTrue(result["matched"])
        self.assertFalse(result["ambiguous"])
        self.assertEqual(result["highlight_count"], 1)
        self.assertEqual(len(result["layouts"]), 1)
        self.assertEqual(result["layouts"][0]["cabinet_number"], "3")
        self.assertEqual(len(result["layouts"][0]["blocks"]), 1)
        cabinet_block = result["layouts"][0]["blocks"][0]
        self.assertEqual(cabinet_block["page"], 1)
        self.assertEqual(cabinet_block["columns"], 12)
        self.assertEqual(
            [section["area"] for section in cabinet_block["sections"]],
            ["48", "52", "40", "51"],
        )
        area_40 = next(
            section
            for section in cabinet_block["sections"]
            if section["area"] == "40"
        )
        target = next(
            cell
            for row in area_40["rows"]
            for cell in row
            if cell["target"]
        )
        self.assertEqual((target["label"], target["row"], target["column"]), ("A3", 3, 1))

    def test_pdf_location_resolves_independent_cabinet_four(self):
        prefixed = inventory._resolve_pdf_location("23-A1")
        repeated = inventory._resolve_pdf_location("32-32")

        self.assertEqual(prefixed["layouts"][0]["cabinet_number"], "4")
        cabinet_block = prefixed["layouts"][0]["blocks"][0]
        self.assertEqual(cabinet_block["page"], 2)
        self.assertEqual(cabinet_block["columns"], 12)
        self.assertEqual(
            [section["area"] for section in cabinet_block["sections"]],
            ["32", "18", "64", "33", "05", "23"],
        )
        self.assertEqual(prefixed["highlight_count"], 1)
        area_23 = next(
            section
            for section in cabinet_block["sections"]
            if section["area"] == "23"
        )
        prefixed_target = next(
            cell
            for row in area_23["rows"]
            for cell in row
            if cell["target"]
        )
        self.assertEqual(prefixed_target["label"], "23A1")
        self.assertEqual(repeated["layouts"][0]["cabinet_number"], "4")
        self.assertEqual(len(repeated["layouts"][0]["blocks"][0]["sections"]), 6)
        self.assertEqual(repeated["highlight_count"], 8)

    def test_image_locations_resolve_cabinet_one_and_cabinet_two_top(self):
        cabinet_one = inventory._resolve_pdf_location("1-13A3")
        cabinet_two = inventory._resolve_pdf_location("2-66A3")

        self.assertEqual(cabinet_one["layouts"][0]["cabinet_number"], "1")
        self.assertEqual(len(cabinet_one["layouts"][0]["blocks"]), 1)
        target_one = next(
            cell
            for row in cabinet_one["layouts"][0]["blocks"][0]["rows"]
            for cell in row
            if cell["target"]
        )
        self.assertEqual(target_one["label"], "13 A3")
        self.assertEqual(target_one["span"], 2)

        self.assertEqual(cabinet_two["layouts"][0]["cabinet_number"], "2")
        self.assertEqual(len(cabinet_two["layouts"][0]["blocks"]), 1)
        target_two = next(
            cell
            for row in cabinet_two["layouts"][0]["blocks"][0]["rows"]
            for cell in row
            if cell["target"]
        )
        self.assertEqual(target_two["label"], "66 A3")

    def test_pdf_location_does_not_guess_unknown_legacy_code(self):
        result = inventory._resolve_pdf_location("0802")

        self.assertFalse(result["matched"])
        self.assertEqual(result["status"], "unmatched")
        self.assertEqual(result["layouts"], [])

    def test_pdf_location_options_use_area_position_format(self):
        options = {item["code"]: item for item in inventory._pdf_location_options()}

        self.assertIn("40-A3", options)
        self.assertIn("23-A1", options)
        self.assertIn("32-32", options)
        self.assertIn("1-13A1", options)
        self.assertIn("2-66A1", options)
        self.assertEqual(options["40-A3"]["area"], "40")
        self.assertIn("3号柜", options["40-A3"]["label"])
        self.assertIn("1号柜", options["1-13A1"]["label"])

    def test_pdf_area_only_still_returns_the_complete_numbered_cabinet(self):
        result = inventory._resolve_pdf_location("48")

        self.assertEqual(result["status"], "area")
        self.assertFalse(result["matched"])
        self.assertEqual(result["layouts"][0]["cabinet_number"], "3")
        self.assertEqual(len(result["layouts"][0]["blocks"]), 1)
        self.assertEqual(len(result["layouts"][0]["blocks"][0]["sections"]), 4)
        self.assertEqual(result["highlight_count"], 0)


if __name__ == "__main__":
    unittest.main()
