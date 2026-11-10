from __future__ import annotations

import inspect
import unittest
from unittest.mock import patch

from 图片 import openrouter_image_site as site


class InfiniteCanvasImageFeatureTests(unittest.TestCase):
    def test_canvas_image_features_reuse_existing_xiaoha_features(self) -> None:
        expected = {
            "background_cutout",
            site.JIMENG_HD_FEATURE_KEY,
            "remove_eyelashes",
            "pose_change",
            "scene_change",
            "outpaint",
            "single_to_double",
            "skin_tone",
            "pupil_color_change",
            "eye_shape_change",
            "three_view",
            "ai_qa_image",
        }

        self.assertEqual(site.INFINITE_CANVAS_IMAGE_FEATURE_KEYS, expected)
        self.assertTrue(all(site.get_feature_by_key(key) is not None for key in expected))

    def test_reference_features_require_a_connected_reference_image(self) -> None:
        self.assertEqual(
            site.INFINITE_CANVAS_IMAGE_FEATURE_REFERENCE_KEYS,
            {
                "pose_change",
                "scene_change",
                "skin_tone",
                "pupil_color_change",
                "eye_shape_change",
                "three_view",
            },
        )

    def test_reference_notes_lock_main_image_and_reference_role(self) -> None:
        pose_notes = site.build_infinite_canvas_image_feature_notes("pose_change", 3, {})
        skin_notes = site.build_infinite_canvas_image_feature_notes("skin_tone", 2, {})

        self.assertIn("第 1 张图是当前图片节点中的主模特图", pose_notes)
        self.assertIn("后续 2 张连接图片只作为姿势参考", pose_notes)
        self.assertIn("第 2 张连接图片只作为肤色参考", skin_notes)
        self.assertIn("只迁移肤色", skin_notes)

    def test_outpaint_notes_keep_directional_pixel_settings(self) -> None:
        notes = site.build_infinite_canvas_image_feature_notes(
            "outpaint",
            1,
            {"top": 100, "bottom": 200, "left": 0, "right": 300},
        )

        self.assertIn("expand upward by 100px", notes)
        self.assertIn("expand downward by 200px", notes)
        self.assertNotIn("expand left by", notes)
        self.assertIn("expand right by 300px", notes)

    def test_static_server_exposes_generic_image_feature_endpoint(self) -> None:
        source = inspect.getsource(site.JimengStaticRequestHandler.do_POST)

        self.assertIn('api/image-feature', source)
        self.assertIn("serve_infinite_canvas_image_feature", source)

    def test_static_server_exposes_authenticated_usage_record_endpoint(self) -> None:
        source = inspect.getsource(site.JimengStaticRequestHandler.do_POST)

        self.assertIn('api/usage-record', source)
        self.assertIn("serve_infinite_canvas_usage_record", source)

    def test_canvas_usage_is_inserted_into_ai_tupian_with_feature_prefix(self) -> None:
        with patch.object(site, "insert_history_db_record") as insert_record:
            recorded = site.record_infinite_canvas_usage(
                account_name="测试账号",
                feature_name="模特换场景",
                model=site.NANO_BANANA_MODEL,
                image_count=2,
            )

        self.assertTrue(recorded)
        insert_record.assert_called_once()
        call_kwargs = insert_record.call_args.kwargs
        self.assertEqual(call_kwargs["account_name"], "测试账号")
        self.assertEqual(call_kwargs["feature_name"], "无限画布-模特换场景")
        self.assertEqual(call_kwargs["model"], site.NANO_BANANA_MODEL)
        self.assertEqual(call_kwargs["image_path"], "")
        self.assertEqual(call_kwargs["image_count"], 2)

    def test_canvas_feature_endpoints_record_successful_outputs(self) -> None:
        model_hd_source = inspect.getsource(site.JimengStaticRequestHandler.serve_infinite_canvas_model_hd)
        image_feature_source = inspect.getsource(site.JimengStaticRequestHandler.serve_infinite_canvas_image_feature)

        self.assertIn("record_infinite_canvas_usage", model_hd_source)
        self.assertIn("record_infinite_canvas_usage", image_feature_source)


if __name__ == "__main__":
    unittest.main()
