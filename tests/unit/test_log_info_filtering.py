#!/usr/bin/env python3
"""Unit tests verifying that [INFO] log entries are never treated as warnings or errors."""

import unittest
from unittest.mock import MagicMock, mock_open, patch

import tests.conftest
import genserv
from addon.genwebpush import OnPiState, OnAlarm


class TestLogInfoFiltering(unittest.TestCase):
    """Test suite for script log severity classification and webpush logging levels."""

    def test_info_log_with_warning_text_not_flagged_as_warning(self):
        """Verify log lines tagged [INFO] containing 'warning' are not marked as has_warning."""
        sample_log = (
            "[2026-08-31 14:22:29] [INFO] Dispatched push payload 'Genmon Software Update' to Lenovo Tab (https://fcm.googleapis.com/fcm/send/eAQK...)\n"
            "[2026-08-31 14:22:29] [INFO] Dispatched push payload 'Genmon System Warning' to Pixel 10 (https://fcm.googleapis.com/fcm/send/dKSH...)\n"
            "[2026-08-31 14:22:29] [INFO] Dispatched push payload 'Genmon System Warning' to MacBook i7 (https://fcm.googleapis.com/fcm/send/fLDA...)\n"
            "[2026-08-31 14:22:30] [INFO] Dispatched push payload 'Genmon System Warning' to iPhone (https://web.push.apple.com/QPh1JsjT03Nl8...)\n"
            "[2026-08-31 14:22:30] [INFO] Dispatched push payload 'Genmon System Warning' to Lenovo Tab (https://fcm.googleapis.com/fcm/send/eAQK...)\n"
        )
        with patch("genserv.os.path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=sample_log)):
                logs = genserv.get_script_logs_json()
                for key in ["genmaint_sync_log", "backup_log", "sdcard_backup_log", "net_watchdog_log", "genwebpush_log"]:
                    if key in logs and logs[key]:
                        self.assertFalse(logs[key]["has_warning"])
                        self.assertFalse(logs[key]["has_error"])

    def test_actual_warning_and_error_lines_still_flagged(self):
        """Verify real [WARN] and [ERROR] entries are correctly identified."""
        sample_log = (
            "[2026-08-30 13:40:00] [INFO] Dispatched push payload 'Genmon System Warning' to Pixel 10\n"
            "[2026-08-30 13:41:00] [WARNING] Network latency high\n"
            "[2026-08-30 13:42:00] [ERROR] Connection refused\n"
        )
        with patch("genserv.os.path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=sample_log)):
                logs = genserv.get_script_logs_json()
                entry = logs.get("net_watchdog_log")
                self.assertIsNotNone(entry)
                self.assertTrue(entry["has_warning"])
                self.assertTrue(entry["has_error"])

    @patch("addon.genwebpush.SendWebPushPayload")
    @patch("addon.genwebpush.console")
    def test_on_pi_state_logs_as_info(self, mock_console, mock_send):
        """Verify OnPiState logs status transitions via console.info, not console.warning."""
        OnPiState(active=True)
        mock_console.info.assert_called()
        mock_console.warning.assert_not_called()

    @patch("addon.genwebpush.SendWebPushPayload")
    @patch("addon.genwebpush.console")
    def test_on_alarm_logs_as_info(self, mock_console, mock_send):
        """Verify OnAlarm logs push handling via console.info, not console.error."""
        OnAlarm(active=True)
        mock_console.info.assert_called()
        mock_console.error.assert_not_called()


if __name__ == "__main__":
    unittest.main()
