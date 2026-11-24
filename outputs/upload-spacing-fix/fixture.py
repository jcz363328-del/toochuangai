import importlib,sys
from pathlib import Path
sys.path.insert(0,'/app')
import streamlit as st
from 图片 import openrouter_image_site as site
from 图片 import upload_frames

st.set_page_config(layout='wide',initial_sidebar_state='expanded')
site.inject_app_styles()
site.inject_clipboard_paste_support()
st.session_state.setdefault('auth_username','offline')
st.session_state.setdefault('feature_results',{})
st.session_state.setdefault('background_jobs',{})
st.session_state.setdefault('fixture_cache',{})
def load(key,max_files=10,**kwargs):return st.session_state.fixture_cache.get(key,[])[:max_files]
def save(key,files,**kwargs):
    st.session_state.fixture_cache[key]=[site.normalize_uploaded_input(f) for f in files]
    return st.session_state.fixture_cache[key]
site.load_upload_cache=load
site.save_upload_cache=save
site.clear_upload_cache=lambda key,**kwargs:save(key,[])
def remove(key,index,**kwargs):
    files=load(key);del files[index];return save(key,files)
site.remove_upload_cache_item=remove
def reorder(key,source,target,**kwargs):
    files=load(key);files.insert(target,files.pop(source));return save(key,files)
site.reorder_upload_cache_item=reorder
with st.sidebar:st.title('小哈上传框测试')
kind=st.query_params.get('kind','single')
if kind=='single':files=[site.render_single_image_uploader('单图输入','single')]
elif kind=='multi':files=site.render_multi_image_uploader('批量素材','multi',max_files=3,allow_reorder=True)
elif kind=='refs':files=site.render_reference_slot_uploaders('reference',3)
elif kind=='compact':files=[site.render_compact_element_image_uploader('元素素材','compact')]
elif kind=='hero':files=site.render_first_screen_material_uploader('hero',hero=True)
elif kind=='materials':files=site.render_first_screen_material_uploader('materials',hero=False)
elif kind=='poster':
    from 图片 import poster_fusion
    importlib.reload(poster_fusion)
    poster_fusion.render(site,site.get_feature_by_key('poster_fusion'))
    files=[]
elif kind=='actual':
    site.ensure_state()
    st.session_state.auth_username='offline'
    site.ensure_history_records_loaded=lambda *args,**kwargs: []
    site.load_db_history_records=lambda *args,**kwargs: []
    site.render_openrouter_feature(site.get_feature_by_key(st.query_params.get('feature',site.IMAGE_SMART_ANALYSIS_FEATURE_KEY)),site.DEFAULT_MODEL,site.DEFAULT_ASPECT_RATIO)
    files=[]
else:files=[]
st.json([site.get_uploaded_file_name(f) for f in files if f is not None])
