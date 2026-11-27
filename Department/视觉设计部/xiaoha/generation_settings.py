"""Image choices captured per job, independently of subsequent UI changes."""
from contextvars import ContextVar
from functools import wraps
import inspect

SEEDREAM_MODEL = "doubao-seedream-5-0-pro-260628"
SEEDREAM_MODEL_ALIASES = (SEEDREAM_MODEL, "Dola-Seedream-5.0-pro", "bytedance-seed/seedream-4.5", "seedream-5-pro")


def is_seedream_model(model):
    return str(model or "").strip() in SEEDREAM_MODEL_ALIASES

IMAGE_MODELS = {
    "gemini-nano-banana-2.1": "Nano Banana 2.1",
    "gpt-image-2.6-sunburst": "GPT Image 2.6 Sunburst",
    SEEDREAM_MODEL: "Seedream 5 Pro（字节官方）",
}
DEFAULT_IMAGE_MODEL = "gemini-nano-banana-2.1"
DEFAULT_RESOLUTION = "2K"
_current_settings = ContextVar("xiaoha_image_settings", default=None)


def resolution_options(model):
    return ("1K", "1.5K", "2K") if is_seedream_model(model) else ("1K", "2K", "4K")


def with_job_image_settings(function):
    @wraps(function)
    def wrapped(context, *args, **kwargs):
        choices = context.get("generation_settings")
        if not choices and context.get("output_mode") == "image":
            choices = {"model": context.get("model") or DEFAULT_IMAGE_MODEL,
                       "resolution": context.get("resolution") or DEFAULT_RESOLUTION}
        token = _current_settings.set(dict(choices) if choices else None)
        try:
            return function(context, *args, **kwargs)
        finally:
            _current_settings.reset(token)
    return wrapped


def apply_image_settings(function):
    signature = inspect.signature(function)
    @wraps(function)
    def wrapped(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        choices = _current_settings.get()
        if choices:
            bound.arguments["model"] = choices["model"]
            bound.arguments["resolution"] = choices["resolution"]
        elif not bound.arguments.get("resolution"):
            bound.arguments["resolution"] = DEFAULT_RESOLUTION
        if choices and "prompt" in bound.arguments:
            prompt = str(bound.arguments["prompt"])
            for old in ("原生 4K", "原生4K", "4K 高清", "4K高清"):
                prompt = prompt.replace(old, old.replace("4K", choices["resolution"]))
            bound.arguments["prompt"] = prompt
        return function(*bound.args, **bound.kwargs)
    return wrapped


def current_resolution():
    return (_current_settings.get() or {}).get("resolution", DEFAULT_RESOLUTION)


def media_image_parameters(model, resolution="2K", aspect_ratio="1:1"):
    if is_seedream_model(model):
        raise ValueError("Seedream 5 Pro 必须使用字节官方接口。")
    if resolution not in resolution_options(model):
        raise ValueError("该模型不支持所选分辨率。")
    if model.startswith("gpt-image-"):
        # Published GPT presets use a different pixel budget from Gemini.
        size = {"1K": "1024x1024", "2K": "2048x2048", "4K": "2880x2880"}[resolution]
        if resolution == "4K" and aspect_ratio == "16:9":
            size = "3840x2160"
        return {"size": size, "quality": "high"}
    if model.startswith("grok-"):
        return {"n": 1}
    return {"aspect_ratio": aspect_ratio, "image_size": resolution}
