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
        source = Image.new('RGB', (80, 160))
        for y in range(160):
            for x in range(80):
                source.putpixel((x,y), (255,255,255) if x % 2 else (0,0,0))
        with self.assertRaisesRegex(RuntimeError, '填充区域'):
            site.detect_first_screen_fill_start(source)

    def test_colored_gradient_with_border_and_footer_is_fillable(self):
        source = Image.new('RGB', (100, 200), (20,30,40))
        for y in range(60, 180):
            for x in range(6, 94):
                source.putpixel((x,y), (255,210 + (y-60)//5,230))
        self.assertEqual(site.detect_first_screen_fill_bounds(source), (60,180))

    def test_design_uses_full_canvas_context_and_restores_original_hero(self):
        source = self.source()
        original = io.BytesIO()
        source.save(original, format='PNG')
        hero = {'data': original.getvalue(), 'name': 'hero.png', 'type': 'image/png'}
        reference = {'data': b'reference-only', 'name': 'selling.png', 'type': 'image/png'}
        generated = io.BytesIO()
        Image.new('RGB', (80, 100), (5, 100, 200)).save(generated, format='PNG')
        with patch.object(site, 'call_openrouter_images_api', return_value={
            'images': [site.image_bytes_to_data_url(generated.getvalue(), 'image/png')]
        }) as call, patch.object(site, 'selling_points_bottom_blank_fraction', return_value=0):
            result = site.run_first_screen_selling_points_job({
                'uploaded_files': [hero, reference], 'model': site.NANO_BANANA_MODEL,
                'a_plus_first_screen_requirements': '自由组合卖点',
            })
        self.assertEqual(call.call_args.kwargs['uploaded_files'][0], hero)
        self.assertEqual(call.call_args.kwargs['uploaded_files'][2:], [reference])
        self.assertEqual(call.call_args.kwargs['uploaded_files'][1]['name'], 'fill-area-guide.png')
        self.assertIn('80×160', call.call_args.kwargs['prompt'])
        self.assertIn('只输出 80×100', call.call_args.kwargs['prompt'])
        self.assertIn('关键安全区', call.call_args.kwargs['prompt'])
        self.assertIn('自由组合卖点', call.call_args.kwargs['prompt'])
        data, _ = site.load_image_bytes_from_url(result['images'][0])
        with Image.open(io.BytesIO(data)) as image:
            self.assertEqual(image.size, source.size)
            self.assertEqual(image.convert('RGB').crop((0, 0, 80, 60)).tobytes(),
                             source.crop((0, 0, 80, 60)).tobytes())
            self.assertEqual(image.getpixel((40,65))[:3], (0,0,0))
            self.assertEqual(image.getpixel((40, 159))[:3], (5, 100, 200))

    def test_diagonal_blank_is_filled_without_touching_hero(self):
        source = Image.new('RGB', (100,200), (255,220,235))
        for x in range(100):
            for y in range(40+x//2):
                source.putpixel((x,y),(40,20,30))
        mask = site.build_first_screen_fill_mask(source)
        self.assertEqual(mask.getpixel((10,60)),255)
        self.assertEqual(mask.getpixel((90,60)),0)
        self.assertEqual(mask.getpixel((90,100)),255)
        canvas = source.copy()
        canvas.paste(Image.new('RGB',source.size,(0,100,200)),(0,0),mask)
        self.assertEqual(canvas.getpixel((10,60)),(0,100,200))
        for x in range(100):
            for y in range(40+x//2):
                self.assertEqual(canvas.getpixel((x,y)),source.getpixel((x,y)))

    def test_side_texture_and_footer_are_editable_below_hero(self):
        source = Image.new('RGB',(100,200),(25,25,25))
        source.paste((255,220,235),(8,60,92,180))
        mask = site.build_first_screen_fill_mask(source)
        self.assertEqual(mask.getpixel((0,100)),255)
        self.assertEqual(mask.getpixel((99,100)),255)
        self.assertEqual(mask.getpixel((50,199)),255)
        self.assertEqual(mask.getpixel((50,20)),0)

    def test_size_fit_uses_clean_color_without_cropping_content(self):
        source = Image.new('RGB',(60,100),(20,30,40))
        result = site.fit_selling_points_region(source,(100,100),(255,220,235))
        self.assertEqual(result.getpixel((0,50))[:3],(255,220,235))
        self.assertEqual(result.getpixel((99,50))[:3],(255,220,235))
        self.assertEqual(result.getpixel((50,50))[:3],(20,30,40))

    def test_large_empty_tail_is_detected(self):
        image = Image.new('RGB',(100,200),'pink')
        for y in range(150):
            for x in range(100):
                image.putpixel((x,y),(0,0,0) if x%2 else (255,255,255))
        self.assertGreater(site.selling_points_bottom_blank_fraction(image),.2)

    def test_blank_tail_retries_once_with_layout_correction(self):
        image = io.BytesIO()
        Image.new('RGB',(100,200),'pink').save(image,format='PNG')
        result={'images':[site.image_bytes_to_data_url(image.getvalue(),'image/png')]}
        with patch.object(site,'call_openrouter_images_api',return_value=result) as call, \
                patch.object(site,'selling_points_bottom_blank_fraction',side_effect=[.3,.02]):
            self.assertEqual(site.request_selling_points_layout('model','prompt',[],(100,200),(255,220,235)),result)
        self.assertEqual(call.call_count,2)
        self.assertIn('质量修正',call.call_args.kwargs['prompt'])
