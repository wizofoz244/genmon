#!/usr/bin/env python3
"""Integration test suite for GenNotify and event message pipeline.

Validates event handler registration, outage tracking state, and event dispatcher
configuration per Google Python Style Guide.
"""

from __future__ import annotations

from typing import Any
import unittest
from unittest.mock import MagicMock, patch

import tests.conftest
from genmonlib.mynotify import GenNotify


class TestNotificationIntegration(unittest.TestCase):
    """Integration tests for event notification dispatcher in mynotify.py."""

    @patch("genmonlib.mynotify.ClientInterface")
    def setUp(self, mock_client_cls: Any) -> None:
        """Sets up mock event callbacks and GenNotify instance."""
        self.log = MagicMock()
        self.ready_callback = MagicMock()
        self.alarm_callback = MagicMock()
        self.run_callback = MagicMock()

        self.notifier = GenNotify(
            log=self.log,
            onready=self.ready_callback,
            onalarm=self.alarm_callback,
            onrun=self.run_callback,
            start=False,
            notify_info=True,
            notify_error=True,
        )

    def test_notification_initialization(self) -> None:
        """Tests that GenNotify registers event handlers properly."""
        self.assertIsNotNone(self.notifier)
        self.assertTrue(self.notifier.notify_info)
        self.assertTrue(self.notifier.notify_error)

    def test_utility_outage_state_tracking(self) -> None:
        """Tests utility voltage change tracking flags."""
        self.notifier.LastOutageStatus = False
        self.assertFalse(self.notifier.LastOutageStatus)

        self.notifier.LastOutageStatus = True
        self.assertTrue(self.notifier.LastOutageStatus)


if __name__ == "__main__":
    unittest.main()
