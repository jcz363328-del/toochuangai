import io
import unittest
from unittest.mock import patch
from PIL import Image
from 图片 import openrouter_image_site as site


class FirstScreenPixelLockTests(unittest.TestCase):
    def source(self):
        image = Image.new('RGB', (80, 160), (255, 232, 236))
        image.paste((30, 40, 50), (0, 0, 80, 60))
        image.putpixel((40, 65), (0, 0, 0))
        return image

    def test_restores_all_existing_content_and_keeps_generated_bottom(self):
        source = self.source()
        data = io.BytesIO()
        source.save(data, format='PNG')
        generated = Image.new('RGB', source.size, (5, 100, 200))
        output = io.BytesIO()
        generated.save(output, format='PNG')
        url = site.preserve_first_screen_pixels(
            site.image_bytes_to_data_url(output.getvalue(), 'image/png'),
            {'data': data.getvalue(), 'name': 'source.png', 'type': 'image/png'},
        )
        result, _ = site.load_image_bytes_from_url(url)
        with Image.open(io.BytesIO(result)) as image:
            self.assertEqual(image.size, source.size)
            self.assertEqual(image.convert('RGB').crop((0, 0, 80, 66)).tobytes(),
                             source.crop((0, 0, 80, 66)).tobytes())
            self.assertEqual(image.getpixel((40, 100))[:3], (5, 100, 200))

    def test_finds_lowest_content_pixel(self):
        self.assertEqual(site.detect_first_screen_fill_start(self.source()), 66)

    def test_rejects_source_without_bottom_blank(self):
        source = self.source()
        source.putpixel((20, 158), (0, 0, 0))
        with self.assertRaisesRegex(RuntimeError, '留白'):
            site.detect_first_screen_fill_start(source)

    def test_generates_only_bottom_without_sending_hero(self):
        source = self.source()
        original = io.BytesIO()
        source.save(original, format='PNG')
        hero = {'data': original.getvalue(), 'name': 'hero.png', 'type': 'image/png'}
        reference = {'data': b'reference-only', 'name': 'selling.png', 'type': 'image/png'}
        generated = io.BytesIO()
        Image.new('RGB', (80, 94), (5, 100, 200)).save(generated, format='PNG')
        with patch.object(site, 'call_openrouter_images_api', return_value={
            'images': [site.image_bytes_to_data_url(generated.getvalue(), 'image/png')]
        }) as call:
            result = site.run_first_screen_selling_points_job({
                'uploaded_files': [hero, reference], 'model': site.NANO_BANANA_MODEL,
                'a_plus_first_screen_requirements': '自由组合卖点',
            })
        self.assertEqual(call.call_args.kwargs['uploaded_files'], [reference])
        self.assertIn('80×94', call.call_args.kwargs['prompt'])
        self.assertIn('自由组合卖点', call.call_args.kwargs['prompt'])
        data, _ = site.load_image_bytes_from_url(result['images'][0])
        with Image.open(io.BytesIO(data)) as image:
            self.assertEqual(image.size, source.size)
            self.assertEqual(image.convert('RGB').crop((0, 0, 80, 66)).tobytes(),
                             source.crop((0, 0, 80, 66)).tobytes())
            self.assertEqual(image.getpixel((40, 159))[:3], (5, 100, 200))
