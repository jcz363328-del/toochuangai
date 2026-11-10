"""Offline Streamlit fixture using the production Xiaoha rendering functions.

Only storage, credentials and job boundaries are replaced. Run through
``xiaoha_ui_responsive_browser.cjs``; never use the production service port.
"""
from __future__ import annotations

import importlib
import io
import sys
from pathlib import Path

import streamlit as st
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from 图片 import openrouter_image_site as site
importlib.reload(site)


def blocked(*args, **kwargs):
    raise RuntimeError("External services are disabled in the responsive UI fixture")


def fixture_image() -> bytes:
    image = Image.new("RGB", (160, 210), "#373049")
    draw = ImageDraw.Draw(image)
    draw.ellipse((48, 20, 112, 94), fill="#bd95a1")
    draw.rounded_rectangle((34, 85, 126, 205), radius=30, fill="#7361bc")
    target = io.BytesIO()
    image.save(target, "PNG")
    return target.getvalue()


def cached_files(key: str, max_files: int = 1, **kwargs):
    storage = st.session_state.setdefault("fixture_uploads", {})
    if key not in storage:
        storage[key] = (
            [{"name": "fixture.png", "type": "image/png", "data": fixture_image()}]
            if key.startswith("batch_uploader_")
            else []
        )
    return storage[key][:max_files]


def save_files(key: str, files, **kwargs):
    st.session_state.fixture_uploads[key] = list(files)
    return list(files)


def main() -> None:
    # The requests object belongs to production code, so refuse every outbound
    # request explicitly in addition to replacing its persistence boundaries.
    site.requests.sessions.Session.request = blocked
    site.ensure_history_storage = lambda: None
    site.get_model_reference_files = lambda: []
    reference = ROOT / "outputs" / "xiaoha-responsive" / "fixture-reference.png"
    reference.parent.mkdir(parents=True, exist_ok=True)
    if not reference.exists():
        reference.write_bytes(fixture_image())
    site.get_skin_texture_reference_files = lambda: [reference]
    site.load_upload_cache = cached_files
    site.save_upload_cache = save_files
    site.clear_upload_cache = lambda key, **kwargs: save_files(key, [])
    site.ensure_history_records_loaded = lambda *args, **kwargs: []
    site.load_db_history_records = blocked
    site.submit_feature_job = blocked
    site.ensure_jimeng_static_server = blocked
    site.prepress_check_service.stage_file = blocked
    site.prepress_check_service.run_check = blocked
    site.prepress_check_service.reset_session = blocked

    st.set_page_config(page_title=f"小哈 · 响应式离线回归 · Streamlit {st.__version__}", layout="wide")
    site.ensure_state()
    st.session_state.is_authenticated = True
    st.session_state.auth_username = "responsive-fixture"
    site.inject_app_styles()
    visible = site.get_visible_features()
    feature = next(
        (item for item in visible if item["key"] == st.session_state.selected_feature_key),
        site.get_feature_by_key("hd_batch"),
    )
    if st.session_state.get("side_menu_visible", True):
        menu_col, content_col = st.columns([0.55, 4.45], gap="small")
        with menu_col:
            site.render_side_menu(feature)
    else:
        st.markdown('<span class="collapsed-side-menu-marker"></span>', unsafe_allow_html=True)
        st.button("▶", key="show_side_menu", on_click=site.set_side_menu_visible, args=(True,))
        content_col = st.container()
    with content_col:
        site.render_openrouter_feature(feature, model=site.DEFAULT_MODEL, aspect_ratio=site.DEFAULT_ASPECT_RATIO)


main()
