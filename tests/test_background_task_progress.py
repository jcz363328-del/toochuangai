from __future__ import annotations

import inspect
import threading
import unittest
from unittest.mock import patch

from 图片 import openrouter_image_site as site


class BackgroundTaskProgressTests(unittest.TestCase):
    def test_submit_feature_job_keeps_existing_job_and_appends_next_one(self) -> None:
        class SessionState(dict):
            def __getattr__(self, name: str):
                return self[name]

            def __setattr__(self, name: str, value) -> None:
                self[name] = value

        runtime = site.TaskRuntime()
        first_started = threading.Event()
        release_first = threading.Event()
        call_count = 0

        def fake_run(_job_context):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                first_started.set()
                release_first.wait(timeout=3)
            return {"images": [f"result-{call_count}"]}

        state = SessionState(background_jobs={}, background_job_queue=[])
        feature = {"key": "queue-test", "name": "队列测试"}
        try:
            with (
                patch.object(site.st, "session_state", state),
                patch.object(site, "get_task_runtime", return_value=runtime),
                patch.object(site, "run_feature_job", side_effect=fake_run),
            ):
                first_job = site.submit_feature_job(
                    feature,
                    {"account_name": "tester", "output_mode": "image"},
                )
                self.assertTrue(first_started.wait(timeout=1))
                second_job = site.submit_feature_job(
                    feature,
                    {"account_name": "tester", "output_mode": "image"},
                )

                self.assertEqual(len(state.background_job_queue), 2)
                self.assertEqual(first_job["status"], "running")
                self.assertEqual(second_job["status"], "queued")
                self.assertEqual(second_job["queue_ahead"], 1)
                self.assertIs(state.background_jobs["queue-test"], second_job)
        finally:
            release_first.set()
            runtime.shutdown(wait=True)

    def test_same_account_generation_jobs_wait_in_fifo_order(self) -> None:
        runtime = site.TaskRuntime()
        first_started = threading.Event()
        release_first = threading.Event()
        second_started = threading.Event()
        execution_order: list[str] = []

        def first_job() -> str:
            execution_order.append("first")
            first_started.set()
            release_first.wait(timeout=3)
            return "first-result"

        def second_job() -> str:
            execution_order.append("second")
            second_started.set()
            return "second-result"

        try:
            first_future = runtime.submit_generation_job("account-a", "job-1", first_job)
            self.assertTrue(first_started.wait(timeout=1))
            second_future = runtime.submit_generation_job("account-a", "job-2", second_job)

            queue_state = runtime.get_generation_queue_state("job-2")
            self.assertEqual(queue_state["state"], "queued")
            self.assertEqual(queue_state["ahead_count"], 1)
            self.assertFalse(second_started.wait(timeout=0.1))

            release_first.set()
            self.assertEqual(first_future.result(timeout=2), "first-result")
            self.assertEqual(second_future.result(timeout=2), "second-result")
            self.assertEqual(execution_order, ["first", "second"])
        finally:
            release_first.set()
            runtime.shutdown(wait=True)

    def test_different_accounts_have_independent_queues(self) -> None:
        runtime = site.TaskRuntime()
        first_started = threading.Event()
        second_started = threading.Event()
        release_jobs = threading.Event()

        def blocking_job(started: threading.Event) -> None:
            started.set()
            release_jobs.wait(timeout=3)

        try:
            first_future = runtime.submit_generation_job(
                "account-a", "job-a", blocking_job, first_started
            )
            second_future = runtime.submit_generation_job(
                "account-b", "job-b", blocking_job, second_started
            )
            self.assertTrue(first_started.wait(timeout=1))
            self.assertTrue(second_started.wait(timeout=1))
            self.assertEqual(runtime.get_generation_queue_state("job-a")["state"], "running")
            self.assertEqual(runtime.get_generation_queue_state("job-b")["state"], "running")
            release_jobs.set()
            first_future.result(timeout=2)
            second_future.result(timeout=2)
        finally:
            release_jobs.set()
            runtime.shutdown(wait=True)

    def test_queued_card_and_submit_buttons_explain_queue_behavior(self) -> None:
        queued_html = site.build_queued_job_card_html(
            {
                "feature_name": "主图生A+ <测试>",
                "queue_ahead": 2,
                "submitted_at": "2026-07-20 12:00:00",
            }
        )
        render_source = inspect.getsource(site.render_openrouter_feature)
        cutout_source = inspect.getsource(site.render_background_cutout_feature)
        canvas_source = inspect.getsource(site.render_infinite_canvas_feature)

        self.assertIn("已加入任务队列", queued_html)
        self.assertIn("前面还有 2 个任务", queued_html)
        self.assertIn("主图生A+ &lt;测试&gt;", queued_html)
        self.assertIn("（加入队列）", render_source)
        self.assertIn("process_button_disabled = is_element_review_pending", render_source)
        self.assertNotIn("当前功能已有任务在后台处理中", render_source)
        self.assertNotIn("当前抠图任务正在处理中", cutout_source)
        self.assertNotIn("当前无限画布已有任务在后台处理", canvas_source)

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
