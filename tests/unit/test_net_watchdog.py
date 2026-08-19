#!/usr/bin/env python3
"""Unit test suite for net_watchdog.sh and Genmon web log integration."""

import os
import re
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, mock_open, patch

import tests.conftest
import genserv


class TestNetWatchdog(unittest.TestCase):
    """Test cases for network watchdog script syntax, IP regex, and genserv log endpoints."""

    def test_bash_script_syntax(self) -> None:
        """Validates that net_watchdog.sh contains clean Bash syntax with zero syntax errors."""
        script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "net_watchdog.sh")
        self.assertTrue(os.path.exists(script_path), f"net_watchdog.sh should exist at {script_path}.")

        result = subprocess.run(
            ["bash", "-n", script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(
            result.returncode, 0, f"Bash syntax check failed:\n{result.stderr}"
        )

    def test_ip_regex_validation(self) -> None:
        """Tests the IP address regex validation used by net_watchdog.sh."""
        ip_regex = re.compile(r"^([0-9]{1,3}\.){3}[0-9]{1,3}$")

        # Valid IPv4 Addresses
        self.assertTrue(ip_regex.match("192.168.1.1"))
        self.assertTrue(ip_regex.match("10.0.0.1"))
        self.assertTrue(ip_regex.match("172.16.0.254"))

        # Invalid / Empty Route Table Outputs
        self.assertIsNone(ip_regex.match(""))
        self.assertIsNone(ip_regex.match("default"))
        self.assertIsNone(ip_regex.match("192.168.1"))
        self.assertIsNone(ip_regex.match("invalid_ip"))

    def test_genserv_get_script_logs_includes_watchdog(self) -> None:
        """Tests that genserv.get_script_logs_json() returns net_watchdog_log with severity detection."""
        sample_log = (
            "[2026-08-02 16:15:00] [INFO] Connected to 192.168.1.1 on wlan0.\n"
            "[2026-08-02 16:18:00] [WARN] Failed to ping 192.168.1.1 on wlan0.\n"
            "[2026-08-02 16:21:00] [ERROR] Router unreachable. Initiating reboot.\n"
        )
        with patch("genserv.os.path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=sample_log)):
                logs = genserv.get_script_logs_json()
                self.assertIn("net_watchdog_log", logs)
                self.assertIsNotNone(logs["net_watchdog_log"])
                self.assertTrue(logs["net_watchdog_log"]["has_error"])
                self.assertTrue(logs["net_watchdog_log"]["has_warning"])
                self.assertEqual(len(logs["net_watchdog_log"]["lines"]), 3)

    def test_genserv_clear_script_log_watchdog(self) -> None:
        """Tests that genserv.clear_script_log_json('watchdog') truncates the watchdog log."""
        target_path = "/var/log/net-watchdog.log"
        m_open = mock_open()
        with patch("genserv.HasWriteAccess", return_value=True):
            with patch("genserv.os.path.exists", side_effect=lambda p: p == target_path):
                with patch("builtins.open", m_open):
                    res_str = genserv.clear_script_log_json("watchdog")
                    self.assertIn('"result": "OK"', res_str)
                    m_open.assert_called_with(target_path, "w", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
