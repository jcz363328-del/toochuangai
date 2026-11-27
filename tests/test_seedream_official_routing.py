import unittest
from unittest.mock import Mock, patch
from Department.视觉设计部.xiaoha import openrouter_image_site as site
from Department.视觉设计部.xiaoha import generation_settings as settings
from Department.视觉设计部.xiaoha import canvas_api_proxy as canvas


class SeedreamOfficialRoutingTests(unittest.TestCase):
    def test_official_model_in_all_choices_and_legacy_names_match(self):
        self.assertIn(settings.SEEDREAM_MODEL, settings.IMAGE_MODELS)
        self.assertIn(settings.SEEDREAM_MODEL, site.MODEL_OPTIONS)
        self.assertIn(settings.SEEDREAM_MODEL, site.INFINITE_CANVAS_IMAGE_MODELS)
        for model in settings.SEEDREAM_MODEL_ALIASES:
            self.assertTrue(site.is_ark_seedream_model(model))
            self.assertEqual(site.resolve_omnia_image_model(model), '')
        self.assertEqual(settings.resolution_options(settings.SEEDREAM_MODEL), ('1K', '1.5K', '2K'))

    def test_every_image_entry_routes_legacy_and_current_model_to_official(self):
        for model in settings.SEEDREAM_MODEL_ALIASES:
            for name in ('call_omnia_sync_image_api', 'call_omnia_media_image_api', 'call_omnia_image_api', 'call_openrouter_images_api'):
                with self.subTest(model=model, entry=name), patch.object(site, 'call_ark_seedream_images_api', return_value={'images': ['ok']}) as ark, patch.object(
                    site.requests, 'post', side_effect=AssertionError('No third-party network allowed')
                ):
                    result = getattr(site, name)(model, '编辑', [], '3:2', '1.5K')
                    self.assertEqual(result['images'], ['ok'])
                    self.assertEqual(ark.call_args.kwargs['size'], '1.5K')
                    self.assertIn('3:2', ark.call_args.args[0])

    def test_job_selection_overrides_hardcoded_nano_before_provider_routing(self):
        @settings.with_job_image_settings
        def run(context):
            return site.call_openrouter_images_api(site.NANO_BANANA_MODEL, 'draw', resolution='4K')
        with patch.object(site, 'call_ark_seedream_images_api', return_value={'images': ['ok']}) as ark:
            run({'generation_settings': {'model': settings.SEEDREAM_MODEL, 'resolution': '1K'}})
        self.assertEqual(ark.call_args.kwargs['size'], '1K')

    def test_text_to_image_uses_byte_dance_endpoint_without_image_field(self):
        response = Mock(status_code=200)
        response.json.return_value = {'data': [{'url': 'https://example.test/result.png'}]}
        with patch.object(site, 'load_ark_api_key', return_value='test-key'), patch.object(site.requests, 'post', return_value=response) as post:
            result = site.call_openrouter_images_api(settings.SEEDREAM_MODEL, '蓝天下的一棵树', resolution='1K')
        self.assertEqual(post.call_args.args[0], site.ARK_IMAGES_URL)
        payload = post.call_args.kwargs['json']
        self.assertNotIn('image', payload)
        self.assertEqual(payload['model'], settings.SEEDREAM_MODEL)
        self.assertEqual(payload['size'], '1K')
        self.assertEqual(result['images'], ['https://example.test/result.png'])

    def test_unsupported_resolution_fails_before_network(self):
        with patch.object(site, 'load_ark_api_key', return_value='test-key'), patch.object(site.requests, 'post') as post:
            for size in ('4K', '512x512', '8192x8192'):
                with self.subTest(size=size), self.assertRaises(ValueError):
                    site.call_ark_seedream_images_api('draw', size=size)
        post.assert_not_called()

    def test_canvas_uses_same_official_route(self):
        from tests.test_canvas_api_proxy import fake_site
        runtime = fake_site()
        runtime.call_seedream_official_image_api = Mock(return_value={'images': ['data:image/png;base64,aW1hZ2U=']})
        result = canvas.generate_canvas_images(runtime, '/images/generations', {'model': settings.SEEDREAM_MODEL, 'prompt': 'draw', 'quality': 'medium'}, [])
        self.assertEqual(len(result['data']), 1)
        runtime.call_seedream_official_image_api.assert_called_once()
        runtime.call_omnia_image_api.assert_not_called()
        runtime.call_omnia_sync_image_api.assert_not_called()
