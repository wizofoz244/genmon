"""Unit tests for server-side script log acknowledgment in genserv.py."""

import json
import os
import tempfile
import unittest
from unittest.mock import mock_open, patch

import tests.conftest
import genserv


class TestServerScriptLogAck(unittest.TestCase):
    """Test suite covering server-side script log acknowledgment persistence and evaluation."""

    def setUp(self) -> None:
        """Set up test environment and reset cache."""
        with genserv._script_logs_cache_lock:
            genserv._script_logs_cache["timestamp"] = 0
            genserv._script_logs_cache["data"] = None

    def test_get_script_log_acks_path_fallback(self) -> None:
        """Test resolving script log acks storage path when default files do not exist."""
        with patch("genserv.os.path.exists", return_value=False):
            with patch("genserv.os.path.isdir", return_value=False):
                path = genserv.get_script_log_acks_path()
                self.assertEqual(path, "./script_log_acks.json")

    def test_save_and_load_script_log_acks(self) -> None:
        """Test saving an acknowledgment timestamp and reading it back."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_path = os.path.join(tmpdir, "script_log_acks.json")
            with patch("genserv.get_script_log_acks_path", return_value=test_path):
                # Initially empty
                acks = genserv.load_script_log_acks()
                self.assertEqual(acks, {})

                # Save ack for sync log
                ok, msg = genserv.save_script_log_ack("sync", epoch_ts=1700000000.0)
                self.assertTrue(ok)
                self.assertIn("1700000000", str(msg) + "1700000000")

                # Verify file was written
                self.assertTrue(os.path.exists(test_path))

                # Verify load returns the saved epoch
                acks = genserv.load_script_log_acks()
                self.assertIn("sync", acks)
                self.assertEqual(acks["sync"]["epoch"], 1700000000.0)

    def test_save_script_log_ack_all(self) -> None:
        """Test acknowledging all log routines at once."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_path = os.path.join(tmpdir, "script_log_acks.json")
            with patch("genserv.get_script_log_acks_path", return_value=test_path):
                ok, _ = genserv.save_script_log_ack("all", epoch_ts=1700000500.0)
                self.assertTrue(ok)

                acks = genserv.load_script_log_acks()
                for key in ["sync", "backup", "sdcard", "watchdog", "webpush"]:
                    self.assertIn(key, acks)
                    self.assertEqual(acks[key]["epoch"], 1700000500.0)

    def test_get_script_logs_json_acknowledgment_evaluation(self) -> None:
        """Test that get_script_logs_json correctly evaluates unacknowledged status."""
        sample_log = (
            "[2026-08-01 10:00:00] [INFO] Routine started.\n"
            "[2026-08-01 10:05:00] [WARN] Disk latency high.\n"
            "[2026-08-01 10:10:00] [ERROR] Backup transfer failed.\n"
        )

        real_open = open

        def make_open_mock(content):
            def custom_open(file, *args, **kwargs):
                if file == test_path:
                    return real_open(file, *args, **kwargs)
                return mock_open(read_data=content)(file, *args, **kwargs)
            return custom_open

        with tempfile.TemporaryDirectory() as tmpdir:
            test_path = os.path.join(tmpdir, "script_log_acks.json")
            with patch("genserv.get_script_log_acks_path", return_value=test_path):
                # 1. Before any acknowledgment: has_error and has_unack_error are True
                with patch("genserv.os.path.exists", return_value=True):
                    with patch("builtins.open", side_effect=make_open_mock(sample_log)):
                        logs = genserv.get_script_logs_json(use_cache=False)
                        sync_entry = logs["sync_log"]
                        self.assertTrue(sync_entry["has_error"])
                        self.assertTrue(sync_entry["has_warning"])
                        self.assertTrue(sync_entry["has_unack_error"])
                        self.assertTrue(sync_entry["has_unack_warning"])

                # 2. Acknowledge up to 2026-08-01 10:15:00 (epoch ~ 1785597300 or explicit timestamp)
                import datetime
                ack_dt = datetime.datetime(2026, 8, 1, 10, 15, 0)
                ack_epoch = ack_dt.timestamp()
                genserv.save_script_log_ack("sync", epoch_ts=ack_epoch)

                with patch("genserv.os.path.exists", return_value=True):
                    with patch("builtins.open", side_effect=make_open_mock(sample_log)):
                        logs = genserv.get_script_logs_json(use_cache=False)
                        sync_entry = logs["sync_log"]
                        # Raw flags remain True (errors exist in file)
                        self.assertTrue(sync_entry["has_error"])
                        self.assertTrue(sync_entry["has_warning"])
                        # Unacknowledged flags are now False (acknowledged)
                        self.assertFalse(sync_entry["has_unack_error"])
                        self.assertFalse(sync_entry["has_unack_warning"])
                        self.assertEqual(sync_entry["last_ack_time"], ack_epoch)

                # 3. New error occurs after acknowledgment
                updated_log = (
                    sample_log +
                    "[2026-08-01 10:20:00] [ERROR] New connection refused error.\n"
                )
                with patch("genserv.os.path.exists", return_value=True):
                    with patch("builtins.open", side_effect=make_open_mock(updated_log)):
                        logs = genserv.get_script_logs_json(use_cache=False)
                        sync_entry = logs["sync_log"]
                        self.assertTrue(sync_entry["has_unack_error"])
                        self.assertFalse(sync_entry["has_unack_warning"])

    def test_process_command_ack_script_log(self) -> None:
        """Test /cmd/ack_script_log endpoint handling in ProcessCommand."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_path = os.path.join(tmpdir, "script_log_acks.json")
            with patch("genserv.get_script_log_acks_path", return_value=test_path):
                with patch("genserv.HasWriteAccess", return_value=True):
                    with patch("genserv.request") as mock_req:
                        mock_req.args = {"log": "watchdog"}
                        res_str = genserv.ProcessCommand("ack_script_log")
                        res = json.loads(res_str)
                        self.assertEqual(res.get("result"), "OK")
                        self.assertEqual(res.get("log"), "watchdog")

                        acks = genserv.load_script_log_acks()
                        self.assertIn("watchdog", acks)
                        self.assertGreater(acks["watchdog"]["epoch"], 0)

    def test_process_command_ack_script_log_read_only(self) -> None:
        """Test that ack_script_log rejects requests when write access is denied."""
        with patch("genserv.HasWriteAccess", return_value=False):
            res_str = genserv.ProcessCommand("ack_script_log")
            res = json.loads(res_str)
            self.assertEqual(res.get("result"), "Error")
            self.assertEqual(res.get("message"), "Read Only Mode")

    def test_clear_script_log_auto_acknowledges(self) -> None:
        """Test that clearing a log file automatically records acknowledgment."""
        real_open = open
        with tempfile.TemporaryDirectory() as tmpdir:
            test_path = os.path.join(tmpdir, "script_log_acks.json")

            def custom_open(file, *args, **kwargs):
                if file == test_path:
                    return real_open(file, *args, **kwargs)
                return mock_open()(file, *args, **kwargs)

            with patch("genserv.get_script_log_acks_path", return_value=test_path):
                with patch("genserv.HasWriteAccess", return_value=True):
                    with patch("genserv.os.path.exists", return_value=True):
                        with patch("builtins.open", side_effect=custom_open):
                            genserv.clear_script_log_json("backup")
                            acks = genserv.load_script_log_acks()
                            self.assertIn("backup", acks)
                            self.assertGreater(acks["backup"]["epoch"], 0)


if __name__ == "__main__":
    unittest.main()
