import io
import unittest
from unittest.mock import patch

from PIL import Image
from streamlit.testing.v1 import AppTest

from Department.视觉设计部.xiaoha import openrouter_image_site as site


class FirstScreenWorkbenchUITests(unittest.TestCase):
    def setUp(self):
        self.feature_key = site.A_PLUS_FIRST_SCREEN_SELLING_POINTS_FEATURE_KEY
        self.hero_key = f"a_plus_first_screen_hero_uploader_{self.feature_key}"
        self.material_key = f"a_plus_first_screen_selling_only_uploader_{self.feature_key}"
        buffer = io.BytesIO()
        Image.new("RGB", (40, 80), "pink").save(buffer, format="PNG")
        self.image = {"data": buffer.getvalue(), "name": "sample.png", "type": "image/png"}
        self.cache = {}
        self.patches = [
            patch.object(site, "load_upload_cache", side_effect=lambda key, **kw: list(self.cache.get(key, []))),
            patch.object(site, "remove_upload_cache_item", side_effect=lambda key, index: self.cache[key].pop(index)),
            patch.object(site, "clear_upload_cache", side_effect=lambda key: self.cache.pop(key, None)),
            patch.object(site, "reorder_upload_cache_item", side_effect=self.reorder),
        ]
        for mock in self.patches:
            mock.start()
            self.addCleanup(mock.stop)

    def reorder(self, key, source, target):
        self.cache[key].insert(target, self.cache[key].pop(source))

    def app(self):
        return AppTest.from_string('''
from Department.视觉设计部.xiaoha import openrouter_image_site as site
site.ensure_state()
feature = site.get_feature_by_key(site.A_PLUS_FIRST_SCREEN_SELLING_POINTS_FEATURE_KEY)
site.render_openrouter_feature(feature, site.DEFAULT_MODEL, site.DEFAULT_ASPECT_RATIO)
''', default_timeout=30).run()

    def assert_ok(self, app):
        self.assertFalse(list(app.exception), [e.message for e in app.exception])

    def test_missing_materials_disable_generation_and_prompt_preserves_text(self):
        app = self.app()
        self.assert_ok(app)
        self.assertTrue(app.button(key=f"process_{self.feature_key}").disabled)
        app.text_area[0].input("保留品牌色").run()
        app.run()
        self.assert_ok(app)
        self.assertEqual(app.text_area[0].value, "保留品牌色")
        self.assertFalse(any("fusion_chip" in str(b.key) for b in app.button))

    def test_top_history_opens_existing_records_for_current_account(self):
        with patch.object(site, "ensure_history_records_loaded", return_value=[]) as load:
            app = self.app()
            load.assert_not_called()
            app.button(key="fusion_open_history").click().run()
            self.assert_ok(app)
            load.assert_called_once()
            self.assertEqual(load.call_args.args[0], self.feature_key)
            self.assertTrue(any(c.value == "暂无历史图片" for c in app.caption))

    def test_reorder_and_remove_update_materials_and_readiness(self):
        first = dict(self.image, name="first.png")
        second = dict(self.image, name="second.png")
        self.cache.update({self.hero_key: [self.image], self.material_key: [first, second]})
        app = self.app()
        self.assert_ok(app)
        self.assertFalse(app.button(key=f"process_{self.feature_key}").disabled)
        app.button(key=f"reorder_upload_preview_{self.material_key}_0_1").click().run()
        self.assert_ok(app)
        self.assertEqual([i["name"] for i in self.cache[self.material_key]], ["second.png", "first.png"])
        app.button(key=f"delete_upload_upload_preview_{self.material_key}_0_0").click().run()
        self.assertEqual([i["name"] for i in self.cache[self.material_key]], ["first.png"])
        app.button(key=f"clear_upload_{self.material_key}").click().run()
        self.assert_ok(app)
        self.assertTrue(app.button(key=f"process_{self.feature_key}").disabled)

    def test_footer_submits_hero_first_with_selected_settings(self):
        self.cache.update({
            self.hero_key: [dict(self.image, name="hero.png")],
            self.material_key: [dict(self.image, name="material.png")],
        })
        with patch.object(site, "submit_feature_job") as submit:
            app = self.app()
            app.number_input(key=f"output_count_{self.feature_key}").set_value(2).run()
            app.text_area[0].input("保留品牌色").run()
            app.button(key=f"process_{self.feature_key}").click().run()
            self.assert_ok(app)
            submit.assert_called_once()
            context = submit.call_args.args[1]
            self.assertEqual([item["name"] for item in context["uploaded_files"]], ["hero.png", "material.png"])
            self.assertEqual(context["max_output_images"], 2)
            self.assertEqual(context["a_plus_first_screen_requirements"], "保留品牌色")

    def test_result_switch_and_zoom_render_without_changing_results(self):
        app = self.app()
        url = site.image_bytes_to_data_url(self.image["data"], "image/png")
        app.session_state["feature_results"] = {self.feature_key: {"images": [url, url]}}
        app.run()
        self.assert_ok(app)
        app.selectbox(key=f"fusion_result_index_{self.feature_key}").select(1).run()
        app.select_slider(key="fusion_result_zoom").set_value(75).run()
        self.assert_ok(app)
        self.assertEqual(len(app.session_state["feature_results"][self.feature_key]["images"]), 2)


if __name__ == "__main__":
    unittest.main()
