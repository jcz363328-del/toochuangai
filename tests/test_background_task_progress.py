from __future__ import annotations

import inspect
import unittest
from unittest.mock import patch

from 图片 import openrouter_image_site as site


class BackgroundTaskProgressTests(unittest.TestCase):
    def test_running_status_uses_an_animated_circular_progress_indicator(self) -> None:
        spinner_html = site.build_running_job_spinner_html(42, "正在生成 A+ <首屏>")

        self.assertIn("xiaoha-task-spinner-orbit", spinner_html)
        self.assertIn("rotate(360deg)", spinner_html)
        self.assertIn("42%", spinner_html)
        self.assertIn("正在生成 A+ &lt;首屏&gt;", spinner_html)
        self.assertNotIn("<首屏>", spinner_html)

    def test_spinner_progress_is_clamped_to_running_range(self) -> None:
        self.assertIn("99%", site.build_running_job_spinner_html(100, "即将完成"))
        self.assertIn("1%", site.build_running_job_spinner_html(0, "正在准备"))

    def test_running_progress_advances_in_small_steps_between_backend_stages(self) -> None:
        self.assertEqual(site.calculate_smooth_running_progress(1, 5), 3)
        self.assertEqual(site.calculate_smooth_running_progress(5, 12), 7)
        self.assertEqual(site.calculate_smooth_running_progress(12, 12), 13)
        self.assertEqual(site.calculate_smooth_running_progress(69, 12), 70)
        self.assertEqual(site.calculate_smooth_running_progress(70, 76), 72)
        self.assertEqual(site.calculate_smooth_running_progress(97, 100), 97)

    def test_completed_backend_result_animates_to_one_hundred(self) -> None:
        self.assertEqual(site.calculate_finishing_progress(20, 0), 20)
        self.assertEqual(site.calculate_finishing_progress(20, 4), 60)
        self.assertEqual(site.calculate_finishing_progress(20, 8), 100)
        self.assertEqual(site.calculate_finishing_progress(20, 30), 100)

        render_source = inspect.getsource(site.render_running_job_status)
        sync_source = inspect.getsource(site.sync_background_jobs)
        self.assertIn('run_every="1s"', render_source)
        self.assertIn("completion_pending", sync_source)

    def test_manual_element_recognition_runs_as_a_background_job(self) -> None:
        detected = {
            "id": 2,
            "name": "遗漏产品",
            "type": "product",
            "regions": [[100, 100, 400, 400]],
        }
        with (
            patch.object(
                site,
                "analyze_main_image_a_plus_element_at_point",
                return_value=detected,
            ) as analyze,
            patch.object(site, "set_task_progress") as progress,
        ):
            result = site.run_main_image_a_plus_manual_element_job(
                {"name": "template.png", "type": "image/png", "data": b"image"},
                (250, 300),
                [{"id": 1, "name": "模特", "regions": [[0, 0, 100, 100]]}],
                "manual-job",
            )

        self.assertEqual(result, detected)
        analyze.assert_called_once()
        self.assertEqual(progress.call_args_list[-1].args, ("manual-job", 100, "补漏识别完成"))

        render_source = inspect.getsource(site.render_openrouter_feature)
        self.assertIn("submit_main_image_a_plus_manual_element_job", render_source)
        self.assertNotIn(
            "new_element = analyze_main_image_a_plus_element_at_point",
            render_source,
        )


if __name__ == "__main__":
    unittest.main()
