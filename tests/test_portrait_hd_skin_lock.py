from __future__ import annotations

import io
import inspect
import unittest
from unittest.mock import Mock, patch

from PIL import Image

from 图片 import openrouter_image_site as site


class PortraitHdSkinLockTests(unittest.TestCase):
    @staticmethod
    def make_image_input(size: tuple[int, int], name: str = "source.png") -> dict[str, object]:
        image = Image.new("RGB", size, (80, 120, 160))
        output = io.BytesIO()
        image.save(output, format="PNG")
        return {"data": output.getvalue(), "name": name, "type": "image/png"}

    @staticmethod
    def read_result_size(image_url: str) -> tuple[int, int]:
        image_bytes, _mime_type = site.load_image_bytes_from_url(image_url)
        with Image.open(io.BytesIO(image_bytes)) as image:
            return image.size

    def test_hd_prompt_locks_source_skin_color_and_texture(self) -> None:
        feature = site.get_feature_by_key("hd_batch")
        self.assertIsNotNone(feature)
        assert feature is not None
        prompt = str(feature["default_prompt"])

        for rule in (
            "肤色与肤质锁定是本次高清处理的最高优先级",
            "禁止提亮、压暗、增白、变黄、变红或统一肤色",
            "毛孔、皮肤颗粒、油脂光泽",
            "禁止磨皮、美颜、祛斑、去痣",
            "原有肤色、肤质、毛孔、斑点、痣、痘印和细纹必须全部保留",
            "整张画面的色温与色调锁定也是本次高清处理的最高优先级",
            "整体与局部色温、冷暖关系、综合色调、色相、白平衡",
            "禁止自动白平衡、自动校色、调色、重新定色",
        ):
            self.assertIn(rule, prompt)
        self.assertNotIn("去掉脸上的斑点", prompt)

    def test_hd_prompt_overrides_requests_to_change_temperature_or_tone(self) -> None:
        prompt = site.build_portrait_hd_prompt("把画面调暖一点，增加电影色调和饱和度")

        self.assertIn("色温与色调锁定也是本次高清处理的最高优先级", prompt)
        self.assertIn("色温、色调、白平衡和全部颜色关系必须逐项保持第1张原图状态", prompt)
        self.assertIn("禁止任何自动校色或风格化调色", prompt)
        self.assertIn("严禁迁移其色温、色调、白平衡、曝光、对比度", prompt)
        self.assertGreater(
            prompt.index("最高优先级硬性规则"),
            prompt.index("把画面调暖一点"),
        )

    def test_reference_image_remains_enabled_but_cannot_transfer_skin(self) -> None:
        first = object()
        second = object()
        prompt = site.build_portrait_hd_prompt("请把皮肤变白并磨皮")

        self.assertEqual(site.get_portrait_hd_inputs([first, second]), [first, second])
        self.assertIn("第二张图片仍作为高清参考图", prompt)
        self.assertIn("只允许参考其清晰度、分辨率和细节解析水平", prompt)
        self.assertIn("严禁从第二张图片借用或迁移肤色、肤质", prompt)
        self.assertGreater(
            prompt.index("最高优先级硬性规则"),
            prompt.index("请把皮肤变白并磨皮"),
        )

    def test_hd_page_keeps_reference_uploader_without_verbose_model_caption(self) -> None:
        render_source = inspect.getsource(site.render_openrouter_feature)

        self.assertIn('supports_skin_reference = feature["key"] == "hd_batch"', render_source)
        self.assertIn("肤质参考图（可选，1 张）", render_source)
        self.assertIn("PORTRAIT_HD_SKIN_LOCK_RULES", render_source)
        self.assertIn("PORTRAIT_HD_COLOR_LOCK_RULES", render_source)
        self.assertIn("参考图仅用于清晰度", render_source)
        self.assertNotIn("当前使用 Nano Banana 2 做高清增强", render_source)
        self.assertNotIn("当前使用火山引擎即梦智能超清专用接口", render_source)

    def test_jimeng_upscale_page_is_separate_from_portrait_hd(self) -> None:
        render_source = inspect.getsource(site.render_openrouter_feature)

        self.assertIn("JIMENG_HD_MODEL_NAME", render_source)
        self.assertIn("开始 8K 超清", render_source)
        self.assertIn("即梦智能超清专用接口", render_source)
        self.assertIn("全局串行队列", render_source)
        self.assertIn("JIMENG_HD_QUEUE_CAPACITY", render_source)

    def test_portrait_hd_and_jimeng_upscale_are_two_features(self) -> None:
        portrait_feature = site.get_feature_by_key("hd_batch")
        jimeng_feature = site.get_feature_by_key(site.JIMENG_HD_FEATURE_KEY)
        assert portrait_feature is not None
        assert jimeng_feature is not None

        self.assertEqual(portrait_feature["name"], "模特图批量高清")
        self.assertEqual(portrait_feature["mode"], "openrouter")
        self.assertEqual(jimeng_feature["name"], "即梦超清")
        self.assertEqual(jimeng_feature["mode"], "jimeng_upscale")
        self.assertEqual(jimeng_feature["model"], site.JIMENG_HD_MODEL_NAME)
        self.assertIn("8K", jimeng_feature["summary"])

    def test_jimeng_upscale_submits_official_8k_scale_fifty_request_and_polls_result(self) -> None:
        source = self.make_image_input((640, 960))

        with (
            patch.object(site, "get_jimeng_public_upload_base_url", return_value=""),
            patch.object(site, "prepare_jimeng_hd_input_base64", return_value="encoded-image"),
            patch.object(site, "_JIMENG_TASK_LOCK") as task_lock,
            patch.object(
                site,
                "jimeng_signed_post",
                return_value={"code": 10000, "data": {"task_id": "task-8k"}},
            ) as submit,
            patch.object(site, "poll_jimeng_task_result", return_value={"images": ["https://example.com/8k.png"]}) as poll,
        ):
            result = site.call_jimeng_hd_upscale([source])

        task_lock.__enter__.assert_called_once()
        task_lock.__exit__.assert_called_once()
        submit.assert_called_once()
        action, body = submit.call_args.args[:2]
        self.assertEqual(action, site.JIMENG_SUBMIT_ACTION)
        self.assertEqual(
            body,
            {
                "req_key": "jimeng_i2i_seed3_tilesr_cvtob",
                "binary_data_base64": ["encoded-image"],
                "resolution": "8k",
                "scale": 50,
            },
        )
        poll.assert_called_once_with("jimeng_i2i_seed3_tilesr_cvtob", "task-8k", timeout=120)
        self.assertEqual(result["channel"], "即梦智能超清 · 原生 8K")
        self.assertEqual(result["resolution"], "8k")

    def test_jimeng_upscale_prefers_official_image_urls_request(self) -> None:
        source = self.make_image_input((640, 960))

        with (
            patch.object(site, "get_jimeng_public_upload_base_url", return_value="https://img.example.com"),
            patch.object(
                site,
                "save_uploaded_inputs_for_jimeng",
                return_value=["https://img.example.com/source.png"],
            ),
            patch.object(
                site,
                "prepare_jimeng_hd_input_base64",
            ) as prepare_base64,
            patch.object(
                site,
                "jimeng_signed_post",
                return_value={"code": 10000, "data": {"task_id": "task-url"}},
            ) as submit,
            patch.object(site, "poll_jimeng_task_result", return_value={"images": ["https://example.com/8k.png"]}),
        ):
            site.call_jimeng_hd_upscale([source])

        body = submit.call_args.args[1]
        self.assertEqual(
            body,
            {
                "req_key": "jimeng_i2i_seed3_tilesr_cvtob",
                "resolution": "8k",
                "scale": 50,
                "image_urls": ["https://img.example.com/source.png"],
            },
        )
        prepare_base64.assert_not_called()

    def test_jimeng_50400_has_actionable_authentication_message(self) -> None:
        message = site.format_user_facing_error_message(
            "Agent 请求失败（HTTP 401，错误码 50400，RequestId request-1）：Access Denied: Access Denied"
        )

        self.assertIn("火山引擎鉴权失败（HTTP 401，错误码 50400）", message)
        self.assertIn("即梦AI-智能超清", message)
        self.assertIn("方舟模型 API Key 不能替代", message)

    def test_jimeng_http_error_preserves_status_code_and_request_id(self) -> None:
        response = Mock()
        response.status_code = 401
        response.json.return_value = {
            "code": 50400,
            "message": "Access Denied: Access Denied",
            "request_id": "request-50400",
        }
        response.headers = {}
        response.text = ""
        with (
            patch.object(site, "build_jimeng_auth_headers", return_value={}),
            patch.object(site.requests, "post", return_value=response),
            self.assertRaisesRegex(
                RuntimeError,
                r"HTTP 401，错误码 50400，RequestId request-50400",
            ),
        ):
            site.jimeng_signed_post(
                site.JIMENG_SUBMIT_ACTION,
                {"req_key": site.JIMENG_HD_UPSCALE_REQ_KEY},
            )

    def test_jimeng_50430_retries_with_backoff(self) -> None:
        limited_response = Mock()
        limited_response.status_code = 429
        limited_response.json.return_value = {
            "code": 50430,
            "message": "Request Has Reached API Concurrent Limit, Please Try Later",
            "request_id": "request-limited",
        }
        limited_response.headers = {}
        limited_response.text = ""
        success_response = Mock()
        success_response.status_code = 200
        success_response.json.return_value = {
            "code": 10000,
            "data": {"task_id": "task-after-wait"},
        }
        success_response.headers = {}
        success_response.text = ""

        with (
            patch.object(site, "build_jimeng_auth_headers", return_value={}),
            patch.object(
                site.requests,
                "post",
                side_effect=[limited_response, success_response],
            ) as post,
            patch.object(site.time, "sleep") as sleep,
        ):
            result = site.jimeng_signed_post(
                site.JIMENG_SUBMIT_ACTION,
                {"req_key": site.JIMENG_HD_UPSCALE_REQ_KEY},
            )

        self.assertEqual(result["data"]["task_id"], "task-after-wait")
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once_with(site.JIMENG_CONCURRENT_LIMIT_RETRY_DELAYS[0])

    def test_jimeng_50430_has_queue_guidance(self) -> None:
        message = site.format_user_facing_error_message(
            "Agent 请求失败（HTTP 429，错误码 50430）："
            "Request Has Reached API Concurrent Limit, Please Try Later"
        )

        self.assertIn("账号级并发 1", message)
        self.assertIn("串行排队", message)
        self.assertIn("请不要重复点击提交", message)

    def test_jimeng_upscale_feature_calls_upscale_directly_without_generation_model(self) -> None:
        source = self.make_image_input((320, 480))
        with (
            patch.object(site, "call_jimeng_hd_upscale", return_value={"images": ["https://example.com/8k.png"], "text": ""}) as upscale,
            patch.object(site, "call_openrouter") as openrouter,
            patch.object(site, "call_openrouter_portrait_hd") as portrait_hd,
        ):
            result = site.process_batch_group(
                {
                    "feature": {"key": site.JIMENG_HD_FEATURE_KEY, "mode": "jimeng_upscale"},
                    "model": site.JIMENG_HD_MODEL_NAME,
                    "prompt": "unused",
                    "output_mode": "image",
                    "aspect_ratio": "自动",
                    "max_output_images": 1,
                },
                [source],
                1,
            )

        upscale.assert_called_once_with(uploaded_files=[source])
        openrouter.assert_not_called()
        portrait_hd.assert_not_called()
        self.assertEqual(result["images"], ["https://example.com/8k.png"])

    def test_portrait_hd_feature_still_uses_original_generation_pipeline(self) -> None:
        source = self.make_image_input((320, 480))
        with (
            patch.object(site, "call_jimeng_hd_upscale") as upscale,
            patch.object(
                site,
                "call_openrouter_portrait_hd",
                return_value={"images": ["https://example.com/portrait-hd.png"], "text": ""},
            ) as portrait_hd,
        ):
            result = site.process_batch_group(
                {
                    "feature": {"key": "hd_batch", "mode": "openrouter"},
                    "model": site.NANO_BANANA_MODEL,
                    "prompt": "只做高清",
                    "output_mode": "image",
                    "aspect_ratio": "自动",
                    "max_output_images": 1,
                },
                [source],
                1,
            )

        upscale.assert_not_called()
        portrait_hd.assert_called_once()
        self.assertEqual(result["images"], ["https://example.com/portrait-hd.png"])

    def test_hd_prompt_locks_canvas_to_source_dimensions_without_cropping(self) -> None:
        source = self.make_image_input((137, 91))

        instruction = site.build_portrait_hd_size_instruction(source)
        prompt = site.build_portrait_hd_prompt("只做高清")

        self.assertIn("137×91px", instruction)
        self.assertIn("禁止裁剪、扩图、补边", instruction)
        self.assertIn("像素宽度和像素高度必须分别与第1张原图完全一致", prompt)
        self.assertIn("完整保留原图上下左右四边", prompt)

    def test_hd_result_is_restored_to_source_size_without_letterbox_borders(self) -> None:
        source = self.make_image_input((10, 10))
        generated = Image.new("RGB", (30, 10), (20, 180, 20))
        for y in range(generated.height):
            for x in range(0, 8):
                generated.putpixel((x, y), (240, 10, 10))
            for x in range(22, 30):
                generated.putpixel((x, y), (10, 10, 240))
        generated_output = io.BytesIO()
        generated.save(generated_output, format="PNG")
        generated_url = site.image_bytes_to_data_url(generated_output.getvalue(), "image/png")

        restored_url = site.restore_portrait_hd_source_size(generated_url, source)
        restored_bytes, _mime_type = site.load_image_bytes_from_url(restored_url)
        with Image.open(io.BytesIO(restored_bytes)) as restored:
            self.assertEqual(restored.size, (10, 10))
            self.assertGreater(restored.getpixel((0, 5))[1], restored.getpixel((0, 5))[0])
            self.assertGreater(restored.getpixel((9, 5))[1], restored.getpixel((9, 5))[2])

    def test_hd_result_with_nearby_model_ratio_fills_every_output_edge(self) -> None:
        source = self.make_image_input((12, 20))
        generated = Image.new("RGB", (9, 16), (40, 170, 220))
        generated_output = io.BytesIO()
        generated.save(generated_output, format="PNG")
        generated_url = site.image_bytes_to_data_url(generated_output.getvalue(), "image/png")

        restored_url = site.restore_portrait_hd_source_size(generated_url, source)
        restored_bytes, _mime_type = site.load_image_bytes_from_url(restored_url)
        with Image.open(io.BytesIO(restored_bytes)) as restored:
            self.assertEqual(restored.size, (12, 20))
            for point in ((0, 0), (11, 0), (0, 19), (11, 19)):
                self.assertEqual(restored.getpixel(point), (40, 170, 220))

    def test_openrouter_hd_uses_source_ratio_and_returns_exact_source_size(self) -> None:
        source = self.make_image_input((137, 91))
        reference = self.make_image_input((64, 64), name="reference.png")
        generated = self.make_image_input((2048, 2048), name="generated.png")
        generated_url = site.image_bytes_to_data_url(bytes(generated["data"]), "image/png")

        with patch.object(
            site,
            "call_openrouter_images_api",
            return_value={"images": [generated_url], "text": ""},
        ) as mocked_call:
            result = site.call_openrouter_portrait_hd(
                model="test-model",
                prompt="只做高清",
                aspect_ratio="1:1",
                uploaded_files=[source, reference],
            )

        self.assertEqual(self.read_result_size(result["images"][0]), (137, 91))
        self.assertEqual(result["target_size"], (137, 91))
        self.assertEqual(
            mocked_call.call_args.kwargs["aspect_ratio"],
            site.select_closest_aspect_ratio((137, 91)),
        )
        self.assertIn("最终结果必须严格为 137×91px", mocked_call.call_args.kwargs["prompt"])


if __name__ == "__main__":
    unittest.main()
