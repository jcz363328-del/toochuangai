import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest


class APlusCanvasTests(unittest.TestCase):
    def test_workspace_switches_between_canvas_and_only_a_plus_tools(self):
        script = '''
import streamlit as st
from types import SimpleNamespace
from Department.视觉设计部.xiaoha.a_plus_canvas import render
features = {'a_plus_canvas': {'key': 'a_plus_canvas', 'name': 'A+画布'},
            'main_image_a_plus': {'key': 'main_image_a_plus', 'name': '主图生A+'},
            'amazon_to_walmart_a_plus': {'key': 'amazon_to_walmart_a_plus', 'name': '沃尔玛A+'},
            'hidden_tool': {'key': 'hidden_tool', 'name': '隐藏', 'hidden': True}}
api = SimpleNamespace(st=st,
    SIDE_MENU_FEATURE_GROUPS=(('A+', tuple(features)), ('模特', ('pose_change',))),
    get_feature_by_key=features.get,
    render_replacement_infinite_canvas_feature=lambda feature: st.text('canvas-rendered'),
    render_openrouter_feature=lambda feature, **kwargs: st.text('tool:' + feature['key']))
render(api, features['a_plus_canvas'], 'test-model', '4:3')
'''
        app = AppTest.from_string(script).run()
        self.assertFalse(list(app.exception))
        self.assertEqual(app.text[0].value, 'canvas-rendered')
        self.assertEqual(len(app.selectbox), 0)

    def test_both_canvas_entries_are_registered(self):
        from Department.视觉设计部.xiaoha import openrouter_image_site as site
        groups = dict(site.SIDE_MENU_FEATURE_GROUPS)
        self.assertIn('a_plus_canvas', groups['A+'])
        self.assertIn('infinite_canvas', groups['工作台'])
        self.assertIsNotNone(site.get_feature_by_key('a_plus_canvas'))
        self.assertEqual(len([item for item in site.FEATURES if item['key'] == 'a_plus_canvas']), 1)


if __name__ == '__main__':
    unittest.main()
