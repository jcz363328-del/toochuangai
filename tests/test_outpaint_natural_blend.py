from __future__ import annotations

import base64
import io
import unittest
from unittest.mock import patch

from PIL import Image

from 图片 import openrouter_image_site as site


def image_data_url(image: Image.Image) -> str:
    output = io.BytesIO()
    image.save(output, format="PNG")
    return f"data:image/png;base64,{base64.b64encode(output.getvalue()).decode('ascii')}"


def uploaded_image(image: Image.Image, name: str = "source.png") -> dict[str, object]:
    output = io.BytesIO()
    image.save(output, format="PNG")
    return {"data": output.getvalue(), "name": name, "type": "image/png"}


class NaturalOutpaintTests(unittest.TestCase):
    def test_expanded_canvas_drives_model_aspect_ratio(self) -> None:
        source = uploaded_image(Image.new("RGB", (100, 100), "white"))
        generated = image_data_url(Image.new("RGB", (300, 100), "white"))
        feature = site.get_feature_by_key("outpaint")
        assert feature is not None
        job_context = {
            "feature": feature,
            "model": site.NANO_BANANA_MODEL,
            "prompt": "自然扩展背景",
            "output_mode": "image",
            "aspect_ratio": site.DEFAULT_ASPECT_RATIO,
            "max_output_images": 1,
            "outpaint_settings": {
                "top": 0,
                "bottom": 0,
                "left": 100,
                "right": 100,
            },
        }

        with patch.object(
            site,
            "call_openrouter",
            return_value={"images": [generated], "text": ""},
        ) as request_image:
            result = site.process_batch_group(job_context, [source], 1)

        self.assertEqual(request_image.call_count, 1)
        for request_call in request_image.call_args_list:
            self.assertEqual(request_call.kwargs["aspect_ratio"], "21:9")
            self.assertEqual(len(request_call.kwargs["uploaded_files"]), 2)
            self.assertEqual(request_call.kwargs["uploaded_files"][0]["data"], source["data"])
            self.assertEqual(
                request_call.kwargs["uploaded_files"][1]["name"],
                "outpaint_region_layout_mask.png",
            )
            self.assertIn("must occupy only about 33.3% of the final frame width", request_call.kwargs["prompt"])
            self.assertIn("same subject frame occupancy", request_call.kwargs["prompt"])
            self.assertIn("strict black-and-white layout mask", request_call.kwargs["prompt"])
        self.assertEqual(result["images"], [generated])
        self.assertEqual(
            result["outpaint_alignment"],
            {
                "source_width": 100,
                "source_height": 100,
                "target_width": 300,
                "target_height": 100,
                "top": 0,
                "bottom": 0,
                "left": 100,
                "right": 100,
            },
        )

    def test_target_canvas_size_is_calculated_without_padding_source(self) -> None:
        source = uploaded_image(Image.new("RGB", (120, 80), "white"))

        self.assertEqual(
            site.get_outpaint_target_canvas_size(source, 20, 30, 40, 50),
            (210, 130),
        )

    def test_region_guide_encodes_the_exact_selected_expansion_area(self) -> None:
        source = uploaded_image(Image.new("RGB", (100, 50), "white"))

        guide_input = site.build_outpaint_region_guide(
            source,
            top_px=50,
            bottom_px=0,
            left_px=0,
            right_px=100,
        )

        self.assertEqual(guide_input["name"], "outpaint_region_layout_mask.png")
        with Image.open(io.BytesIO(guide_input["data"])) as guide:
            self.assertEqual(guide.size, (200, 100))
            self.assertEqual(guide.getpixel((50, 25)), (0, 0, 0))
            self.assertEqual(guide.getpixel((150, 75)), (0, 0, 0))
            self.assertEqual(guide.getpixel((50, 75)), (255, 255, 255))

    def test_maximum_expansion_is_three_times_original_dimensions(self) -> None:
        source = uploaded_image(Image.new("RGB", (120, 80), "white"))
        feature = site.get_feature_by_key("outpaint")
        assert feature is not None

        self.assertEqual(
            site.get_outpaint_extension_limits(source),
            {"top": 80, "bottom": 80, "left": 120, "right": 120},
        )
        self.assertEqual(
            site.get_outpaint_target_canvas_size(source, 999, 999, 999, 999),
            (360, 240),
        )
        self.assertEqual(feature["max_output_images"], 1)

    def test_default_expansion_is_half_of_each_side_limit(self) -> None:
        self.assertEqual(site.get_outpaint_default_extension(2000), 1000)
        self.assertEqual(site.get_outpaint_default_extension(100), 50)

    def test_framing_instruction_requires_visible_new_scene_area(self) -> None:
        source = uploaded_image(Image.new("RGB", (100, 100), "white"))

        instruction = site.build_outpaint_source_framing_instruction(source, 0, 0, 100, 100)

        self.assertIn("33.3% of the final frame width", instruction)
        self.assertIn("100.0% of the final frame height", instruction)
        self.assertIn("66.7% of the final frame area", instruction)
        self.assertIn("same crop", instruction)

    def test_compare_gallery_places_source_inside_expanded_result_coordinates(self) -> None:
        alignment = {
            "source_width": 100,
            "source_height": 100,
            "target_width": 300,
            "target_height": 100,
            "top": 0,
            "bottom": 0,
            "left": 100,
            "right": 100,
        }

        with patch.object(
            site,
            "build_gallery_item",
            side_effect=lambda source, **_kwargs: {"src": source},
        ), patch.object(site.components, "html") as render_html:
            site.render_before_after_compare_gallery(
                ["source-image"],
                ["result-image"],
                ["扩图结果"],
                "outpaint",
                outpaint_alignments=[alignment],
            )

        rendered_html = render_html.call_args.args[0]
        self.assertIn('"target_width": 300', rendered_html)
        self.assertIn('"view": "result-image"', rendered_html)
        self.assertIn('"download": "result-image"', rendered_html)
        self.assertIn("Number(alignment.left || 0) / targetWidth", rendered_html)
        self.assertIn("sourceWidth / targetWidth", rendered_html)
        self.assertIn("height: 620px", rendered_html)
        self.assertIn("左键查看大图 · 右键使用 Chrome 原生菜单", rendered_html)
        self.assertIn('<img class="compare-native-result"', rendered_html)
        self.assertIn("normalizeNativeResultSrc_compare_outpaint_1", rendered_html)
        self.assertIn(
            "nativeResultImage.src = normalizeNativeResultSrc_compare_outpaint_1(pair.view || pair.result)",
            rendered_html,
        )
        self.assertIn('parsed.pathname.startsWith("/history_images/")', rendered_html)
        self.assertIn('parsed.pathname.startsWith("/jimeng_uploads/")', rendered_html)
        self.assertIn("hostWindow_compare_outpaint_1.location.hostname", rendered_html)
        self.assertIn("nativeResultImage.style.clipPath", rendered_html)
        self.assertIn("nativeResultImage.style.left", rendered_html)
        self.assertIn("pointer-events: none", rendered_html)
        self.assertIn("opacity: 1", rendered_html)
        self.assertIn("openCompareFullscreen_compare_outpaint_1", rendered_html)
        self.assertIn('overlay.id = "lashforge-fullscreen-viewer"', rendered_html)
        self.assertIn('control.addEventListener("click"', rendered_html)
        self.assertIn("pointerDownOnEffect && !dragMoved", rendered_html)
        self.assertIn("Math.hypot", rendered_html)
        self.assertNotIn('control.addEventListener("contextmenu"', rendered_html)
        self.assertNotIn("compare-context-menu", rendered_html)
        self.assertNotIn("http://localhost:41595/api/item/addFromURL", rendered_html)
        self.assertNotIn('<img src="${pair.result}"', rendered_html)

    def test_direct_download_url_requests_attachment_response(self) -> None:
        with patch.object(
            site,
            "build_history_download_public_url",
            return_value="http://example.com/image.png?token=abc",
        ):
            download_url = site.build_direct_image_download_url("source-image")

        self.assertEqual(download_url, "http://example.com/image.png?token=abc&download=1")

    def test_prompt_requires_one_pass_generation_without_stitching(self) -> None:
        feature = site.get_feature_by_key("outpaint")
        assert feature is not None
        notes = site.build_outpaint_extra_notes(100, 100, 100, 100)
        prompt = site.build_prompt(feature, "", "4:5", notes)

        self.assertIn("one-pass", prompt)
        self.assertIn("do not paste the original back", prompt)
        self.assertIn("禁止把原图作为矩形图层覆盖或拼接回结果", prompt)
        self.assertNotIn("transparent blank margins", prompt)
        self.assertNotIn("最终输出必须保持原始比例不变", prompt)


if __name__ == "__main__":
    unittest.main()
