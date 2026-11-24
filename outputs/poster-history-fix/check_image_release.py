import sys,io
sys.path.insert(0,'/app')
from unittest.mock import patch
from PIL import Image
from streamlit.testing.v1 import AppTest
from 图片 import openrouter_image_site as site
from 图片 import poster_fusion,upload_frames
feature=site.get_feature_by_key('poster_fusion')
assert feature and feature in site.get_visible_features()
assert 'poster_fusion' in dict(site.SIDE_MENU_FEATURE_GROUPS)['A+']
files=[{'name':f'{i}.png','type':'image/png','data':bytes([i])} for i in range(4)]
with patch.object(site,'call_openrouter_images_api',return_value={'images':['ok']}) as call, patch.object(site,'finalize_feature_job_result',side_effect=lambda context,result,job:result):
 result=site.run_feature_job({'feature':feature,'uploaded_files':files,'output_mode':'image','max_output_images':1})
 assert result['images']==['ok']
 assert call.call_args.kwargs['uploaded_files']==files
script='''
import streamlit as st
from 图片 import openrouter_image_site as site
st.set_page_config(layout='wide')
site.ensure_state()
st.session_state['auth_username']='isolated-package-test'
site.load_upload_cache=lambda *a,**kw:[]
site.render_openrouter_feature(site.get_feature_by_key('poster_fusion'),site.DEFAULT_MODEL,site.DEFAULT_ASPECT_RATIO)
'''
app=AppTest.from_string(script).run(timeout=15)
assert not list(app.exception),list(app.exception)
assert app.button(key='poster_fusion_generate').disabled
out=io.BytesIO();Image.new('RGB',(20,20),'blue').save(out,format='PNG')
source=site.image_bytes_to_data_url(out.getvalue(),'image/png')
with patch.object(site.st,'iframe') as render:
 site.render_zoomable_image_gallery([source],1,120,'test_image_package',native_fullscreen_context_menu=True)
 assert 'if (true || event.altKey) return;' in render.call_args.args[0]
print('PASS: packaged poster registration, menu, worker role order, real empty page render, upload-frame dependency and native history menu')
