#!/usr/bin/env python3
"""Unit tests for background services status API and ProcessCommand routing."""

import json
import sys
import unittest
from unittest.mock import MagicMock, patch

import tests.conftest
import genserv


class TestServicesStatus(unittest.TestCase):
    """Test suite for get_services_status_json and ProcessCommand routing."""

    def test_services_status_all_running_with_psutil(self):
        """Verify get_services_status_json correctly reports running processes with psutil and active Tailscale."""
        mock_psutil = MagicMock()

        p_genmon = MagicMock()
        p_genmon.info = {
            "pid": 1001,
            "cmdline": ["python3", "/home/pi/genmon/genmon.py"],
            "create_time": 1000.0,
            "cpu_percent": 1.2,
            "memory_info": MagicMock(rss=45 * 1024 * 1024),
        }
        p_genserv = MagicMock()
        p_genserv.info = {
            "pid": 1002,
            "cmdline": ["python3", "/home/pi/genmon/genserv.py"],
            "create_time": 1000.0,
            "cpu_percent": 0.8,
            "memory_info": MagicMock(rss=35 * 1024 * 1024),
        }
        p_webpush = MagicMock()
        p_webpush.info = {
            "pid": 1003,
            "cmdline": ["python3", "/home/pi/genmon/addon/genwebpush.py"],
            "create_time": 1000.0,
            "cpu_percent": 0.3,
            "memory_info": MagicMock(rss=25 * 1024 * 1024),
        }
        mock_psutil.process_iter.return_value = [p_genmon, p_genserv, p_webpush]

        def subp_side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "which tailscale" in cmd_str:
                return b"/usr/bin/tailscale"
            if "tailscale funnel status" in cmd_str:
                return b"Funnel on:\nhttps://mygenmon.ts.net proxy http://127.0.0.1:8000"
            return b""

        with patch.dict(sys.modules, {"psutil": mock_psutil}):
            with patch("subprocess.check_output", side_effect=subp_side_effect):
                data = genserv.get_services_status_json()

        self.assertEqual(data["overall_status"], "NORMAL")
        self.assertGreaterEqual(data["running_count"], 3)
        self.assertEqual(data["failed_count"], 0)

        # Check core service presence
        svc_names = [s["name"] for s in data["services"]]
        self.assertIn("genmon.py", svc_names)
        self.assertIn("genserv.py", svc_names)
        self.assertIn("genwebpush.py", svc_names)

        gm = next(s for s in data["services"] if s["name"] == "genmon.py")
        self.assertEqual(gm["status_code"], "running")
        self.assertEqual(gm["pids"], [1001])
        self.assertEqual(gm["memory_mb"], 45.0)

        # Check Tailscale
        ts = data["tailscale"]
        self.assertTrue(ts["installed"])
        self.assertEqual(ts["status_code"], "active")
        self.assertEqual(ts["url"], "https://mygenmon.ts.net")
        self.assertEqual(ts["target"], "http://127.0.0.1:8000")

    def test_services_status_running_with_pgrep_fallback(self):
        """Verify fallback to pgrep when psutil is not available."""
        def subp_side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "pgrep -f genmon.py" in cmd_str:
                return b"2001\n"
            if "pgrep -f genserv.py" in cmd_str:
                return b"2002\n"
            if "pgrep -f genwebpush.py" in cmd_str:
                return b"2003\n"
            raise Exception("not running")

        with patch.dict(sys.modules, {"psutil": None}):
            with patch("subprocess.check_output", side_effect=subp_side_effect):
                data = genserv.get_services_status_json()

        self.assertEqual(data["overall_status"], "NORMAL")
        self.assertGreaterEqual(data["running_count"], 3)
        gm = next(s for s in data["services"] if s["name"] == "genmon.py")
        self.assertEqual(gm["status_code"], "running")
        self.assertEqual(gm["pids"], [2001])

    def test_services_status_stopped_core(self):
        """Verify stopped core services are flagged as failed with WARNING overall status."""
        mock_psutil = MagicMock()
        mock_psutil.process_iter.return_value = []

        with patch.dict(sys.modules, {"psutil": mock_psutil}):
            with patch("subprocess.check_output", side_effect=Exception("not found")):
                data = genserv.get_services_status_json()

        self.assertEqual(data["overall_status"], "WARNING")
        self.assertGreaterEqual(data["failed_count"], 2)
        gm = next(s for s in data["services"] if s["name"] == "genmon.py")
        self.assertEqual(gm["status_code"], "failed")

    @patch("genserv.get_services_status_json")
    def test_process_command_routing(self, mock_get_status):
        """Verify ProcessCommand correctly routes services_status_json."""
        mock_get_status.return_value = {"overall_status": "NORMAL", "running_count": 2}
        resp = genserv.ProcessCommand("services_status_json")
        parsed = json.loads(resp)
        self.assertEqual(parsed["overall_status"], "NORMAL")
        self.assertEqual(parsed["running_count"], 2)


if __name__ == "__main__":
    unittest.main()
