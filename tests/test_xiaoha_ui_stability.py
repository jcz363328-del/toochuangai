from __future__ import annotations

import inspect
import unittest

from Department.视觉设计部.xiaoha import openrouter_image_site as site


class XiaoHaUiStabilityTests(unittest.TestCase):
    def test_sidebar_styles_support_current_and_legacy_streamlit_columns(self) -> None:
        source = inspect.getsource(site._workbench_assets.inject_app_styles)
        self.assertIn(':is(div[data-testid="column"], div[data-testid="stColumn"]):has(.side-menu-shell)', source)
        self.assertNotIn('        div[data-testid="column"]:has(.side-menu-shell)', source)
        for state in ("summary:hover", "summary:focus", "summary:focus-visible", "summary:active", "details[open] > summary"):
            self.assertIn(state, source)

    def test_gallery_preview_conversion_is_cached_without_spinner(self) -> None:
        source = inspect.getsource(site.build_gallery_preview_data_url)

        self.assertIn("@st.cache_data(show_spinner=False, max_entries=256)", source)

    def test_stale_render_tree_does_not_fade_during_widget_rerun(self) -> None:
        source = inspect.getsource(site._workbench_assets.inject_app_styles)

        self.assertIn('[data-stale="true"]', source)
        self.assertIn("opacity: 1 !important", source)
        self.assertIn("transition: none !important", source)

    def test_shared_feature_workbench_uses_stable_compact_layout(self) -> None:
        source = inspect.getsource(site._feature_workbench.render_openrouter_feature)

        self.assertIn('else [1, 1]', source)
        self.assertIn('st.columns(column_ratio, gap="medium")', source)
        self.assertIn('feature-workbench-left-marker', source)
        self.assertIn('feature-workbench-right-marker', source)
        self.assertIn('meta_items = meta_items[:3]', source)
        self.assertIn('if len(page_subtitle) > 42:', source)


if __name__ == "__main__":
    unittest.main()
