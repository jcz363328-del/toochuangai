from __future__ import annotations

import inspect
import unittest
from unittest.mock import patch

from 图片 import openrouter_image_site as site


class FeatureOutputCountTests(unittest.TestCase):
    def test_image_job_runs_one_independent_call_per_selected_result(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_run_once(context: dict[str, object]) -> dict[str, object]:
            calls.append(context)
            index = len(calls)
            self.assertEqual(context["max_output_images"], 1)
            self.assertTrue(context["_defer_feature_finalize"])
            self.assertIn(f"第 {index}/4 个独立候选", str(context["prompt"]))
            return {
                "images": [f"image-{index}"],
                "source_images": ["source"],
                "captions": [f"candidate-{index}"],
                "text": f"text-{index}",
            }

        context = {
            "feature": {"key": "scene_change", "output_mode": "image", "max_output_images": 1},
            "output_mode": "image",
            "max_output_images": 4,
            "prompt": "change scene",
        }
        with (
            patch.object(site, "_run_feature_job_once", side_effect=fake_run_once),
            patch.object(site, "finalize_feature_job_result", side_effect=lambda _ctx, result, _job_id: result),
        ):
            result = site.run_feature_job(context)

        self.assertEqual(len(calls), 4)
        self.assertEqual(result["images"], ["image-1", "image-2", "image-3", "image-4"])
        self.assertEqual(result["requested_output_count"], 4)
        self.assertEqual(result["completed_variant_count"], 4)

    def test_selected_result_count_is_capped_at_four(self) -> None:
        with (
            patch.object(
                site,
                "_run_feature_job_once",
                side_effect=lambda _ctx: {"images": ["image"], "text": ""},
            ) as run_once,
            patch.object(site, "finalize_feature_job_result", side_effect=lambda _ctx, result, _job_id: result),
        ):
            result = site.run_feature_job(
                {
                    "feature": {"key": "ai_qa_image", "output_mode": "image"},
                    "output_mode": "image",
                    "max_output_images": 99,
                    "prompt": "generate",
                }
            )

        self.assertEqual(run_once.call_count, site.FEATURE_OUTPUT_COUNT_MAX)
        self.assertEqual(result["requested_output_count"], site.FEATURE_OUTPUT_COUNT_MAX)

    def test_text_feature_is_never_repeated(self) -> None:
        expected = {"images": [], "text": "analysis"}
        with patch.object(site, "_run_feature_job_once", return_value=expected) as run_once:
            result = site.run_feature_job(
                {
                    "feature": {"key": site.IMAGE_SMART_ANALYSIS_FEATURE_KEY, "output_mode": "text"},
                    "output_mode": "text",
                    "max_output_images": 4,
                    "prompt": "analyze",
                }
            )

        run_once.assert_called_once()
        self.assertIs(result, expected)

    def test_every_image_ui_path_contains_output_count_selector(self) -> None:
        for renderer in (
            site.render_openrouter_feature,
            site.render_background_cutout_feature,
        ):
            source = inspect.getsource(renderer)
            self.assertIn("结果张数", source)
            self.assertIn("FEATURE_OUTPUT_COUNT_MAX", source)


if __name__ == "__main__":
    unittest.main()
