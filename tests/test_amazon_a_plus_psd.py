from __future__ import annotations

import io
import struct
import sys
import unittest
from pathlib import Path

from PIL import Image, ImageDraw


MODULE_DIR = Path(__file__).resolve().parents[1] / "图片"
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

from amazon_a_plus_psd import (
    build_layered_a_plus,
    clean_green_edge_spill,
    fit_green_screen_to_canvas,
    remove_green_screen,
    select_closest_aspect_ratio,
)


def read_psd_layer_count(psd_bytes: bytes) -> int:
    offset = 26
    color_mode_length = struct.unpack(">I", psd_bytes[offset : offset + 4])[0]
    offset += 4 + color_mode_length
    image_resources_length = struct.unpack(">I", psd_bytes[offset : offset + 4])[0]
    offset += 4 + image_resources_length
    layer_and_mask_length = struct.unpack(">I", psd_bytes[offset : offset + 4])[0]
    if layer_and_mask_length <= 0:
        return 0
    offset += 4
    layer_info_length = struct.unpack(">I", psd_bytes[offset : offset + 4])[0]
    if layer_info_length <= 0:
        return 0
    offset += 4
    return abs(struct.unpack(">h", psd_bytes[offset : offset + 2])[0])


class AmazonAPlusPsdTests(unittest.TestCase):
    def build_green_screen_fixture(self) -> Image.Image:
        image = Image.new("RGB", (240, 160), (0, 255, 0))
        draw = ImageDraw.Draw(image)
        draw.rectangle((12, 14, 58, 58), fill=(210, 35, 45))
        draw.rectangle((28, 28, 40, 40), fill=(0, 255, 0))
        draw.rectangle((108, 22, 116, 52), fill=(30, 70, 220))
        draw.rectangle((123, 22, 131, 52), fill=(30, 70, 220))
        draw.ellipse((62, 104, 106, 144), fill=(245, 190, 20))
        return image

    def test_builds_separate_layers_and_readable_psd(self) -> None:
        result = build_layered_a_plus(self.build_green_screen_fixture())

        self.assertEqual(result["layer_count"], 3)
        self.assertEqual(len(result["layer_manifest"]), 3)
        self.assertEqual(read_psd_layer_count(result["psd_bytes"]), 3)

        composite = result["composite"]
        self.assertEqual(composite.size, (240, 160))
        self.assertEqual(composite.getpixel((0, 0))[3], 0)
        self.assertGreater(composite.getpixel((20, 20))[3], 0)
        self.assertGreater(composite.getpixel((32, 32))[3], 0)

        with Image.open(io.BytesIO(result["psd_bytes"])) as psd_image:
            self.assertEqual(psd_image.format, "PSD")
            self.assertEqual(psd_image.size, (240, 160))
            psd_image.load()

    def test_selects_closest_native_4k_aspect_ratio(self) -> None:
        self.assertEqual(select_closest_aspect_ratio((1464, 600)), "21:9")
        self.assertEqual(select_closest_aspect_ratio((600, 600)), "1:1")

    def test_fits_without_stretching_and_pads_with_green(self) -> None:
        source = Image.new("RGB", (200, 100), (220, 35, 45))

        result = fit_green_screen_to_canvas(source, (100, 100))

        self.assertEqual(result.size, (100, 100))
        self.assertEqual(result.getpixel((50, 5)), (0, 255, 0))
        self.assertNotEqual(result.getpixel((50, 50)), (0, 255, 0))

    def test_removes_opaque_green_spill_from_antialiased_edges(self) -> None:
        large = Image.new("RGB", (400, 400), (0, 255, 0))
        draw = ImageDraw.Draw(large)
        draw.ellipse((72, 72, 328, 328), fill=(238, 218, 198))
        flattened = large.resize((100, 100), Image.Resampling.LANCZOS)

        result = remove_green_screen(flattened)
        pixels = result.load()
        contaminated_edge_pixels = 0
        partial_alpha_pixels = 0
        for y in range(result.height):
            for x in range(result.width):
                red, green, blue, alpha = pixels[x, y]
                if 0 < alpha < 255:
                    partial_alpha_pixels += 1
                if alpha > 8 and green - max(red, blue) > 8:
                    contaminated_edge_pixels += 1

        self.assertGreater(partial_alpha_pixels, 0)
        self.assertEqual(contaminated_edge_pixels, 0)

    def test_partial_alpha_edge_does_not_turn_magenta(self) -> None:
        image = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rectangle((2, 2, 5, 5), fill=(238, 218, 198, 255))
        image.putpixel((1, 3), (120, 230, 115, 80))

        cleaned = clean_green_edge_spill(image)
        red, green, blue, alpha = cleaned.getpixel((1, 3))

        self.assertGreater(alpha, 0)
        self.assertFalse(red - green > 45 and blue - green > 45)
        self.assertLessEqual(green - max(red, blue), 8)


if __name__ == "__main__":
    unittest.main()
