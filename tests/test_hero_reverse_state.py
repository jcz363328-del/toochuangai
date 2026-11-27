import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from Department.视觉设计部.xiaoha import openrouter_image_site as site


APP = '''
import streamlit as st
from unittest.mock import patch
from Department.视觉设计部.xiaoha import openrouter_image_site as site
page = st.radio('Page', ['reverse', 'other'], key='page')
if page == 'reverse':
    with patch.object(site, 'render_single_image_uploader', return_value={'data':b'test', 'name':'test.png'}), \\
         patch.object(site, 'analyze_hero_style_reverse_reference', return_value={'prompt':'generated prompt'}), \\
         patch.object(site, 'render_result_preview'), patch.object(site, 'render_history_records'):
        site.render_a_plus_hero_style_reverse_feature({'key':site.A_PLUS_HERO_STYLE_REVERSE_FEATURE_KEY,'name':'reverse'})
'''


class HeroReverseStateTests(unittest.TestCase):
    def test_completed_job_restores_batch_once_after_leaving_page(self):
        class State(dict):
            __getattr__ = dict.__getitem__
            __setattr__ = dict.__setitem__
        state = State(feature_results={}, history_records_cache={},
                      hero_style_reverse_state={'prompt':'edited draft'}, auth_username='tester')
        result = {'images':['finished.png'], 'hero_reverse_batch':{
            'prompt':'submitted prompt', 'target_size':[1464,1800], 'parent':''}}
        job = {'job_id':'persistent-job'}
        with patch.object(site.st, 'session_state', state), \
                patch.object(site, 'set_history_visible_limit'):
            site.store_completed_background_job_result(site.A_PLUS_HERO_STYLE_REVERSE_FEATURE_KEY, job, result)
            site.store_completed_background_job_result(site.A_PLUS_HERO_STYLE_REVERSE_FEATURE_KEY, job, result)
        self.assertEqual(state.hero_style_reverse_state['prompt'], 'edited draft')
        self.assertEqual(len(state.hero_style_reverse_state['batches']), 1)
        self.assertEqual(state.hero_style_reverse_state['batches'][0]['images'], ['finished.png'])

    def test_prompt_survives_height_change_and_navigation(self):
        app = AppTest.from_string(APP, default_timeout=20).run()
        self.assertFalse(app.exception)
        app.button(key='analyze_' + site.A_PLUS_HERO_STYLE_REVERSE_FEATURE_KEY).click().run()
        key = 'hero_style_reverse_prompt_' + site.A_PLUS_HERO_STYLE_REVERSE_FEATURE_KEY
        self.assertEqual(app.text_area(key=key).value, 'generated prompt')
        app.number_input(key='hero_style_reverse_height_' + site.A_PLUS_HERO_STYLE_REVERSE_FEATURE_KEY).set_value(1800).run()
        self.assertEqual(app.text_area(key=key).value, 'generated prompt')
        app.text_area(key=key).set_value('edited prompt').run()
        app.radio(key='page').set_value('other').run()
        app.radio(key='page').set_value('reverse').run()
        self.assertFalse(app.exception)
        self.assertEqual(app.text_area(key=key).value, 'edited prompt')
        self.assertEqual(app.number_input(key='hero_style_reverse_height_' + site.A_PLUS_HERO_STYLE_REVERSE_FEATURE_KEY).value, 1800)

    def test_generation_worker_finishes_without_ui_session(self):
        entered, resume = Event(), Event()
        def generate(*args):
            entered.set()
            self.assertTrue(resume.wait(5))
            return ['result.png']
        context = {'prompt':'saved prompt','uploaded_files':[], 'hero_reverse_count':2,
                   'aspect_ratio':'4:3','hero_reverse_size':[0,0]}
        with patch.object(site, 'generate_hero_style_reverse_images', side_effect=generate):
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(site.run_hero_reverse_job, context)
                self.assertTrue(entered.wait(5))
                resume.set()
                result = future.result(timeout=5)
        self.assertEqual(result['images'], ['result.png'])
        self.assertEqual(result['hero_reverse_batch']['prompt'], 'saved prompt')

    def test_reverse_job_uses_background_dispatch(self):
        context = {'feature': {'key':site.A_PLUS_HERO_STYLE_REVERSE_FEATURE_KEY}}
        with patch.object(site, 'run_hero_reverse_job', return_value={'images':['result']}) as run, \
                patch.object(site, 'finalize_feature_job_result', side_effect=lambda c,r,j:r):
            result = site._run_feature_job_once(context)
        run.assert_called_once_with(context)
        self.assertEqual(result['images'], ['result'])
