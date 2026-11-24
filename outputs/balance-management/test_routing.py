"""Exercise the staged routes without importing the app or live provider."""
from __future__ import annotations

import ast
from contextlib import nullcontext
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
import unittest
from unittest.mock import Mock, patch as mock_patch

from patch_main import patch


ROOT = Path(__file__).resolve().parent
BASELINES = ("runtime", "image")


def extracted_namespace(baseline, names):
    source = (ROOT / f"{baseline}-patched.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    selected = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.Assign))
                and ((isinstance(node, ast.FunctionDef) and node.name in names)
                     or (isinstance(node, ast.Assign) and any(
                         isinstance(target, ast.Name) and target.id in {
                             "XIAOHA_DASHBOARD_KEY", "XIAOHA_BALANCE_KEY", "XIAOHA_DEFAULT_FEATURE_KEY",
                             "FEATURE_QUERY_KEY", "DEFAULT_MODEL", "DEFAULT_ASPECT_RATIO",
                             "NANO_BANANA_MODEL", "SIDE_MENU_FEATURE_GROUPS",
                         } for target in node.targets)))]
    # The special-page navigation is independent of the image feature groups.
    namespace = {"Any": Any, "SimpleNamespace": SimpleNamespace, "SIDE_MENU_FEATURE_GROUPS": ()}
    exec(compile(ast.Module(body=selected, type_ignores=[]), source[:0] + baseline, "exec"), namespace)
    return namespace


def fake_streamlit(selected="__balance__", authenticated=True):
    return SimpleNamespace(
        session_state=SimpleNamespace(selected_feature_key=selected, is_authenticated=authenticated),
        query_params={"feature": selected},
        sidebar=nullcontext(), container=Mock(side_effect=lambda **_: nullcontext()),
        expander=Mock(side_effect=lambda *_, **__: nullcontext()),
        button=Mock(), markdown=Mock(), warning=Mock(), rerun=Mock(), set_page_config=Mock(),
    )


def main_namespace(baseline, selected, authenticated=True):
    namespace = extracted_namespace(baseline, {"main"})
    namespace["st"] = fake_streamlit(selected, authenticated)
    for name in (
        "ensure_state", "restore_auth_session", "sync_background_jobs", "ensure_history_storage",
        "inject_app_styles", "inject_clipboard_paste_support", "inject_upload_reorder_support",
        "authenticate_requested_user", "render_side_menu", "render_xiaoha_usage_dashboard",
        "render_xiaoha_balance_management", "render_openrouter_feature",
    ):
        namespace[name] = Mock()
    for name in ("consume_pending_upload_delete", "consume_pending_upload_reorder", "consume_pending_outpaint_drag"):
        namespace[name] = Mock(return_value=False)
    namespace["ensure_jimeng_static_server"] = Mock(return_value={"started": True})
    namespace["get_visible_features"] = Mock(return_value=[{"key": "hd_batch", "name": "批量高清"}])
    return namespace


class BalanceRoutingTests(unittest.TestCase):
    def test_sidebar_exposes_balance_and_uses_existing_selection_callback(self):
        for baseline in BASELINES:
            with self.subTest(baseline=baseline):
                ns = extracted_namespace(baseline, {"render_side_menu"})
                ns.update(st=fake_streamlit(), get_visible_features=Mock(return_value=[]), select_feature=Mock())
                ns["render_side_menu"]()
                buttons = [call for call in ns["st"].button.call_args_list if call.args == ("余额管理",)]
                self.assertEqual(len(buttons), 1)
                self.assertEqual(buttons[0].kwargs["args"], ("__balance__",))
                self.assertIs(buttons[0].kwargs["on_click"], ns["select_feature"])
                self.assertEqual(buttons[0].kwargs["type"], "primary")
                ns["st"].expander.assert_any_call("状态与数据", expanded=True)

    def test_deep_link_survives_validation_and_dispatches_for_each_existing_auth_state(self):
        for baseline in BASELINES:
            for authenticated in (True, False):
                with self.subTest(baseline=baseline, authenticated=authenticated):
                    ns = main_namespace(baseline, "__balance__", authenticated)
                    ns["main"]()
                    self.assertEqual(ns["st"].session_state.selected_feature_key, "__balance__")
                    self.assertEqual(ns["st"].query_params["feature"], "__balance__")
                    ns["render_xiaoha_balance_management"].assert_called_once_with()
                    ns["render_openrouter_feature"].assert_not_called()
                    ns["render_xiaoha_usage_dashboard"].assert_not_called()

    def test_existing_routes_do_not_render_balance(self):
        for baseline in BASELINES:
            for selected, renderer in (("hd_batch", "render_openrouter_feature"),
                                       ("__usage_dashboard__", "render_xiaoha_usage_dashboard")):
                with self.subTest(baseline=baseline, selected=selected):
                    ns = main_namespace(baseline, selected)
                    ns["main"]()
                    ns[renderer].assert_called_once()
                    ns["render_xiaoha_balance_management"].assert_not_called()

    def test_view_gets_only_streamlit_and_lazy_loader_without_fetching_in_wrapper(self):
        view, provider = ModuleType("图片.balance_view"), ModuleType("图片.balance_provider")
        view.render_balance_management = Mock()
        provider.load_balance_snapshot = Mock()
        for baseline in BASELINES:
            with self.subTest(baseline=baseline):
                view.render_balance_management.reset_mock()
                ns = extracted_namespace(baseline, {"render_xiaoha_balance_management"})
                ns["st"] = fake_streamlit()
                with mock_patch.dict("sys.modules", {view.__name__: view, provider.__name__: provider}):
                    ns["render_xiaoha_balance_management"]()
                api, loader = view.render_balance_management.call_args.args
                self.assertEqual(vars(api), {"st": ns["st"]})
                self.assertIs(loader, provider.load_balance_snapshot)
                provider.load_balance_snapshot.assert_not_called()

    def test_patch_refuses_already_patched_baseline(self):
        for baseline in BASELINES:
            with self.subTest(baseline=baseline):
                source = (ROOT / f"{baseline}-patched.py").read_text(encoding="utf-8")
                with self.assertRaises(ValueError):
                    patch(source)


if __name__ == "__main__":
    unittest.main()
