"""Shared native upload targets with image previews, drag/drop and clipboard support."""
from __future__ import annotations

import base64
import hashlib
import io
import html
import json
from pathlib import Path
import streamlit.components.v1 as components

_FRAME_SCRIPT = Path(__file__).with_name("upload_frame_actions.js").read_text(encoding="utf-8-sig")
from PIL import Image, ImageOps


def render_file_frame(api, label, *, preview_files=None, frame_height=260, remove_button_key="", **kwargs):
    st = api.st
    key = str(kwargs['key'])
    scope_key = 'upload_frame_' + hashlib.sha256(key.encode()).hexdigest()[:16]
    multiple = bool(kwargs.get('accept_multiple_files'))
    preview = 'none'
    original_source = ''
    original_name = ''
    with st.container(key=scope_key):
        uploaded = st.file_uploader(label, **kwargs)
        selected = list(uploaded or []) if multiple else ([uploaded] if uploaded is not None else [])
        shown = selected or list(preview_files or [])
        if shown:
            try:
                raw = api.normalize_uploaded_input(shown[0])['data']
                normalized = api.normalize_uploaded_input(shown[0])
                mime = normalized.get('type') or 'image/png'
                original_source = 'data:' + mime + ';base64,' + base64.b64encode(raw).decode('ascii')
                original_name = str(normalized.get('name') or 'image.png')
                image = ImageOps.exif_transpose(Image.open(io.BytesIO(raw)))
                image.thumbnail((900, 900))
                buf = io.BytesIO()
                image.save(buf, format='PNG')
                preview = 'url("data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii') + '")'
            except (OSError, ValueError, KeyError):
                pass
        has_preview = preview != 'none'
        if has_preview:
            st.markdown('<span class="upload-frame-meta" hidden data-source="' + html.escape(original_source, quote=True) + '" data-filename="' + html.escape(original_name, quote=True) + '" data-remove-key="' + html.escape(remove_button_key, quote=True) + '"></span>', unsafe_allow_html=True)
        # Install in the host realm: upload nonce changes remove the widget iframe.
        # Callbacks owned by a removed iframe otherwise stop working after replacement.
        components.html('<script>const s=window.parent.document.createElement("script");'
                        + 's.textContent=' + json.dumps(_FRAME_SCRIPT).replace('</', r'<\/')
                        + ';window.parent.document.head.appendChild(s);s.remove();</script>', height=0)
        message = ('拖入更多图片 · 点击选图 · Ctrl+V 粘贴' if multiple else '拖入新图片替换 · 点击选图 · Ctrl+V 粘贴') if shown else '＋\\a 拖入图片到此框\\a 或点击选图 · Ctrl+V 粘贴'
        if has_preview:
            message = ('点击放大 · 右键下载、更换或移除' if remove_button_key
                       else '点击放大 · 右击下载或更换 · 拖入 / Ctrl+V 替换')
        allowed = set(kwargs.get('type') or [])
        image_types = {'png', 'jpg', 'jpeg', 'webp', 'bmp', 'tif', 'tiff', 'gif'}
        if allowed - image_types:
            message = '＋\\a 拖入图片或文件到此框\\a 或点击选择文件'
        scope = f'div.st-key-{scope_key}.st-key-{scope_key}'
        if remove_button_key:
            st.markdown('<style>[class~=' + json.dumps('st-key-' + remove_button_key, ensure_ascii=False) + ']{display:none!important;}</style>', unsafe_allow_html=True)
        st.markdown(f'''<style>
        {scope}, {scope} [data-testid="stElementContainer"], {scope} [data-testid="stLayoutWrapper"] {{min-width:0!important;max-width:100%!important;}}
        {scope} [data-testid="stFileUploaderDropzone"] {{
          width:100%!important;max-width:100%!important;min-width:0!important;
          height:{frame_height}px!important;min-height:{frame_height}px!important;
          position:relative!important;overflow:hidden!important;border:1px dashed #6971a7!important;border-radius:14px!important;
          background-color:#0c1529!important;background-image:{preview}!important;
          background-position:center!important;background-repeat:no-repeat!important;background-size:contain!important;
        }}
        {scope} [data-testid="stFileUploaderDropzone"]:hover {{border-color:#a99bff!important;background-color:#14203a!important;}}
        {scope} [data-testid="stFileUploaderDropzone"]::after {{
          content:"{message}"!important;white-space:pre-line!important;text-align:center!important;
          color:#d3d9f4!important;line-height:2!important;pointer-events:none!important;
          position:absolute!important;inset:0!important;display:flex!important;
          align-items:{'end' if has_preview else 'center'}!important;justify-content:center!important;
          padding:12px!important;box-sizing:border-box!important;
          background:{'linear-gradient(transparent 72%,rgba(4,10,25,.9))' if has_preview else 'transparent'}!important;
        }}
        {scope} [data-testid="stFileUploaderDropzoneInstructions"],
        {scope} [data-testid="stFileUploaderDropzone"] button,
        {scope} [data-testid="stFileUploaderFile"], {scope} [data-testid="stFileChips"], {scope} [data-testid="stFileChip"] {{display:none!important;}}
        </style>''', unsafe_allow_html=True)
        if multiple and shown:
            st.caption(f'已选 {len(shown)} 张图片，可继续批量拖入；每张素材在预览区查看。')
        elif allowed - image_types and shown:
            st.caption('已选：' + '、'.join(str(getattr(item, 'name', '') or '文件') for item in shown))
    return uploaded
