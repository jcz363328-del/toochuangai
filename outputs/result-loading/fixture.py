import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import streamlit as st
from 图片 import openrouter_image_site as site
st.set_page_config(layout="wide")
site.ensure_state()
site.inject_app_styles()
site.sync_background_jobs=lambda:None
site.ensure_history_records_loaded=lambda *a,**k:[]
site.load_db_history_records=lambda *a,**k:[]
site.load_upload_cache=lambda *a,**k:[]
site.get_model_reference_files=lambda:[]
site.get_skin_texture_reference_files=lambda:[]
feature=site.get_feature_by_key(st.query_params.get("feature","hd_batch"))
key=feature["key"]
st.session_state.selected_feature_key=key
status=st.selectbox("测试任务状态",["running","queued","completed"])
st.session_state.background_jobs={key:{"status":status,"stage":"正在请求 Nano Banana 2.1","job_id":"demo"}}
site.render_openrouter_feature(feature,site.NANO_BANANA_MODEL,site.DEFAULT_ASPECT_RATIO)
