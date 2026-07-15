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

from amazon_a_plus_psd import build_layered_a_plus


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


if __name__ == "__main__":
    unittest.main()
