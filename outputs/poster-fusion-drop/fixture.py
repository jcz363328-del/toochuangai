import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import streamlit as st
from types import SimpleNamespace
from 图片 import openrouter_image_site as site
import importlib
from 图片 import poster_fusion
importlib.reload(poster_fusion)
render = poster_fusion.render
st.set_page_config(layout='wide')
site.inject_app_styles()
site.inject_clipboard_paste_support()
st.session_state.setdefault('feature_results', {})
st.session_state.setdefault('background_jobs', {})
render(SimpleNamespace(st=st, normalize_uploaded_input=site.normalize_uploaded_input,
    render_result_preview=lambda *a, **kw: None, NANO_BANANA_MODEL='test',
    submit_feature_job=lambda *a: None, render_running_job_status=lambda *a: None), {'key':'poster_fusion'})
