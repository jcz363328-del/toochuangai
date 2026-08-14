from __future__ import annotations

import base64
import io
import inspect
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
        generated = image_data_url(Image.new("RGB", (300, 100), "blue"))
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

        with (
            patch.object(
                site,
                "call_openrouter",
                return_value={"images": [generated], "text": ""},
            ) as request_image,
            patch.object(
                site,
                "build_outpaint_region_guide",
                side_effect=AssertionError("geometry guide must not be sent to normal outpainting"),
            ),
        ):
            result = site.process_batch_group(job_context, [source], 1)

        self.assertEqual(request_image.call_count, 1)
        for request_call in request_image.call_args_list:
            self.assertEqual(request_call.kwargs["aspect_ratio"], "21:9")
            self.assertEqual(len(request_call.kwargs["uploaded_files"]), 1)
            transition_input = request_call.kwargs["uploaded_files"][0]
            self.assertEqual(transition_input["name"], "outpaint_transition_canvas.png")
            with Image.open(io.BytesIO(transition_input["data"])) as transition_canvas:
                self.assertEqual(transition_canvas.size, (300, 100))
                self.assertEqual(transition_canvas.getpixel((10, 50))[3], 255)
                self.assertEqual(transition_canvas.getpixel((150, 50)), (255, 255, 255, 255))
            self.assertIn("must occupy only about 33.3% of the final frame width", request_call.kwargs["prompt"])
            self.assertIn("same subject frame occupancy", request_call.kwargs["prompt"])
            self.assertIn("There is exactly one input image", request_call.kwargs["prompt"])
            self.assertIn("authoritative outpaint working canvas", request_call.kwargs["prompt"])
            self.assertIn("soft edge-color fields outside it", request_call.kwargs["prompt"])
            self.assertIn("softly blended former-edge corridor", request_call.kwargs["prompt"])
            self.assertIn("Globally harmonize exposure, white balance", request_call.kwargs["prompt"])
            self.assertIn("do not restart a different body or object", request_call.kwargs["prompt"])
            self.assertIn("zero requested expansion must remain exactly on the final image edge", request_call.kwargs["prompt"])
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

    def test_unchanged_crop_is_retried_once(self) -> None:
        source = uploaded_image(Image.new("RGB", (100, 100), "red"))
        unchanged = image_data_url(Image.new("RGB", (100, 100), "red"))
        expanded = image_data_url(Image.new("RGB", (300, 100), "green"))
        feature = site.get_feature_by_key("outpaint")
        assert feature is not None
        job_context = {
            "feature": feature,
            "model": site.NANO_BANANA_MODEL,
            "prompt": "expand",
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
            side_effect=[
                {"images": [unchanged], "text": ""},
                {"images": [expanded], "text": ""},
            ],
        ) as request_image:
            result = site.process_batch_group(job_context, [source], 1)

        self.assertEqual(request_image.call_count, 2)
        self.assertIn(
            "previous attempt failed because it returned the original crop",
            request_image.call_args_list[1].kwargs["prompt"],
        )
        self.assertEqual(result["images"], [expanded])

    def test_default_outpaint_submission_returns_three_independent_results(self) -> None:
        source = uploaded_image(Image.new("RGB", (100, 100), "white"))
        generated = [
            image_data_url(Image.new("RGB", (300, 100), color))
            for color in ("red", "green", "blue")
        ]
        feature = site.get_feature_by_key("outpaint")
        assert feature is not None
        job_context = {
            "feature": feature,
            "model": site.NANO_BANANA_MODEL,
            "prompt": "expand",
            "output_mode": "image",
            "aspect_ratio": site.DEFAULT_ASPECT_RATIO,
            "max_output_images": feature["max_output_images"],
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
            side_effect=[
                {"images": [generated[0]], "text": ""},
                {"images": [generated[1]], "text": ""},
                {"images": [generated[2]], "text": ""},
            ],
        ) as request_image:
            result = site.process_batch_group(job_context, [source], 1)

        self.assertEqual(request_image.call_count, 3)
        for index, request_call in enumerate(request_image.call_args_list, start=1):
            self.assertIn(f"Generate candidate {index} of 3", request_call.kwargs["prompt"])
            self.assertIn("Return exactly one finished image in this call", request_call.kwargs["prompt"])
        self.assertEqual(result["images"], generated)

    def test_rectangular_join_triggers_one_full_frame_repair_pass(self) -> None:
        source = uploaded_image(Image.new("RGB", (100, 100), "red"))
        stitched_image = Image.new("RGB", (300, 100), "blue")
        for x in range(100, 200):
            for y in range(100):
                stitched_image.putpixel((x, y), (255, 0, 0))
        stitched = image_data_url(stitched_image)
        repaired = image_data_url(Image.new("RGB", (300, 100), "green"))
        feature = site.get_feature_by_key("outpaint")
        assert feature is not None
        job_context = {
            "feature": feature,
            "model": site.NANO_BANANA_MODEL,
            "prompt": "expand seamlessly",
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
            side_effect=[
                {"images": [stitched], "text": ""},
                {"images": [repaired], "text": ""},
            ],
        ) as request_image:
            result = site.process_batch_group(job_context, [source], 1)

        self.assertEqual(request_image.call_count, 2)
        repair_call = request_image.call_args_list[1]
        self.assertEqual(
            repair_call.kwargs["uploaded_files"][0]["name"],
            "outpaint_seam_repair_reference.jpg",
        )
        self.assertIn("FULL-FRAME SEAM REPAIR PASS", repair_call.kwargs["prompt"])
        self.assertIn("artifact, not protected content", repair_call.kwargs["prompt"])
        self.assertEqual(result["images"], [repaired])

    def test_unrepaired_rectangular_join_is_retried_then_blocked(self) -> None:
        source = uploaded_image(Image.new("RGB", (100, 100), "red"))
        stitched_image = Image.new("RGB", (300, 100), "blue")
        for x in range(100, 200):
            for y in range(100):
                stitched_image.putpixel((x, y), (255, 0, 0))
        stitched = image_data_url(stitched_image)
        feature = site.get_feature_by_key("outpaint")
        assert feature is not None
        job_context = {
            "feature": feature,
            "model": site.NANO_BANANA_MODEL,
            "prompt": "expand seamlessly",
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
            side_effect=[
                {"images": [stitched], "text": ""},
                {"images": [stitched], "text": ""},
                {"images": [stitched], "text": ""},
            ],
        ) as request_image:
            result = site.process_batch_group(job_context, [source], 1)

        self.assertEqual(request_image.call_count, 3)
        self.assertIn(
            "CLEAN REGENERATION AFTER RECTANGULAR-JOIN REJECTION",
            request_image.call_args_list[2].kwargs["prompt"],
        )
        self.assertEqual(result["images"], [])
        self.assertIn("这些坏图不会进入结果和下载", result["text"])

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

    def test_exact_source_canvas_places_original_at_selected_asymmetric_coordinates(self) -> None:
        source_image = Image.new("RGB", (100, 50), (240, 20, 20))
        source = uploaded_image(source_image)

        canvas_input = site.build_outpaint_source_canvas(
            source,
            top_px=50,
            bottom_px=0,
            left_px=0,
            right_px=100,
        )

        self.assertEqual(canvas_input["name"], "outpaint_transition_canvas.png")
        with Image.open(io.BytesIO(canvas_input["data"])) as canvas:
            self.assertEqual(canvas.size, (200, 100))
            rgba = canvas.convert("RGBA")
            self.assertEqual(rgba.getpixel((50, 25)), (240, 20, 20, 255))
            self.assertEqual(rgba.getpixel((150, 75)), (240, 20, 20, 255))
            self.assertEqual(rgba.getpixel((50, 75)), (240, 20, 20, 255))
            self.assertEqual(rgba.getpixel((50, 50))[3], 255)
            self.assertEqual(rgba.getpixel((99, 75))[3], 255)

    def test_transition_canvas_uses_an_opaque_edge_color_scaffold(self) -> None:
        source = uploaded_image(Image.new("RGB", (200, 200), (240, 20, 20)))

        canvas_input = site.build_outpaint_source_canvas(
            source,
            top_px=100,
            bottom_px=100,
            left_px=100,
            right_px=100,
        )

        with Image.open(io.BytesIO(canvas_input["data"])) as canvas:
            rgba = canvas.convert("RGBA")
            self.assertEqual(rgba.getpixel((100, 200)), (240, 20, 20, 255))
            self.assertEqual(rgba.getpixel((299, 200)), (240, 20, 20, 255))
            self.assertEqual(rgba.getpixel((200, 100)), (240, 20, 20, 255))
            self.assertEqual(rgba.getpixel((200, 299)), (240, 20, 20, 255))
            self.assertEqual(rgba.getpixel((200, 200))[3], 255)

    def test_boundary_detector_finds_the_old_source_rectangle(self) -> None:
        source = uploaded_image(Image.new("RGB", (100, 100), "red"))
        stitched_image = Image.new("RGB", (300, 100), "blue")
        for x in range(100, 200):
            for y in range(100):
                stitched_image.putpixel((x, y), (255, 0, 0))

        measurements = site.measure_outpaint_boundary_seams(
            image_data_url(stitched_image),
            source,
            top_px=0,
            bottom_px=0,
            left_px=100,
            right_px=100,
        )

        self.assertEqual([item["side"] for item in measurements], ["left", "right"])
        self.assertTrue(all(item["detected"] for item in measurements))
        self.assertTrue(all(float(item["ratio"]) > 2.2 for item in measurements))
        self.assertTrue(site.has_outpaint_rectangular_join(measurements))

    def test_multiscale_detector_finds_a_soft_but_complete_inset_rectangle(self) -> None:
        source = uploaded_image(Image.new("RGB", (100, 100), (180, 180, 180)))
        stitched_image = Image.new("RGB", (300, 300), (100, 100, 100))
        for x in range(112, 188):
            for y in range(112, 188):
                stitched_image.putpixel((x, y), (180, 180, 180))

        measurements = site.measure_outpaint_boundary_seams(
            image_data_url(stitched_image),
            source,
            top_px=100,
            bottom_px=100,
            left_px=100,
            right_px=100,
        )

        self.assertGreaterEqual(
            sum(bool(item["detected"]) for item in measurements),
            2,
        )
        self.assertTrue(site.has_outpaint_rectangular_join(measurements))

    def test_result_crop_preserves_unexpanded_edge_for_asymmetric_selection(self) -> None:
        source = uploaded_image(Image.new("RGB", (100, 100), "white"))
        generated = Image.new("RGB", (400, 100), "blue")
        for x in range(200):
            for y in range(100):
                generated.putpixel((x, y), (240, 20, 20))

        right_only = site.crop_outpaint_result_to_selected_region(
            image_data_url(generated),
            source,
            top_px=0,
            bottom_px=0,
            left_px=0,
            right_px=100,
        )
        left_only = site.crop_outpaint_result_to_selected_region(
            image_data_url(generated),
            source,
            top_px=0,
            bottom_px=0,
            left_px=100,
            right_px=0,
        )

        right_bytes, _mime = site.load_image_bytes_from_url(right_only)
        left_bytes, _mime = site.load_image_bytes_from_url(left_only)
        with Image.open(io.BytesIO(right_bytes)) as right_result:
            self.assertEqual(right_result.size, (200, 100))
            self.assertEqual(right_result.getpixel((10, 50)), (240, 20, 20))
        with Image.open(io.BytesIO(left_bytes)) as left_result:
            self.assertEqual(left_result.size, (200, 100))
            self.assertEqual(left_result.getpixel((190, 50)), (0, 0, 255))

    def test_same_ratio_model_result_is_resized_to_exact_selected_pixels(self) -> None:
        source = uploaded_image(Image.new("RGB", (100, 100), "white"))
        generated = image_data_url(Image.new("RGB", (1000, 500), "blue"))

        exact_result = site.crop_outpaint_result_to_selected_region(
            generated,
            source,
            top_px=0,
            bottom_px=0,
            left_px=50,
            right_px=50,
        )

        exact_bytes, _mime = site.load_image_bytes_from_url(exact_result)
        with Image.open(io.BytesIO(exact_bytes)) as image:
            self.assertEqual(image.size, (200, 100))

    def test_drag_selection_is_not_rounded_to_fifty_pixels(self) -> None:
        consume_source = inspect.getsource(site.consume_pending_outpaint_drag)
        preview_source = inspect.getsource(site.render_outpaint_extension_preview_card)

        self.assertEqual(site.OUTPAINT_DRAG_STEP_PX, 1)
        self.assertIn("value / drag_step", consume_source)
        self.assertNotIn("value / 50", consume_source)
        self.assertIn('"step": OUTPAINT_DRAG_STEP_PX', preview_source)

    def test_outpaint_ui_exposes_exact_directional_pixel_inputs(self) -> None:
        render_source = inspect.getsource(site.render_openrouter_feature)

        self.assertIn("最终输出尺寸（可直接输入）", render_source)
        self.assertIn('"最终宽度（px）"', render_source)
        self.assertIn('"最终高度（px）"', render_source)
        self.assertIn('"应用目标尺寸"', render_source)
        self.assertIn("requested_target_width - selected_source_width", render_source)
        self.assertIn("requested_target_height - selected_source_height", render_source)
        self.assertIn("精确扩展像素（可直接输入）", render_source)
        self.assertIn('"上扩展（px）"', render_source)
        self.assertIn('"下扩展（px）"', render_source)
        self.assertIn('"左扩展（px）"', render_source)
        self.assertIn('"右扩展（px）"', render_source)
        self.assertIn("最终文件严格输出", render_source)
        self.assertIn('"target_width": locked_target_width', render_source)
        self.assertIn('"target_height": locked_target_height', render_source)

    def test_locked_target_size_mismatch_is_rejected_before_generation(self) -> None:
        source = uploaded_image(Image.new("RGB", (100, 100), "white"))
        feature = site.get_feature_by_key("outpaint")
        assert feature is not None
        job_context = {
            "feature": feature,
            "model": site.NANO_BANANA_MODEL,
            "prompt": "expand",
            "output_mode": "image",
            "aspect_ratio": site.DEFAULT_ASPECT_RATIO,
            "max_output_images": 1,
            "outpaint_settings": {
                "source_width": 100,
                "source_height": 100,
                "target_width": 999,
                "target_height": 100,
                "top": 0,
                "bottom": 0,
                "left": 50,
                "right": 50,
            },
        }

        with self.assertRaisesRegex(RuntimeError, "扩图提交尺寸校验失败"):
            site.process_batch_group(job_context, [source], 1)

    def test_source_can_be_dragged_inside_a_fixed_target_canvas(self) -> None:
        source = uploaded_image(Image.new("RGB", (120, 80), "white"))

        with patch.object(site.components, "html") as render_html:
            site.render_outpaint_extension_preview_card(
                source,
                top_px=20,
                bottom_px=20,
                left_px=30,
                right_px=30,
                component_key="outpaint_position_test",
                drag_state_keys={
                    "top": "outpaint_top_outpaint",
                    "bottom": "outpaint_bottom_outpaint",
                    "left": "outpaint_left_outpaint",
                    "right": "outpaint_right_outpaint",
                    "mode": "outpaint_drag_mode_outpaint",
                },
            )

        rendered_html = render_html.call_args.args[0]
        self.assertIn('data-mode="position"', rendered_html)
        self.assertIn('class="outpaint-source-handle"', rendered_html)
        self.assertIn("horizontalTotal", rendered_html)
        self.assertIn("verticalTotal", rendered_html)
        self.assertIn("horizontalTotal - nextLeft", rendered_html)
        self.assertIn("verticalTotal - nextTop", rendered_html)
        self.assertIn("targetWidth = sourceWidth", rendered_html)
        self.assertIn("mode: mode_outpaint_position_test", rendered_html)

    def test_outpaint_drag_defaults_to_resizing_the_canvas(self) -> None:
        source = uploaded_image(Image.new("RGB", (120, 80), "white"))

        with patch.object(site.components, "html") as render_html:
            site.render_outpaint_extension_preview_card(
                source,
                top_px=20,
                bottom_px=20,
                left_px=30,
                right_px=30,
                component_key="outpaint_resize_default_test",
                drag_state_keys={
                    "top": "outpaint_top_resize_default",
                    "bottom": "outpaint_bottom_resize_default",
                    "left": "outpaint_left_resize_default",
                    "right": "outpaint_right_resize_default",
                    "mode": "outpaint_drag_mode_resize_default",
                },
            )

        rendered_html = render_html.call_args.args[0]
        self.assertIn('"mode": "resize"', rendered_html)
        self.assertIn(
            'data-mode="resize">调整扩图范围（改变比例）',
            rendered_html,
        )
        self.assertIn(
            'data-mode="position">移动原图位置（不改变比例）',
            rendered_html,
        )
        self.assertIn("实时改变目标尺寸和比例", rendered_html)
        self.assertIn('data-value="ratio"', rendered_html)
        self.assertIn("targetWidth / Math.max(targetHeight, 1)", rendered_html)

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
        self.assertEqual(feature["max_output_images"], 3)

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
        self.assertIn("target canvas of 300x100px", instruction)
        self.assertIn("coordinate x=100px, y=0px", instruction)
        self.assertIn("[100, 0] to [200, 100]", instruction)

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
        self.assertIn("four numeric directional expansion amounts", prompt)
        self.assertIn("do not paste the original back", prompt)
        self.assertIn("禁止把原图作为矩形图层覆盖或拼接回结果", prompt)
        self.assertIn("transition corridor", prompt)
        self.assertIn("no straight horizontal or vertical join", prompt)
        self.assertIn("working canvas is a geometry constraint", prompt)
        self.assertIn(
            "replace every blurred or stretched edge-color scaffold pixel",
            prompt,
        )
        self.assertIn("Reconstruct both sides of every former boundary together", prompt)
        self.assertIn("globally harmonize exposure, white balance", prompt)
        self.assertNotIn("transparent blank margins", prompt)
        self.assertNotIn("最终输出必须保持原始比例不变", prompt)


if __name__ == "__main__":
    unittest.main()
