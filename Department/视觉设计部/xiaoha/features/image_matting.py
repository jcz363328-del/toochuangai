"""Run local ONNX image matting and refine the resulting mask."""

from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps


class ImageMattingSegmenter:
    """Local ONNX matting backend adapted from pangxiaobin/image-matting."""

    def __init__(self, model_path: Path, model_input_size: tuple[int, int], *, default_model_path: Path, trim_image) -> None:
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise RuntimeError("缺少 onnxruntime，请先安装依赖：pip install onnxruntime opencv-python") from exc

        resolved_model_path = Path(model_path).expanduser()
        if not resolved_model_path.exists() or not resolved_model_path.is_file():
            raise RuntimeError(
                "未找到 image-matting 的 RMBG-1.4 ONNX 模型文件。"
                f"请把 model.onnx 放到：{default_model_path}，"
                "或通过环境变量 IMAGE_MATTING_MODEL_PATH 指定模型路径。"
            )

        self.trim_image = trim_image
        self.model_path = resolved_model_path
        self.model_input_size = (int(model_input_size[0]), int(model_input_size[1]))
        providers = self.get_available_providers(ort)
        try:
            if "DmlExecutionProvider" in providers:
                session_options = ort.SessionOptions()
                session_options.enable_mem_pattern = False
                session_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
                self.ort_session = ort.InferenceSession(
                    str(self.model_path),
                    providers=providers,
                    sess_options=session_options,
                )
            else:
                self.ort_session = ort.InferenceSession(str(self.model_path), providers=providers)
        except Exception as exc:
            raise RuntimeError(f"image-matting 模型加载失败：{exc}") from exc

    @staticmethod
    def get_available_providers(ort: Any) -> list[str]:
        available_providers = list(ort.get_available_providers())
        if "CUDAExecutionProvider" in available_providers:
            return ["CUDAExecutionProvider", "CPUExecutionProvider"]
        if "DmlExecutionProvider" in available_providers:
            return ["DmlExecutionProvider", "CPUExecutionProvider"]
        return ["CPUExecutionProvider"]

    def preprocess_image(self, image_array: Any) -> Any:
        import numpy as np

        if len(image_array.shape) < 3:
            image_array = image_array[:, :, np.newaxis]
        resized = np.array(Image.fromarray(image_array).resize(self.model_input_size, Image.Resampling.BILINEAR))
        normalized = resized.astype(np.float32) / 255.0
        mean = np.array([0.5, 0.5, 0.5], dtype=np.float32)
        normalized = (normalized - mean) / np.array([1.0, 1.0, 1.0], dtype=np.float32)
        normalized = normalized.transpose(2, 0, 1)
        return np.expand_dims(normalized, axis=0)

    @staticmethod
    def postprocess_mask(result: Any, image_size: tuple[int, int]) -> Image.Image:
        import numpy as np

        mask_array = np.squeeze(result).astype(np.float32)
        mask = Image.fromarray(mask_array).resize(image_size, Image.Resampling.BILINEAR)
        resized = np.asarray(mask).astype(np.float32)
        max_value = float(resized.max()) if resized.size else 0.0
        min_value = float(resized.min()) if resized.size else 0.0
        if max_value - min_value <= 1e-6:
            alpha = np.zeros_like(resized, dtype=np.uint8)
        else:
            alpha = ((resized - min_value) / (max_value - min_value) * 255.0).clip(0, 255).astype(np.uint8)
        return Image.fromarray(alpha, mode="L")

    def segment_image(self, image: Image.Image, trim_result: bool = True) -> Image.Image:
        import numpy as np

        original = ImageOps.exif_transpose(image).convert("RGBA")
        input_image = original.convert("RGB")
        image_array = np.array(input_image)
        preprocessed = self.preprocess_image(image_array)
        ort_inputs = {self.ort_session.get_inputs()[0].name: preprocessed}
        try:
            ort_outputs = self.ort_session.run(None, ort_inputs)
        except Exception as exc:
            raise RuntimeError(f"image-matting ONNX 推理失败：{exc}") from exc

        alpha = self.postprocess_mask(ort_outputs[0][0][0], input_image.size)
        alpha = alpha.filter(ImageFilter.GaussianBlur(0.35))
        alpha = ImageEnhance.Contrast(alpha).enhance(1.08)
        alpha = ImageChops.multiply(alpha, original.getchannel("A"))
        result = original.copy()
        result.putalpha(alpha)
        if trim_result:
            return self.trim_image(result)
        return result
