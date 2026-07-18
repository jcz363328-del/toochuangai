from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from 图片 import openrouter_image_site as site


class XiaohaKeepaliveTests(unittest.TestCase):
    def test_feature_selection_is_persisted_without_manual_rerun(self) -> None:
        fake_streamlit = SimpleNamespace(
            session_state=SimpleNamespace(selected_feature_key="hd_batch"),
            query_params={},
        )

        with patch.object(site, "st", fake_streamlit):
            site.select_feature("outpaint")

        self.assertEqual(fake_streamlit.session_state.selected_feature_key, "outpaint")
        self.assertEqual(fake_streamlit.query_params[site.FEATURE_QUERY_KEY], "outpaint")

    def test_direct_streamlit_launch_enables_long_lived_sessions(self) -> None:
        with (
            patch.object(
                site,
                "load_runtime_settings",
                return_value={"server_address": "0.0.0.0", "server_port": 8501},
            ),
            patch.object(site.os, "execv") as execv,
        ):
            site.relaunch_with_streamlit()

        launch_args = execv.call_args.args[1]
        self.assertEqual(
            launch_args[launch_args.index("--server.websocketPingInterval") + 1],
            "20",
        )
        self.assertEqual(
            launch_args[launch_args.index("--server.disconnectedSessionTTL") + 1],
            "86400",
        )
        self.assertEqual(
            launch_args[launch_args.index("--server.fileWatcherType") + 1],
            "none",
        )

    def test_watchdog_waits_for_repeated_failures_before_restart(self) -> None:
        watchdog_path = Path(site.__file__).with_name("xiaoha_watchdog.ps1")
        watchdog_text = watchdog_path.read_text(encoding="utf-8")

        self.assertIn("[int]$ConsecutiveFailureThreshold = 3", watchdog_text)
        self.assertIn("$consecutiveFailures -ge $failureThreshold", watchdog_text)
        self.assertIn('"--server.disconnectedSessionTTL"', watchdog_text)
        self.assertIn('"86400"', watchdog_text)


if __name__ == "__main__":
    unittest.main()
