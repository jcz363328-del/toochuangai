import sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import streamlit as st
from 图片 import openrouter_image_site as site
st.set_page_config(layout="wide")
site.ensure_state()
site.inject_app_styles()
site.sync_background_jobs=lambda:None
st.session_state.selected_feature_key="hd_batch"
clicked=st.button("开始处理",key="process_hd_batch")
with st.container(key="workbench_results"):
    site.render_result_preview([],show_title=False,feature_key="hd_batch")
if clicked:
    time.sleep(.5)
    st.session_state.background_jobs={"hd_batch":{"status":"running","stage":"正在请求 Nano Banana 2.1"}}
    st.rerun()
