import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest

from 图片 import multi_reference_composer as composer
from 图片 import openrouter_image_site as site


def analysis(prefix="a"):
    return {**{key: f"{prefix}-{key}" for key, _ in composer.COMPONENTS}, "prompt": f"{prefix}-full-prompt"}


def references():
    return composer.prepare_references(site, [
        {"name": "背景.png", "data": b"background", "type": "image/png"},
        {"name": "主体.png", "data": b"subject", "type": "image/png"},
    ])


class ComposerWorkerTests(unittest.TestCase):
    def api(self, **kwargs):
        return SimpleNamespace(
            IMAGE_SMART_ANALYSIS_MODEL="vision", NANO_BANANA_MODEL="image", DEFAULT_ASPECT_RATIO="自动",
            set_task_progress=Mock(), format_user_facing_error_message=str, **kwargs,
        )

    def test_each_reference_is_analyzed_in_its_own_request(self):
        api = self.api(call_openrouter=Mock(side_effect=[{"text": json.dumps(analysis("a"))}, {"text": json.dumps(analysis("b"))}]))
        refs = references()
        with ThreadPoolExecutor(max_workers=1) as executor:
            result = executor.submit(composer.run_job, api, {"composer_action": "analyze", "composer_references": refs, "job_id": "offline"}).result()
        self.assertEqual(api.call_openrouter.call_count, 2)
        for call, ref in zip(api.call_openrouter.call_args_list, refs):
            self.assertEqual(call.kwargs["uploaded_files"], [ref["file"]])
            self.assertEqual(call.kwargs["output_mode"], "text")
        self.assertEqual(len(result["multi_reference_analysis"]), 2)

    def test_retry_keeps_successful_analysis_and_retries_only_failed_reference(self):
        api = self.api(call_openrouter=Mock(side_effect=[{"text": json.dumps(analysis())}, RuntimeError("temporary")]))
        context = {"composer_action": "analyze", "composer_references": references()}
        first = composer.run_job(api, context)
        self.assertEqual(sum(bool(row.get("error")) for row in first["multi_reference_analysis"].values()), 1)
        api.call_openrouter = Mock(return_value={"text": json.dumps(analysis("retry"))})
        second = composer.run_job(api, {**context, "composer_cache": first["multi_reference_analysis"]})
        api.call_openrouter.assert_called_once()
        self.assertEqual(api.call_openrouter.call_args.kwargs["uploaded_files"][0]["data"], b"subject")
        self.assertTrue(all(row.get("analysis") for row in second["multi_reference_analysis"].values()))

    def test_changed_analysis_requirements_invalidate_cached_results(self):
        api = self.api(call_openrouter=Mock(return_value={"text": json.dumps(analysis())}))
        context = {"composer_action": "analyze", "composer_references": references()}
        first = composer.run_job(api, context)
        api.call_openrouter.reset_mock()
        composer.run_job(api, {**context, "composer_requirements": "focus on lighting", "composer_cache": first["multi_reference_analysis"]})
        self.assertEqual(api.call_openrouter.call_count, 2)

    def test_duplicate_bytes_are_analyzed_once_even_with_different_filenames(self):
        files = [references()[0]["file"], {**references()[0]["file"], "name": "renamed.png"}]
        self.assertEqual(len(composer.prepare_references(site, files)), 1)

    def test_malformed_model_output_is_rejected_instead_of_inventing_components(self):
        for text in ("not JSON", "[]", '{"prompt":"only a prompt"}', json.dumps({**analysis(), "texture": {"foo": "bar"}})):
            with self.subTest(text=text), self.assertRaises(RuntimeError):
                composer.parse_analysis(text)
        self.assertEqual(composer.parse_analysis("```json\n" + json.dumps(analysis()) + "\n```"), analysis())

    def test_composed_prompt_only_contains_selected_components(self):
        a, b = analysis("a"), analysis("b")
        prompt = composer.compose_prompt([
            {"component": "background", "reference_id": "a", "text": a["background"]},
            {"component": "subject", "reference_id": "b", "text": b["subject"]},
            {"component": "texture", "reference_id": "a", "text": "edited material"},
        ], "keep negative space")
        self.assertIn(a["background"], prompt)
        self.assertIn(b["subject"], prompt)
        self.assertIn("edited material", prompt)
        self.assertIn("keep negative space", prompt)
        for unwanted in (a["subject"], b["background"], a["prompt"], a["texture"], b["decoration"]):
            self.assertNotIn(unwanted, prompt)
        with self.assertRaises(ValueError):
            composer.compose_prompt([])

    def test_copy_is_only_added_when_explicitly_provided(self):
        selected = [{"component": "typography", "text": "bold serif"}]
        self.assertIn("不添加文字", composer.compose_prompt(selected))
        self.assertIn("Fresh look", composer.compose_prompt(selected, copy_text="Fresh look"))
        self.assertNotIn("不添加文字", composer.compose_prompt(selected, copy_text="Fresh look"))

    def test_generation_does_not_send_whole_reference_images(self):
        api = self.api(call_openrouter_images_api=Mock(return_value={"images": ["finished.png"]}))
        context = {"composer_action": "generate", "prompt": "selected components", "uploaded_files": [references()[0]["file"]], "aspect_ratio": "4:5"}
        result = composer.run_job(api, context)
        self.assertEqual(result["images"], ["finished.png"])
        self.assertEqual(api.call_openrouter_images_api.call_args.kwargs["uploaded_files"], [])
        self.assertEqual(api.call_openrouter_images_api.call_args.kwargs["aspect_ratio"], "4:5")

    def test_analysis_dispatch_does_not_create_image_history(self):
        with patch.object(site, "call_openrouter", return_value={"text": json.dumps(analysis())}), patch.object(site, "finalize_feature_job_result") as finalize:
            result = site.run_feature_job({"feature": {"key": composer.MULTI_REFERENCE_COMPOSER_FEATURE_KEY}, "composer_action": "analyze", "composer_references": references(), "output_mode": "text"})
        self.assertIn("multi_reference_analysis", result)
        finalize.assert_not_called()

    def test_new_feature_uses_existing_batch_generation_and_history_flow(self):
        context = {"feature": site.get_feature_by_key(composer.MULTI_REFERENCE_COMPOSER_FEATURE_KEY), "composer_action": "generate", "prompt": "chosen background", "output_mode": "image", "max_output_images": 3}
        with patch.object(site, "call_openrouter_images_api", side_effect=[{"images": [f"image-{i}"]} for i in range(3)]) as generate, patch.object(site, "finalize_feature_job_result", side_effect=lambda ctx, result, job_id: result):
            result = site.run_feature_job(context)
        self.assertEqual(generate.call_count, 3)
        self.assertEqual(result["images"], ["image-0", "image-1", "image-2"])

    def test_analysis_completion_preserves_existing_base_images(self):
        state = {"feature_results": {composer.MULTI_REFERENCE_COMPOSER_FEATURE_KEY: {"images": ["old.png"]}}}
        result = {"multi_reference_analysis": {"cache": {"analysis": analysis()}}}
        job = {"job_id": "done"}
        with patch.object(site.st, "session_state", state):
            site.store_completed_background_job_result(composer.MULTI_REFERENCE_COMPOSER_FEATURE_KEY, job, result)
            site.store_completed_background_job_result(composer.MULTI_REFERENCE_COMPOSER_FEATURE_KEY, job, result)
        self.assertEqual(state["feature_results"][composer.MULTI_REFERENCE_COMPOSER_FEATURE_KEY]["images"], ["old.png"])
        self.assertEqual(len(state[composer.STATE_KEY]["analyses"]), 1)


