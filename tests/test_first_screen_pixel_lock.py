import io
import unittest
from unittest.mock import patch

from PIL import Image, ImageChops, ImageDraw

from Department.视觉设计部.xiaoha import openrouter_image_site as site


class FirstScreenPixelLockTests(unittest.TestCase):
    @staticmethod
    def source():
        image = Image.new('RGB', (80, 160), (255, 232, 236))
        image.paste((30, 40, 50), (0, 0, 80, 60))
        image.putpixel((40, 65), (0, 0, 0))
        return image

    @staticmethod
    def decorated_source():
        image = Image.new('RGB', (160, 320), (255, 232, 236))
        image.paste((30, 40, 50), (0, 0, 160, 80))
        image.paste((70, 20, 50), (0, 0, 10, 320))
        image.paste((70, 20, 50), (150, 0, 160, 320))
        image.paste((35, 45, 55), (0, 300, 160, 320))
        draw = ImageDraw.Draw(image)
        # Low-contrast lettering must not be mistaken for empty background.
        for x in (25, 43, 61):
            draw.rectangle((x, 110, x + 3, 127), fill=(244, 221, 225))
            draw.rectangle((x, 124, x + 12, 127), fill=(244, 221, 225))
        image.paste((20, 100, 170), (100, 150, 132, 182))
        image.paste((230, 160, 25), (108, 158, 124, 174))
        return image

    @staticmethod
    def upload(image, name='source.png'):
        data = io.BytesIO()
        image.save(data, format='PNG')
        return {'data': data.getvalue(), 'name': name, 'type': 'image/png'}

    @classmethod
    def image_url(cls, image):
        return site.image_bytes_to_data_url(cls.upload(image)['data'], 'image/png')

    @staticmethod
    def decode(image_url):
        data, _ = site.load_image_bytes_from_url(image_url)
        with Image.open(io.BytesIO(data)) as image:
            return image.convert('RGB')

    def test_finds_lowest_content_pixel(self):
        self.assertEqual(site.detect_first_screen_fill_start(self.source()), 66)

    def test_colored_gradient_with_border_and_footer_is_fillable(self):
        source = Image.new('RGB', (100, 200), (20, 30, 40))
        for y in range(60, 180):
            for x in range(6, 94):
                source.putpixel((x, y), (255, 210 + (y - 60) // 5, 230))
        self.assertEqual(site.detect_first_screen_fill_bounds(source), (60, 180))

    def test_mask_preserves_side_footer_light_text_and_embedded_picture(self):
        source = self.decorated_source()
        mask = site.build_first_screen_fill_mask(source)
        for point in ((4, 200), (155, 200), (80, 310), (80, 30),
                      (26, 117), (48, 126), (61, 115), (102, 152), (115, 165)):
            with self.subTest(point=point):
                self.assertEqual(mask.getpixel(point), 0)
        self.assertEqual(mask.getpixel((80, 260)), 255)

    def test_manual_start_only_restricts_blank_mask_and_never_unlocks_artwork(self):
        source = self.decorated_source()
        automatic = site.build_first_screen_fill_mask(source)
        manual = site.build_first_screen_fill_mask(source, manual_start=95)
        self.assertIsNone(manual.crop((0, 0, source.width, 95)).getbbox())
        self.assertIsNone(ImageChops.subtract(manual, automatic).getbbox())
        for point in ((4, 200), (80, 310), (26, 117), (115, 165)):
            self.assertEqual(manual.getpixel(point), 0)
        self.assertEqual(manual.getpixel((80, 260)), 255)

    def test_pale_enclosed_foreground_is_not_used_as_background_seed(self):
        source = Image.new('RGB', (100, 200), (255, 220, 235))
        source.paste((30, 40, 50), (0, 0, 100, 50))
        source.paste((245, 210, 225), (25, 100, 75, 170))
        mask = site.build_first_screen_fill_mask(source)
        self.assertEqual(mask.getpixel((50, 125)), 0)
        self.assertIsNone(mask.crop((25, 100, 75, 170)).getbbox())
        self.assertEqual(mask.getpixel((10, 125)), 255)

    def test_contrast_two_lettering_remains_protected(self):
        source = Image.new('RGB', (100, 200), (255, 220, 235))
        source.paste((30, 40, 50), (0, 0, 100, 50))
        source.paste((253, 218, 233), (25, 100, 29, 131))
        source.paste((253, 218, 233), (25, 127, 41, 131))
        mask = site.build_first_screen_fill_mask(source)
        self.assertIsNone(mask.crop((25, 100, 29, 131)).getbbox())
        self.assertIsNone(mask.crop((25, 127, 41, 131)).getbbox())
        self.assertEqual(mask.getpixel((10, 125)), 255)

    def test_flat_foreground_inside_detailed_gradient_is_not_treated_as_blank(self):
        source = Image.new('RGB', (100, 200), (30, 40, 50))
        for y in range(50, 200):
            source.paste((255, 80 + y - 50, 220), (0, y, 100, y + 1))
        source.paste((255, 155, 220), (25, 100, 75, 170))
        with self.assertRaises(RuntimeError):
            site.build_first_screen_fill_mask(source)

    def test_safe_region_is_largest_available_rectangle(self):
        mask = Image.new('L', (140, 220), 0)
        mask.paste(255, (20, 80, 120, 200))
        mask.paste(255, (1, 1, 8, 10))
        self.assertEqual(site.find_first_screen_safe_region(mask), (20, 80, 120, 200))

    def test_diagonal_safe_rectangle_never_contains_protected_holes(self):
        mask = Image.new('L', (160, 320), 0)
        for x in range(10, 150):
            for y in range(50 + x // 2, 300):
                mask.putpixel((x, y), 255)
        mask.paste(0, (90, 180, 125, 210))
        bounds = site.find_first_screen_safe_region(mask)
        self.assertEqual(mask.crop(bounds).getextrema(), (255, 255))
        self.assertGreater((bounds[2] - bounds[0]) * (bounds[3] - bounds[1]), 5000)
        self.assertNotEqual(bounds, mask.getbbox())

    def test_insufficient_contiguous_blank_is_rejected_before_model_call(self):
        source = self.decorated_source()
        sparse_mask = Image.new('L', source.size, 0)
        for x in range(0, source.width, 8):
            for y in range(90, source.height, 8):
                sparse_mask.paste(255, (x, y, x + 2, y + 2))
        with patch.object(site, 'build_first_screen_fill_mask', return_value=sparse_mask), \
                patch.object(site, 'call_openrouter_images_api') as call:
            with self.assertRaises(RuntimeError):
                site.run_first_screen_selling_points_job({
                    'uploaded_files': [self.upload(source), self.upload(source, 'selling.png')],
                    'model': site.NANO_BANANA_MODEL,
                })
        call.assert_not_called()

    def test_content_without_blank_fails_even_when_manual_height_is_set(self):
        source = Image.new('RGB', (160, 320))
        for x in range(source.width):
            for y in range(source.height):
                source.putpixel((x, y), (255, 255, 255) if (x + y) % 2 else (0, 0, 0))
        for manual_start in (0, 100):
            with self.subTest(manual_start=manual_start), \
                    patch.object(site, 'call_openrouter_images_api') as call:
                with self.assertRaises(RuntimeError):
                    site.run_first_screen_selling_points_job({
                        'uploaded_files': [self.upload(source), self.upload(source, 'selling.png')],
                        'model': site.NANO_BANANA_MODEL,
                        'a_plus_first_screen_keep_height': manual_start,
                    })
                call.assert_not_called()

    def test_generation_changes_only_safe_rectangle_and_preserves_all_original_content(self):
        source = self.decorated_source()
        hero = self.upload(source, 'hero.png')
        reference = self.upload(Image.new('RGB', (80, 100), 'blue'), 'selling.png')
        mask = site.build_first_screen_fill_mask(source)
        bounds = site.find_first_screen_safe_region(mask)
        expected_size = (bounds[2] - bounds[0], bounds[3] - bounds[1])
        generated = self.image_url(Image.new('RGB', (70, 130), (5, 100, 200)))
        with patch.object(site, 'call_openrouter_images_api', return_value={'images': [generated]}) as call:
            result = site.run_first_screen_selling_points_job({
                'uploaded_files': [hero, reference], 'model': site.NANO_BANANA_MODEL,
                'a_plus_first_screen_requirements': '自由组合卖点',
            })
        call.assert_called_once()
        inputs = call.call_args.kwargs['uploaded_files']
        self.assertEqual(inputs[0], hero)
        self.assertEqual(inputs[2:], [reference])
        self.assertEqual(inputs[1]['name'], 'fill-area-guide.png')
        with Image.open(io.BytesIO(inputs[1]['data'])) as guide:
            self.assertEqual(guide.size, expected_size)
        prompt = call.call_args.kwargs['prompt']
        self.assertIn(f'{source.width}×{source.height}', prompt)
        self.assertIn(f'{expected_size[0]}×{expected_size[1]}', prompt)
        self.assertIn('自由组合卖点', prompt)
        image = self.decode(result['images'][0])
        self.assertEqual(image.size, source.size)
        difference = ImageChops.difference(image, source)
        self.assertIsNotNone(difference.getbbox())
        difference.paste((0, 0, 0), bounds)
        self.assertIsNone(difference.getbbox())
        for region in ((0, 0, 160, 80), (0, 80, 10, 320), (150, 80, 160, 320),
                       (0, 300, 160, 320), (20, 105, 80, 132), (100, 150, 132, 182)):
            self.assertEqual(image.crop(region).tobytes(), source.crop(region).tobytes())

    def test_size_fit_preserves_all_four_corner_markers_for_wide_and_tall_material(self):
        markers = ((255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0))
        background = (255, 220, 235)
        for original_size, target_size in (((120, 60), (60, 120)), ((60, 120), (120, 60))):
            with self.subTest(original_size=original_size):
                image = Image.new('RGB', original_size, (20, 30, 40))
                w, h = original_size
                for box, color in zip(((0, 0, 16, 16), (w - 16, 0, w, 16),
                                       (0, h - 16, 16, h), (w - 16, h - 16, w, h)), markers):
                    image.paste(color, box)
                result = site.fit_selling_points_region(image, target_size, background).convert('RGB')
                scale = min(target_size[0] / w, target_size[1] / h)
                fw, fh = round(w * scale), round(h * scale)
                left, top = (target_size[0] - fw) // 2, (target_size[1] - fh) // 2
                points = ((left + 2, top + 2), (left + fw - 3, top + 2),
                          (left + 2, top + fh - 3), (left + fw - 3, top + fh - 3))
                self.assertEqual(result.size, target_size)
                for point, color in zip(points, markers):
                    self.assertLessEqual(max(abs(a - b) for a, b in zip(result.getpixel(point), color)), 3)
                self.assertEqual(result.getpixel((0, 0)), background)

    def test_sparse_layout_is_accepted_without_forcing_material_to_fill_tail(self):
        result = {'images': [self.image_url(Image.new('RGB', (100, 200), 'pink'))]}
        with patch.object(site, 'call_openrouter_images_api', return_value=result) as call, \
                patch.object(site, 'selling_points_bottom_blank_fraction', return_value=.99):
            self.assertEqual(
                site.request_selling_points_layout('model', 'prompt', [], (100, 200), (255, 220, 235)),
                result,
            )
        call.assert_called_once()


if __name__ == '__main__':
    unittest.main()
