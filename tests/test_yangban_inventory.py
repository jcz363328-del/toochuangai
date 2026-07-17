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


if __name__ == "__main__":
    unittest.main()
