import os
import sys
from pathlib import Path

FOLDER = Path(__file__).resolve().parent
ROOT = FOLDER.parents[1]
sys.path.insert(0, str(ROOT))
os.environ['TC_SINGLE_PORT'] = '1'

import streamlit as st
from 图片 import openrouter_image_site as site

site.DB_IMAGE_DIR = FOLDER / 'history'
site.ensure_jimeng_upload_dir = lambda: FOLDER / 'uploads'
# Deliberately wrong configured origin; only the reverse proxy is reachable.
site.get_history_public_base_url = lambda: 'http://public-config.invalid:8000/history_images'
site.get_jimeng_public_upload_base_url = lambda: 'http://public-config.invalid:8000/jimeng_uploads'

st.set_page_config(layout='wide')
st.title('Real Streamlit original download regression')
paths = [site.DB_IMAGE_DIR / 'a/result.png', site.DB_IMAGE_DIR / 'b/result.png', site.DB_IMAGE_DIR / 'c/photo.jpg']
items = [dict(id=i+1, display_image=str(p), original_image=str(p), download_source=str(p),
              download_name=f'原图_{i+1}{p.suffix}', created_at='2026-11-20 12:00:00',
              feature_name='fixture', model='fixture') for i,p in enumerate(paths)]

@st.dialog('历史图片', width='large')
def history():
    site.render_history_gallery(items, key_prefix='e2e_history', columns_per_row=3)

if st.button('打开历史记录'):
    history()

st.subheader('结果图片')
site.render_result_preview([str(p) for p in paths[:2]], show_title=False)

st.subheader('上传参考图和第三方原图')
site.render_zoomable_image_gallery([site.image_bytes_to_data_url(paths[2].read_bytes(),'image/jpeg')],
        columns=1,thumb_height=180,component_key='e2e_data_original')
site.render_zoomable_image_gallery(['http://127.0.0.1:18583/result.png'],
        columns=1,thumb_height=180,component_key='e2e_remote_original')

st.subheader('问答原图按钮')
for index, path in enumerate(paths):
    st.download_button(f'问答下载原图 {index+1}', data=lambda p=path: p.read_bytes(),
                       file_name=path.name, key=f'e2e_qa_{index}', on_click='ignore')

st.subheader('前后对比')
site.render_before_after_compare_gallery([str(paths[0])], [str(paths[1])], ['对比'], 'e2e')