APP = '''
import streamlit as st
from unittest.mock import patch
from 图片 import openrouter_image_site as site
from 图片 import multi_reference_composer as composer
site.ensure_state()
page = st.radio('page', ['composer', 'other'], key='fixture_page')
st.session_state.setdefault('fixture_files', [
    {'name':'background.png','type':'image/png','data':b'background'},
    {'name':'subject.png','type':'image/png','data':b'subject'}])
if page == 'composer':
    with patch.object(site, 'render_multi_image_uploader', return_value=st.session_state.fixture_files), patch.object(site, 'render_result_preview'):
        composer.render(site, site.get_feature_by_key(composer.MULTI_REFERENCE_COMPOSER_FEATURE_KEY))
'''


class ComposerUiTests(unittest.TestCase):
    def app(self):
        app = AppTest.from_string(APP, default_timeout=30).run()
        cache = {composer.fingerprint("") + ":" + ref["id"]: {"analysis": analysis(str(index))} for index, ref in enumerate(references())}
        app.session_state[composer.STATE_KEY]["analyses"] = cache
        app.run()
        self.assertFalse(list(app.exception))
        return app

    def pick(self, app, field, index):
        return app.multiselect(key="composer_pick_" + field + "_" + composer.fingerprint("")[:12]).select(references()[index]["id"]).run()

    def test_user_can_mix_two_images_edit_and_submit_the_composed_prompt(self):
        app = self.app()
        self.pick(app, "background", 0)
        self.pick(app, "subject", 1)
        app.button(key="composer_compose").click().run()
        prompt = app.text_area(key="composer_prompt").value
        self.assertIn("0-background", prompt)
        self.assertIn("1-subject", prompt)
        self.assertNotIn("0-subject", prompt)
        app.text_area(key="composer_prompt").set_value(prompt + "\nmanual edit").run()
        app.number_input(key="composer_output_count").set_value(2).run()
        with patch.object(site, "submit_feature_job") as submit:
            app.button(key="composer_generate").click().run()
        self.assertFalse(list(app.exception))
        context = submit.call_args.args[1]
        self.assertIn("manual edit", context["prompt"])
        self.assertEqual(context["max_output_images"], 2)
        self.assertEqual(context["uploaded_files"], [])

    def test_drafts_and_selection_survive_leaving_the_page(self):
        app = self.app()
        self.pick(app, "background", 0)
        app.button(key="composer_compose").click().run()
        app.text_area(key="composer_prompt").set_value("edited draft").run()
        app.radio(key="fixture_page").set_value("other").run()
        app.radio(key="fixture_page").set_value("composer").run()
        self.assertFalse(list(app.exception))
        self.assertEqual(app.text_area(key="composer_prompt").value, "edited draft")
        self.assertFalse(app.button(key="composer_generate").disabled)
        self.assertEqual(app.multiselect[0].value, [references()[0]["id"]])

    def test_removed_reference_cannot_be_used_by_stale_selection(self):
        app = self.app()
        self.pick(app, "background", 0)
        app.button(key="composer_compose").click().run()
        app.session_state['fixture_files'] = [references()[1]["file"]]
        app.run()
        self.assertFalse(list(app.exception))
        self.assertEqual(app.multiselect[0].value, [])
        self.assertTrue(app.button(key="composer_generate").disabled)

    def test_selection_changes_require_recomposition(self):
        app = self.app()
        self.pick(app, "background", 0)
        app.button(key="composer_compose").click().run()
        self.pick(app, "texture", 1)
        self.assertTrue(app.button(key="composer_generate").disabled)
        app.button(key="composer_compose").click().run()
        self.assertFalse(app.button(key="composer_generate").disabled)

    def test_retry_button_only_submits_the_chosen_failed_reference(self):
        app = self.app()
        cache = app.session_state[composer.STATE_KEY]["analyses"]
        for ref in references():
            cache[composer.fingerprint("") + ":" + ref["id"]] = {"error": "temporary failure"}
        app.run()
        with patch.object(site, "submit_feature_job") as submit:
            app.button(key="composer_retry_" + references()[1]["id"]).click().run()
        self.assertFalse(list(app.exception))
        self.assertEqual([ref["id"] for ref in submit.call_args.args[1]["composer_references"]], [references()[1]["id"]])

    def test_clearing_count_uses_one_result(self):
        app = self.app()
        app.text_area(key="composer_prompt").set_value("manually entered prompt").run()
        app.number_input(key="composer_output_count").set_value(None).run()
        with patch.object(site, "submit_feature_job") as submit:
            app.button(key="composer_generate").click().run()
        self.assertFalse(list(app.exception))
        self.assertEqual(submit.call_args.args[1]["max_output_images"], 1)


if __name__ == "__main__":
    unittest.main()
