from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from 图片 import openrouter_image_site as site
site.st.set_page_config(page_title='小哈聊天布局验收',layout='wide',initial_sidebar_state='collapsed')
import importlib
from 图片 import qa_chat
importlib.reload(qa_chat)
site.ensure_state()
site.inject_app_styles()
site.st.session_state.auth_username = '视觉验收'
site.HISTORY_DIR = Path(__file__).parent / 'history'
if site.st.query_params.get('sample') == '1':
    from 图片.qa_chat import ChatStore
    from PIL import Image
    store = ChatStore(site.HISTORY_DIR)
    if not any(store.turns('视觉验收',c['id']) for c in store.list('视觉验收')):
        chat = store.create('视觉验收')
        image = Path(__file__).parent / 'sample.png'
        Image.new('RGB',(640,400),'#ddc28c').save(image)
        turn = store.add('视觉验收',chat,'参考这张图片，生成金色复古纸张背景，中央留白。',[],site.DEFAULT_MODEL)
        store.update('视觉验收',turn,status='completed',images=[str(image.resolve())])
site.render_openrouter_feature(site.get_feature_by_key('ai_qa_image'),site.DEFAULT_MODEL,site.DEFAULT_ASPECT_RATIO)


