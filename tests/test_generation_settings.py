from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest

from Department.视觉设计部.xiaoha import generation_settings as settings
from Department.视觉设计部.xiaoha import feature_dispatch
from tests.test_omnia_task_recovery import OmniaTaskRecoveryTests


class GenerationSettingsTests(unittest.TestCase):
    def test_job_choices_override_hardcoded_defaults_and_reset_after_job(self):
        @settings.apply_image_settings
        def generate(model, resolution="", prompt=""):
            return model, resolution, prompt
        @settings.with_job_image_settings
        def job(context):
            with ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(copy_context().run, generate, "old-model", "4K", "原生 4K 输出").result()
        self.assertEqual(job({"generation_settings": {"model": "gpt-image-2.6-sunburst", "resolution": "2K"}}),
                         ("gpt-image-2.6-sunburst", "2K", "原生 2K 输出"))
        self.assertEqual(generate("default"), ("default", "2K", ""))

    def test_model_specific_resolution_parameters(self):
        self.assertEqual(settings.media_image_parameters("gpt-image-2.6-sunburst"), {"size": "2048x2048", "quality": "high"})
        self.assertEqual(settings.media_image_parameters("gpt-image-2.6-sunburst", "4K", "16:9")["size"], "3840x2160")
        self.assertEqual(settings.media_image_parameters("gemini-nano-banana-2.1"), {"aspect_ratio": "1:1", "image_size": "2K"})
        with self.assertRaises(ValueError):
            settings.media_image_parameters("Dola-Seedream-5.0-pro")
        with self.assertRaises(ValueError):
            settings.media_image_parameters("Dola-Seedream-5.0-pro", "4K")

    def test_submission_captures_choices_without_mutating_caller_or_queued_job(self):
        state = SimpleNamespace(background_jobs={}, background_job_queue=[])
        state.generation_choices = {"hd_batch": {"model": "gpt-image-2.6-sunburst", "resolution": "2K"}}
        state.get = lambda key, default=None: getattr(state, key, default)
        runtime = Mock(max_outstanding_jobs=64, max_account_jobs=8)
        runtime.get_generation_queue_state.return_value = {"state": "queued", "queue_position": 1}
        context = {"model": "old", "output_mode": "image"}
        feature_dispatch.submit_feature_job(
            {"key": "hd_batch"}, context,
            JIMENG_HD_FEATURE_KEY="jimeng_hd", JIMENG_HD_GLOBAL_QUEUE_KEY="hd", NANO_BANANA_MODEL="nano",
            clear_task_progress=Mock(), datetime=__import__("datetime").datetime,
            get_request_limiter=Mock(), get_task_runtime=lambda: runtime,
            run_queued_feature_job=Mock(), set_task_progress=Mock(), st=SimpleNamespace(session_state=state))
        queued = runtime.submit_generation_job.call_args.args[3]
        self.assertEqual(queued["model"], "gpt-image-2.6-sunburst")
        self.assertEqual(queued["resolution"], "2K")
        state.generation_choices["hd_batch"]["resolution"] = "4K"
        self.assertEqual(queued["generation_settings"]["resolution"], "2K")
        self.assertEqual(context, {"model": "old", "output_mode": "image"})


class SunburstRequestTests(OmniaTaskRecoveryTests):
    def test_sunburst_selected_in_job_reaches_provider_with_gpt_parameters(self):
        from Department.视觉设计部.xiaoha import openrouter_image_site as site
        self.get.side_effect = [self.completed, self.asset]
        @settings.with_job_image_settings
        def run(context):
            return site.call_openrouter_images_api(site.NANO_BANANA_MODEL, "edit", resolution="4K")
        run({"generation_settings": {"model": "gpt-image-2.6-sunburst", "resolution": "2K"}})
        payload = self.post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "gpt-image-2.6-sunburst")
        self.assertEqual(payload["parameters"], {"size": "2048x2048", "quality": "high"})


if __name__ == "__main__":
    unittest.main()
