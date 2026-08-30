#!/usr/bin/env python3
"""Unit tests for GenNotify event callback dispatching and OnSystemHealth."""

import unittest
from unittest.mock import MagicMock, patch

import tests.conftest
from genmonlib.mynotify import GenNotify
from addon.genwebpush import OnSystemHealth


class TestNotifySystemHealth(unittest.TestCase):
    """Test suite for GenNotify error silencing and genwebpush OnSystemHealth."""

    @patch("genmonlib.mynotify.ClientInterface")
    def test_process_event_data_silent_when_unregistered(self, mock_client):
        """Verify ProcessEventData does not log an error if callback is not registered."""
        mock_log = MagicMock()
        notifier = GenNotify(start=False, log=mock_log)
        notifier.LogError = MagicMock()

        # SYSTEMHEALTH is not registered in notifier.Events
        self.assertNotIn("SYSTEMHEALTH", notifier.Events)

        notifier.ProcessEventData("SYSTEMHEALTH", "Degraded", None)

        # Ensure LogError was not called
        notifier.LogError.assert_not_called()

    @patch("genmonlib.mynotify.ClientInterface")
    def test_process_event_data_invokes_registered_callback(self, mock_client):
        """Verify ProcessEventData invokes registered callback properly."""
        mock_callback = MagicMock()
        notifier = GenNotify(start=False, onsystemhealth=mock_callback)

        self.assertIn("SYSTEMHEALTH", notifier.Events)
        notifier.ProcessEventData("SYSTEMHEALTH", "OK", None)

        mock_callback.assert_called_once_with("OK")

    @patch("addon.genwebpush.SendWebPushPayload")
    def test_on_system_health_dispatch(self, mock_send):
        """Verify OnSystemHealth dispatches push payload with correct category."""
        OnSystemHealth("OK")
        mock_send.assert_called_with("Genmon System Health", "System Health: OK", category="info")

        mock_send.reset_mock()
        OnSystemHealth("Communication Lost")
        mock_send.assert_called_with("Genmon System Health", "System Health: Communication Lost", category="warning")


if __name__ == "__main__":
    unittest.main()
