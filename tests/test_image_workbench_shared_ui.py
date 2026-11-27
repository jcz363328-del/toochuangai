import io
import unittest
from unittest.mock import patch

from PIL import Image
from streamlit.testing.v1 import AppTest

from Department.视觉设计部.xiaoha import openrouter_image_site as site


class SharedImageWorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.cache = {}
        self.patches = [
            patch.object(site, "load_upload_cache", side_effect=lambda key, **kw: self.cache.get(key, [])),
            patch.object(site, "get_model_reference_files", return_value=[]),
            patch.object(site, "get_skin_texture_reference_files", return_value=[]),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def app(self, key):
        return AppTest.from_string(f'''
from Department.视觉设计部.xiaoha import openrouter_image_site as site
site.ensure_state()
feature=site.get_feature_by_key({key!r})
site.render_openrouter_feature(feature,site.DEFAULT_MODEL,site.DEFAULT_ASPECT_RATIO)
''', default_timeout=30).run()

    def test_all_similar_image_tools_render_and_expose_top_history(self):
        for feature in site.FEATURES:
            key = feature["key"]
            if key in {"prepress_check", "infinite_canvas"}:
                continue
            with self.subTest(feature=key):
                app = self.app(key)
                self.assertFalse(list(app.exception), [e.message for e in app.exception])
                history_key = "fusion_open_history" if key == site.A_PLUS_FIRST_SCREEN_SELLING_POINTS_FEATURE_KEY else f"workbench_history_{key}"
                if key == site.MULTI_REFERENCE_COMPOSER_FEATURE_KEY:
                    history_key = "workbench_history_a_plus_canvas"
                self.assertEqual(app.button(key=history_key).label, "历史记录")

    def test_style_tool_submits_material_order_count_and_prompt(self):
        key = site.A_PLUS_STYLE_MODEL_REPLACE_FEATURE_KEY
        data = io.BytesIO()
        Image.new("RGB", (64, 96), "pink").save(data, format="PNG")
        self.cache[f"a_plus_style_model_replace_uploader_{key}"] = [
            {"data": data.getvalue(), "name": name, "type": "image/png"}
            for name in ("style.png", "model.png")
        ]
        with patch.object(site, "submit_feature_job") as submit:
            app = self.app(key)
            app.number_input(key=f"output_count_{key}").set_value(3).run()
            app.text_area[0].input("保留品牌色").run()
            app.button(key=f"process_{key}").click().run()
            self.assertFalse(list(app.exception), [e.message for e in app.exception])
            submit.assert_called_once()
            context = submit.call_args.args[1]
            self.assertEqual([f["name"] for f in context["uploaded_files"]], ["style.png", "model.png"])
            self.assertEqual(context["max_output_images"], 3)
            self.assertIn("保留品牌色", context["prompt"])


if __name__ == "__main__":
    unittest.main()
