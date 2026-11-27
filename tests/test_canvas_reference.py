import io
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from PIL import Image
from Department.视觉设计部.xiaoha import canvas_reference as reference
from Department.视觉设计部.xiaoha import openrouter_image_site as site
from Department.视觉设计部.xiaoha.multi_reference_composer import COMPONENTS


class CanvasReferenceTests(unittest.TestCase):
    def setUp(self):
        output = io.BytesIO()
        Image.new('RGB', (48, 72), 'purple').save(output, format='PNG')
        self.image = site.image_bytes_to_data_url(output.getvalue(), 'image/png')
        self.analysis = {key: title + '描述' for key, title in COMPONENTS}
        self.analysis['prompt'] = '完整反推文案'

    def test_each_analysis_request_only_sends_one_own_image(self):
        with patch.object(site, 'call_openrouter', return_value={'text': json.dumps(self.analysis)}) as call:
            result = reference.run_node(site, {'action': 'analyze', 'images': [self.image], 'prompt': '关注光线'}, 'tester')
        self.assertEqual(result['analysis'], self.analysis)
        self.assertEqual(result['text'], '完整反推文案')
        self.assertEqual(len(call.call_args.kwargs['uploaded_files']), 1)
        self.assertIn('关注光线', call.call_args.kwargs['prompt'])

    def test_rejects_multiple_reference_images_and_empty_composition(self):
        with patch.object(site, 'call_openrouter') as analyze, patch.object(site, 'run_feature_job') as generate:
            for payload in [
                {'action': 'analyze', 'images': []},
                {'action': 'analyze', 'images': [self.image, self.image]},
                {'action': 'generate', 'prompt': ''},
                {'action': 'generate', 'prompt': 'selected text', 'images': [self.image]},
            ]:
                with self.subTest(payload=payload), self.assertRaises(ValueError):
                    reference.run_node(site, payload, 'tester')
        analyze.assert_not_called()
        generate.assert_not_called()

    def test_selected_text_generates_without_pixels_and_saves_history(self):
        with patch.object(site, 'call_openrouter_images_api', return_value={'images': [self.image]}) as generate, \
             patch.object(site, 'finalize_feature_job_result', side_effect=lambda c, r, j: r) as history:
            result = reference.run_node(site, {'action': 'generate', 'prompt': '背景：紫色\n主体：花瓶'}, 'tester')
        self.assertEqual(generate.call_args.kwargs['uploaded_files'], [])
        self.assertIn('背景：紫色\n主体：花瓶', generate.call_args.kwargs['prompt'])
        self.assertEqual(result['images'], [self.image])
        self.assertEqual(history.call_args.args[0]['account_name'], 'tester')
        self.assertEqual(history.call_args.args[0]['feature']['key'], site.MULTI_REFERENCE_COMPOSER_FEATURE_KEY)

    def test_reference_entry_opens_a_plus_canvas(self):
        with patch('Department.视觉设计部.xiaoha.a_plus_canvas.render') as render:
            site.render_openrouter_feature(site.get_feature_by_key(site.MULTI_REFERENCE_COMPOSER_FEATURE_KEY), site.NANO_BANANA_MODEL, '4:3')
        self.assertEqual(render.call_args.args[1]['key'], 'a_plus_canvas')
        self.assertNotIn(site.MULTI_REFERENCE_COMPOSER_FEATURE_KEY, dict(site.SIDE_MENU_FEATURE_GROUPS)['A+'])

    def test_history_stays_available_from_canvas(self):
        from Department.视觉设计部.xiaoha.a_plus_canvas import render
        api = SimpleNamespace(st=Mock(), get_feature_by_key=site.get_feature_by_key,
                              MULTI_REFERENCE_COMPOSER_FEATURE_KEY=site.MULTI_REFERENCE_COMPOSER_FEATURE_KEY,
                              render_fusion_history_dialog=Mock(), render_replacement_infinite_canvas_feature=Mock())
        api.st.button.return_value = True
        render(api, site.get_feature_by_key('a_plus_canvas'), site.NANO_BANANA_MODEL, '4:3')
        self.assertEqual(api.render_fusion_history_dialog.call_args.args[0]['key'], site.MULTI_REFERENCE_COMPOSER_FEATURE_KEY)
