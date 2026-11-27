import unittest
import tempfile
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from Department.视觉设计部.xiaoha import poster_fusion as fusion


class PosterFusionTests(unittest.TestCase):
    def test_all_upload_slots_restore_after_widget_cleanup_and_delete_independently(self):
        from Department.视觉设计部.xiaoha import openrouter_image_site as site

        class RerunRequested(Exception):
            pass

        keys = ['poster_fusion_primary'] + [f'poster_fusion_reference_{i}' for i in range(2, 5)]
        originals = [{'name': f'{i}.png', 'type': 'image/png', 'data': bytes([i])} for i in range(4)]
        api = SimpleNamespace(
            st=SimpleNamespace(button=Mock(return_value=False), rerun=Mock(side_effect=RerunRequested)),
            load_upload_cache=partial(site.load_upload_cache, account_name='poster-test'),
            save_upload_cache=partial(site.save_upload_cache, account_name='poster-test'),
            clear_upload_cache=partial(site.clear_upload_cache, account_name='poster-test'),
            get_uploader_widget_key=lambda key: key + '__uploader__0',
            reset_upload_widget=Mock(),
        )
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(site, 'UPLOAD_CACHE_DIR', Path(folder)), \
             patch.object(site, 'ensure_history_storage'), \
             patch('Department.视觉设计部.xiaoha.upload_frames.render_file_frame') as frame:
            for key, image in zip(keys, originals):
                frame.return_value = image
                with self.assertRaises(RerunRequested):
                    fusion.render_image_slot(api, '图片', key)
                api.reset_upload_widget.assert_called_with(key)
            # A native uploader returns None after navigating away and back.
            frame.return_value = None
            for key, image in zip(keys, originals):
                self.assertEqual(fusion.render_image_slot(api, '图片', key), image)
                self.assertEqual(frame.call_args.kwargs['preview_files'], [image])
                self.assertEqual(frame.call_args.kwargs['remove_button_key'], f'clear_upload_{key}')
            self.assertEqual(site.load_upload_cache(keys[0], account_name='other-user'), [])

            replacement = {'name': 'replacement.png', 'type': 'image/png', 'data': b'replacement'}
            frame.return_value = replacement
            with self.assertRaises(RerunRequested):
                fusion.render_image_slot(api, '图片', keys[1])
            frame.return_value = None
            self.assertEqual(fusion.render_image_slot(api, '图片', keys[1]), replacement)

            api.st.button.return_value = True
            with self.assertRaises(RerunRequested):
                fusion.render_image_slot(api, '图片', keys[1])
            api.reset_upload_widget.assert_called_with(keys[1])
            api.st.button.return_value = False
            self.assertIsNone(fusion.render_image_slot(api, '图片', keys[1]))
            for i in (0, 2, 3):
                self.assertEqual(fusion.render_image_slot(api, '图片', keys[i]), originals[i])

    def test_all_four_images_reach_provider_in_role_order(self):
        images = [{'name': str(i), 'data': bytes([i])} for i in range(4)]
        call = Mock(return_value={'images': ['one', 'two']})
        result = fusion.run_job(SimpleNamespace(NANO_BANANA_MODEL='model', call_openrouter_images_api=call), {
            'uploaded_files': images, 'aspect_ratio': '3:4', 'poster_fusion_notes': '花卉环绕商品',
        })
        self.assertEqual(call.call_args.kwargs['uploaded_files'], images)
        self.assertEqual(call.call_args.kwargs['aspect_ratio'], '3:4')
        self.assertIn('第1张是主体海报', call.call_args.kwargs['prompt'])
        self.assertIn('花卉环绕商品', call.call_args.kwargs['prompt'])
        self.assertIn('禁止直接拼贴', call.call_args.kwargs['prompt'])
        self.assertEqual(result['images'], ['one'])

    def test_two_and_three_images_reach_provider_without_padding(self):
        for count in (2, 3):
            with self.subTest(count=count):
                files = [{'name': str(i)} for i in range(count)]
                call = Mock(return_value={'images': ['result']})
                api = SimpleNamespace(NANO_BANANA_MODEL='model', call_openrouter_images_api=call)
                fusion.run_job(api, {'uploaded_files': files})
                self.assertEqual(call.call_args.kwargs['uploaded_files'], files)
                self.assertNotIn('恰好4张', call.call_args.kwargs['prompt'])

    def test_missing_or_extra_reference_never_calls_provider(self):
        call = Mock()
        api = SimpleNamespace(NANO_BANANA_MODEL='model', call_openrouter_images_api=call)
        for count in [0, 1, 5]:
            with self.subTest(count=count), self.assertRaises(ValueError):
                fusion.run_job(api, {'uploaded_files': [{}] * count})
        call.assert_not_called()

    def test_registered_feature_dispatches_to_fusion_and_history(self):
        from unittest.mock import patch
        from Department.视觉设计部.xiaoha import openrouter_image_site as site
        feature = site.get_feature_by_key(fusion.FEATURE_KEY)
        self.assertIsNotNone(feature)
        self.assertIn(feature, site.get_visible_features())
        self.assertIn(fusion.FEATURE_KEY, dict(site.SIDE_MENU_FEATURE_GROUPS)["A+"])
        self.assertNotIn(site.MULTI_REFERENCE_COMPOSER_FEATURE_KEY, dict(site.SIDE_MENU_FEATURE_GROUPS)["A+"])
        self.assertNotIn(fusion.FEATURE_KEY, dict(site.SIDE_MENU_FEATURE_GROUPS)["智能创作"])
        context = {'feature': feature, 'uploaded_files': [{'name': str(i)} for i in range(4)],
                   'output_mode': 'image', 'max_output_images': 1}
        with patch.object(site, 'call_openrouter_images_api', return_value={'images': ['result']}) as call, \
             patch.object(site, 'finalize_feature_job_result', side_effect=lambda c, r, j: r) as finalize:
            result = site.run_feature_job(context)
        self.assertEqual(result['images'], ['result'])
        self.assertEqual(len(call.call_args.kwargs['uploaded_files']), 4)
        finalize.assert_called_once()

    def test_empty_provider_response_fails_clearly(self):
        api = SimpleNamespace(NANO_BANANA_MODEL='model', call_openrouter_images_api=Mock(return_value={}))
        with self.assertRaisesRegex(RuntimeError, '未返回'):
            fusion.run_job(api, {'uploaded_files': [{}] * 4})

    def test_page_requires_all_roles_and_can_submit_again_after_completion(self):
        from streamlit.testing.v1 import AppTest
        script = '''
import io
import streamlit as st
from PIL import Image
from types import SimpleNamespace
from unittest.mock import patch
from Department.视觉设计部.xiaoha.poster_fusion import render
st.session_state.setdefault('feature_results', {})
st.session_state.setdefault('background_jobs', {})
st.session_state.setdefault('upload_cache', {})
st.session_state.setdefault('seeded_uploads', set())
buf = io.BytesIO()
Image.new('RGB', (20, 30), 'blue').save(buf, format='PNG')
def upload(label, **kwargs):
    key = kwargs['key'].split('__uploader__')[0]
    if key in st.session_state.seeded_uploads: return None
    st.session_state.seeded_uploads.add(key)
    out = io.BytesIO(buf.getvalue()); out.name = key + '.png'
    return out
def normalize(f):
    return f if isinstance(f, dict) else {'name': f.name, 'data': f.getvalue(), 'type': 'image/png'}
def save(key, files):
    st.session_state.upload_cache[key] = [normalize(f) for f in files]
def reset(key):
    state_key = 'nonce_' + key
    st.session_state[state_key] = st.session_state.get(state_key, 0) + 1
def submit(feature, context):
    st.session_state['submitted'] = context
    st.session_state['submit_count'] = st.session_state.get('submit_count', 0) + 1
api = SimpleNamespace(st=st, NANO_BANANA_MODEL='test',
    normalize_uploaded_input=normalize,
    load_upload_cache=lambda key, **kw: st.session_state.upload_cache.get(key, []),
    save_upload_cache=save, clear_upload_cache=lambda key: st.session_state.upload_cache.pop(key, None),
    get_uploader_widget_key=lambda key: key + '__uploader__' + str(st.session_state.get('nonce_' + key, 0)),
    reset_upload_widget=reset,
    submit_feature_job=submit, render_running_job_status=lambda k: None,
    render_image_workbench_header=lambda *a: st.button("历史记录", key="history"),
    render_result_preview=lambda *a, **kw: None)
current = st.radio('功能', ['海报融合', '其他功能'], key='test_feature')
if current == '海报融合':
    with patch.object(st, 'file_uploader', side_effect=upload):
        render(api, {'key': 'poster_fusion', 'name': '海报融合'})
'''
        app = AppTest.from_string(script).run()
        self.assertFalse(list(app.exception))
        self.assertTrue(any(b.label == "历史记录" for b in app.button))
        self.assertFalse(next(b for b in app.button if b.key == "poster_fusion_generate").disabled)
        next(b for b in app.button if b.key == "poster_fusion_generate").click().run()
        self.assertFalse(list(app.exception))
        submitted = app.session_state['submitted']
        self.assertEqual(len(submitted['uploaded_files']), 4)
        self.assertIn('primary', submitted['uploaded_files'][0]['name'])
        self.assertEqual(submitted['max_output_images'], 1)
        app.session_state['background_jobs'] = {'poster_fusion': {'status': 'running'}}
        app.run()
        self.assertTrue(next(b for b in app.button if b.key == "poster_fusion_generate").disabled)
        app.session_state['background_jobs'] = {'poster_fusion': {'status': 'completed'}}
        app.run()
        self.assertFalse(next(b for b in app.button if b.key == "poster_fusion_generate").disabled)
        app.radio(key='test_feature').set_value('其他功能').run()
        self.assertFalse(list(app.exception))
        app.radio(key='test_feature').set_value('海报融合').run()
        self.assertFalse(next(b for b in app.button if b.key == "poster_fusion_generate").disabled)
        self.assertEqual(len(app.session_state['upload_cache']), 4)
        # Optional reference slots may be empty, including gaps in slot order.
        for key, expected in [('poster_fusion_reference_2', 3), ('poster_fusion_reference_3', 2)]:
            app.button(key='clear_upload_' + key).click().run()
            before_count = app.session_state['submit_count']
            app.button(key='poster_fusion_generate').click().run()
            self.assertEqual(app.session_state['submit_count'], before_count + 1)
            self.assertEqual(len(app.session_state['submitted']['uploaded_files']), expected)
            self.assertIn('primary', app.session_state['submitted']['uploaded_files'][0]['name'])
        for missing in ['poster_fusion_reference_4', 'poster_fusion_primary']:
            app.button(key='clear_upload_' + missing).click().run()
            before_count = app.session_state['submit_count']
            app.button(key='poster_fusion_generate').click().run()
            self.assertTrue(any("请先补齐素材" in warning.value for warning in app.warning))
            self.assertEqual(app.session_state['submit_count'], before_count)
        self.assertFalse(list(app.exception))


if __name__ == '__main__':
    unittest.main()
