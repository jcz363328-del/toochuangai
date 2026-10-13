from __future__ import annotations

import base64
import io
import inspect
import unittest

from PIL import Image

from 图片 import openrouter_image_site as site


class ImageResizeFeatureTests(unittest.TestCase):
    def test_feature_is_registered_as_local_processing(self) -> None:
        feature = site.get_feature_by_key("image_resize")

        self.assertIsNotNone(feature)
        self.assertEqual(feature["name"], "图片尺寸放大")
        self.assertEqual(feature["mode"], "local_resize")

    def test_local_resize_outputs_exact_dimensions(self) -> None:
        source = Image.new("RGB", (40, 20), (210, 80, 120))
        source_buffer = io.BytesIO()
        source.save(source_buffer, format="PNG")

        result_url = site.resize_uploaded_image_locally(
            {"data": source_buffer.getvalue(), "name": "source.png", "type": "image/png"},
            320,
            180,
        )

        payload = base64.b64decode(result_url.split(",", 1)[1])
        with Image.open(io.BytesIO(payload)) as resized:
            self.assertEqual(resized.size, (320, 180))

    def test_page_exposes_fixed_size_controls(self) -> None:
        source = inspect.getsource(site.render_openrouter_feature)

        self.assertIn('"锁定原比例"', source)
        self.assertIn('"目标宽度"', source)
        self.assertIn('"目标高度"', source)
        self.assertIn('"开始放大"', source)


if __name__ == "__main__":
    unittest.main()
