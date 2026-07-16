from __future__ import annotations

import unittest
from unittest.mock import patch

from 图片 import openrouter_image_site as site


class SessionState(dict):
    def __getattr__(self, key: str):
        try:
            return self[key]
        except KeyError as exc:
            raise AttributeError(key) from exc

    def __setattr__(self, key: str, value) -> None:
        self[key] = value


class FakeStreamlit:
    def __init__(self, session_state: SessionState) -> None:
        self.session_state = session_state
        self.rerun_called = False

    def button(self, *args, **kwargs) -> bool:
        return False

    def markdown(self, *args, **kwargs) -> None:
        return None

    def caption(self, *args, **kwargs) -> None:
        return None

    def rerun(self) -> None:
        self.rerun_called = True


class XiaohaHistoryLazyLoadingTests(unittest.TestCase):
    def build_state(self) -> SessionState:
        return SessionState(
            auth_username="tester",
            history_panel_expanded={},
            history_visible_counts={},
            history_records_cache={},
            local_history_records={},
        )

    def test_collapsed_history_does_not_query_records(self) -> None:
        state = self.build_state()
        fake_st = FakeStreamlit(state)
        feature = {"key": "amazon_a_plus", "name": "亚马逊A+生成"}

        with (
            patch.object(site, "st", fake_st),
            patch.object(site, "ensure_history_records_loaded") as load_records,
        ):
            site.render_history_records(feature)

        load_records.assert_not_called()

    def test_expanded_history_queries_records(self) -> None:
        state = self.build_state()
        feature = {"key": "amazon_a_plus", "name": "亚马逊A+生成"}
        cache_key = site.get_history_cache_key("tester", feature["key"])
        state.history_panel_expanded[cache_key] = True
        fake_st = FakeStreamlit(state)

        with (
            patch.object(site, "st", fake_st),
            patch.object(site, "ensure_history_records_loaded", return_value=[]) as load_records,
        ):
            site.render_history_records(feature)

        load_records.assert_called_once_with(
            feature["key"],
            "tester",
            cache_key,
            site.HISTORY_PAGE_SIZE,
        )


if __name__ == "__main__":
    unittest.main()
