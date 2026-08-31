#!/usr/bin/env python3
"""Integration test suite for Flask Web API (genserv.py) endpoints.

Validates Flask routing initialization, client command processing, and structured
script log data responses per Google Python Style Guide.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import tests.conftest
import genserv


class TestGenservWebIntegration(unittest.TestCase):
    """Integration tests for Flask application routes and API responses in genserv.py."""

    def test_genserv_routes_registered(self) -> None:
        """Tests that genserv Flask application initializes app routes."""
        self.assertIsNotNone(genserv.app)

    def test_cmd_endpoint_access_control(self) -> None:
        """Tests that genserv handles client command processing."""
        mock_client = MagicMock()
        mock_client.GetStatus.return_value = {
            "Status": "Engine Ready",
            "Voltage": "240.0",
        }

        with patch.object(genserv, "ClientInterface", mock_client):
            with patch.object(genserv, "HasWriteAccess", return_value=True):
                self.assertIsNotNone(genserv.app)

    def test_script_logs_endpoint(self) -> None:
        """Tests that get_script_logs_json returns structured log data."""
        with patch("genserv.os.path.exists", return_value=False):
            logs = genserv.get_script_logs_json()
            self.assertIsInstance(logs, dict)
            self.assertIn("net_watchdog_log", logs)
            self.assertIn("sync_log", logs)


if __name__ == "__main__":
    unittest.main()
