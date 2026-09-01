#!/usr/bin/env python3
"""Unit tests for GenNotify outage baseline initialization and debouncing.

Verifies that starting or restarting GenNotify with normal utility power
does not trigger spurious "power restored" or "outage" notifications.
"""

import json
import unittest
from unittest.mock import MagicMock, patch

import tests.conftest
from genmonlib.mynotify import GenNotify
from genmonlib.controller import GeneratorController


class TestNotifyOutageStartup(unittest.TestCase):
    """Tests for GenNotify outage and status notification baseline handling."""

    @patch("genmonlib.mynotify.ClientInterface")
    def test_outage_baseline_suppresses_spurious_restoration_on_start(
        self, mock_client: MagicMock
    ) -> None:
        """Verify that starting when utility power is normal does NOT fire onutilitychange."""
        mock_callback = MagicMock()
        notifier = GenNotify(start=False, onutilitychange=mock_callback)

        # Initial state should be uninitialized (None)
        self.assertIsNone(notifier.LastOutageStatus)

        # Mock generator: outage_json reporting normal utility power (not in outage)
        normal_outage_json = json.dumps({
            "Outage": [
                {"Status": "No outage has occurred since program launched."},
                {"System In Outage": "No"},
                {"Utility Voltage": "240 V"},
            ]
        })
        notifier.SendCommand = MagicMock(return_value=normal_outage_json)

        # First poll
        result = notifier.GetOutageState()

        # Should return False (no outage)
        self.assertFalse(result)
        # Internal state should be baseline established as False
        self.assertFalse(notifier.LastOutageStatus)
        # Callback MUST NOT be called (suppressing spurious restoration alert on restart)
        mock_callback.assert_not_called()

        # Second poll with same normal state
        notifier.GetOutageState()
        mock_callback.assert_not_called()

    @patch("genmonlib.mynotify.ClientInterface")
    def test_active_outage_on_startup_is_dispatched(
        self, mock_client: MagicMock
    ) -> None:
        """Verify that starting DURING an active outage correctly triggers the outage alert."""
        mock_callback = MagicMock()
        notifier = GenNotify(start=False, onutilitychange=mock_callback)

        active_outage_json = json.dumps({
            "Outage": [
                {"Status": "System in outage since 2026-09-01 12:00:00"},
                {"System In Outage": "Yes"},
                {"Utility Voltage": "0 V"},
            ]
        })
        notifier.SendCommand = MagicMock(return_value=active_outage_json)

        result = notifier.GetOutageState()

        self.assertTrue(result)
        self.assertTrue(notifier.LastOutageStatus)
        # Must notify user that power is out!
        mock_callback.assert_called_once_with(True)

    @patch("genmonlib.mynotify.ClientInterface")
    def test_outage_and_restoration_lifecycle(
        self, mock_client: MagicMock
    ) -> None:
        """Verify normal lifecycle: startup -> outage occurs -> outage restored."""
        mock_callback = MagicMock()
        notifier = GenNotify(start=False, onutilitychange=mock_callback)

        normal_json = json.dumps({
            "Outage": [
                {"Status": "No outage"},
                {"System In Outage": "No"},
            ]
        })
        outage_json = json.dumps({
            "Outage": [
                {"Status": "Power out"},
                {"System In Outage": "Yes"},
            ]
        })

        # 1. Startup: normal power -> no alert
        notifier.SendCommand = MagicMock(return_value=normal_json)
        notifier.GetOutageState()
        mock_callback.assert_not_called()

        # 2. Outage occurs -> alert dispatched with True
        notifier.SendCommand = MagicMock(return_value=outage_json)
        notifier.GetOutageState()
        mock_callback.assert_called_once_with(True)
        self.assertTrue(notifier.LastOutageStatus)

        # 3. Power restored -> alert dispatched with False
        mock_callback.reset_mock()
        notifier.SendCommand = MagicMock(return_value=normal_json)
        notifier.GetOutageState()
        mock_callback.assert_called_once_with(False)
        self.assertFalse(notifier.LastOutageStatus)

    @patch("genmonlib.mynotify.ClientInterface")
    def test_software_update_and_pi_state_startup_suppression(
        self, mock_client: MagicMock
    ) -> None:
        """Verify software update and pi state baseline suppression on startup."""
        mock_sw = MagicMock()
        mock_pi = MagicMock()
        notifier = GenNotify(
            start=False,
            onsoftwareupdate=mock_sw,
            onpistate=mock_pi,
        )

        monitor_json = json.dumps({
            "Monitor": [
                {
                    "Generator Monitor Stats": [
                        {"Update Available": "No"},
                        {"Monitor Health": "OK"},
                    ]
                },
                {},
                {
                    "Platform Stats": [
                        {"Pi CPU Frequency Throttling": "OK"},
                        {"Pi ARM Frequency Cap": "OK"},
                        {"Pi Undervoltage": "OK"},
                    ]
                },
            ]
        })
        notifier.SendCommand = MagicMock(return_value=monitor_json)

        notifier.GetMonitorState()

        # Neither should fire on initial normal startup
        mock_sw.assert_not_called()
        mock_pi.assert_not_called()
        self.assertFalse(notifier.LastSoftwareUpdateStatus)
        self.assertEqual(notifier.LastPiState, "OK")


class TestControllerOutageDelay(unittest.TestCase):
    """Tests for GeneratorController outage delay debouncing default."""

    def test_default_outage_notice_delay_is_five_seconds(self) -> None:
        """Verify default outage_notice_delay is 5 seconds to debounce transient startup 0V."""
        controller = GeneratorController(log=None)
        self.assertEqual(controller.OutageNoticeDelay, 5)


if __name__ == "__main__":
    unittest.main()
