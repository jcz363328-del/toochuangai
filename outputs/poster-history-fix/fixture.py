import sys,io
sys.path[:0]=['/tmp/poster-history-fix','/app']
import streamlit as st
from PIL import Image
from 图片 import openrouter_image_site as site
from 图片 import poster_fusion
st.set_page_config(layout='wide')
site.inject_app_styles()
site.inject_clipboard_paste_support()
site.ensure_state()
st.session_state['auth_username']='isolated-ui-check'
st.session_state.setdefault('fixture_cache',{})
def load(key,max_files=20,**kwargs):return st.session_state.fixture_cache.get(key,[])[:max_files]
def save(key,files,**kwargs):
 st.session_state.fixture_cache[key]=[site.normalize_uploaded_input(f) for f in files]
 return st.session_state.fixture_cache[key]
def remove(key,index,**kwargs):
 files=load(key);del files[index];return save(key,files)
site.load_upload_cache=load
site.save_upload_cache=save
site.clear_upload_cache=lambda key,**kwargs:save(key,[])
site.remove_upload_cache_item=remove
site.ensure_history_records_loaded=lambda *a,**kw:[]
site.load_db_history_records=lambda *a,**kw:[]
site.submit_feature_job=lambda *a,**kw:None
with st.sidebar:
 st.title('图片交互验证')
 view=st.radio('功能',['海报融合','批量高清','历史记录'])
@st.dialog('历史记录',width='large')
def history():
 out=io.BytesIO();Image.new('RGB',(600,400),'#46769a').save(out,format='PNG')
 original=site.image_bytes_to_data_url(out.getvalue(),'image/png')
 out=io.BytesIO();Image.new('RGB',(90,60),'#ae6838').save(out,format='PNG')
 preview=site.image_bytes_to_data_url(out.getvalue(),'image/png')
 site.build_history_download_public_url=lambda source:source
 site.render_history_gallery([dict(display_image=preview,original_image=original,download_source=original,download_name='history-original.png',created_at='2026-11-24 10:00',feature_name='海报融合')],key_prefix='ui_history')
if view=='海报融合':poster_fusion.render(site,site.get_feature_by_key('poster_fusion'))
elif view=='批量高清':site.render_openrouter_feature(site.get_feature_by_key('hd_batch'),site.DEFAULT_MODEL,site.DEFAULT_ASPECT_RATIO)
else:
 if st.button('打开历史记录'):history()
