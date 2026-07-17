from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
