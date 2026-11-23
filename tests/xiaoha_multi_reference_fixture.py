"""Offline browser fixture. Never uses production credentials or provider APIs."""
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import streamlit as st
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from 图片 import openrouter_image_site as site
from 图片 import multi_reference_composer as composer


def image_bytes(color, subject=False):
    image = Image.new("RGB", (640, 480), color)
    draw = ImageDraw.Draw(image)
    if subject:
        draw.rounded_rectangle((240, 100, 400, 390), 32, fill="#e9c18a", outline="#69482a", width=6)
    else:
        for radius in (60, 100, 150):
            draw.ellipse((320-radius, 240-radius, 320+radius, 240+radius), outline="#bfd0ed", width=3)
    target = io.BytesIO()
    image.save(target, "PNG")
    return target.getvalue()


def blocked(*args, **kwargs):
    raise RuntimeError("External requests are disabled in the offline fixture")


def analyze(**kwargs):
    assert len(kwargs["uploaded_files"]) == 1
    name = kwargs["uploaded_files"][0]["name"]
    values = {
        "background": "柔和蓝色渐变背景，中央自然光晕，顶部左侧柔光，保留宽阔留白。",
        "subject": "画面中央一只暖金色圆角护肤瓶，正面视角，瓶身比例修长。",
        "supporting_elements": "少量透明玻璃道具，位于主体两侧后方。",
        "decoration": "细线圆弧点缀，视觉克制，保持空间层次。",
        "typography": "细长衬线标题与简洁无衬线正文，左对齐，字间距宽松。",
        "texture": "细腻磨砂材质，柔和边缘高光，清晰真实的商业摄影质感。",
        "prompt": name + "：简洁、连贯的商业主视觉，主体清晰，留白充足，蓝金配色与柔和摄影光线。",
    }
    return {"text": json.dumps(values, ensure_ascii=False)}


def submit(feature, context):
    # Execute the real workflow with offline providers; only its queue boundary
    # and image persistence are replaced in this fixture.
    context = {**context, "job_id": "fixture"}
    if context["composer_action"] == "analyze":
        result = composer.run_job(SimpleNamespace(**vars(site)), context)
        composer.accept_analysis_result(st.session_state, result)
    else:
        result = composer.run_job(SimpleNamespace(**vars(site)), context)
        st.session_state.feature_results[feature["key"]] = result
    st.session_state["fixture_last_submission"] = {key: context[key] for key in ("composer_action", "prompt", "max_output_images")}


site.requests.sessions.Session.request = blocked
site.ensure_history_storage = lambda: None
site.get_model_reference_files = lambda: []
site.get_skin_texture_reference_files = lambda: []
site.ensure_jimeng_static_server = blocked
site.call_openrouter = analyze
site.call_openrouter_images_api = lambda **kwargs: {"images": [site.image_bytes_to_data_url(image_bytes("#8ca6ce", True))]}
site.submit_feature_job = submit
site.render_fusion_history_dialog = lambda feature: st.info("离线测试不读取生产历史记录")
site.set_task_progress = lambda *args: None
site.get_runtime_settings_fingerprint = lambda: "offline"

st.set_page_config(page_title="多图参考创作 · 离线验证", layout="wide", initial_sidebar_state="expanded")
site.ensure_state()
st.session_state.is_authenticated = True
st.session_state.auth_username = "offline-fixture"
if not st.session_state.get("fixture_initialized"):
    st.session_state.selected_feature_key = composer.MULTI_REFERENCE_COMPOSER_FEATURE_KEY
    st.session_state.fixture_uploads = {"multi_reference_composer_uploads": [
        {"name": "background.png", "type": "image/png", "data": image_bytes("#7896c1")},
        {"name": "subject.png", "type": "image/png", "data": image_bytes("#dbc8ac", True)},
    ]}
    st.session_state.fixture_initialized = True
site.load_upload_cache = lambda key, **kwargs: list(st.session_state.fixture_uploads.get(key, []))[:kwargs.get("max_files", 10)]
site.save_upload_cache = lambda key, files, **kwargs: st.session_state.fixture_uploads.update({key: list(files)})
site.clear_upload_cache = lambda key, **kwargs: st.session_state.fixture_uploads.pop(key, None)
site.inject_app_styles()
feature = site.get_feature_by_key(st.session_state.selected_feature_key)
with st.sidebar:
    site.render_side_menu(feature)
site.render_openrouter_feature(feature, site.DEFAULT_MODEL, site.DEFAULT_ASPECT_RATIO)
