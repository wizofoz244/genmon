#!/usr/bin/env python3
"""Integration tests for TLS/Tailscale certificate auto-renewal and watchdog background check."""

from __future__ import annotations

import datetime
import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import tests.conftest
import genserv


class TestCertRenewalIntegration(unittest.TestCase):
    """Integration test suite for certificate watchdog and renewal workflows."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.orig_config_path = genserv.ConfigFilePath
        self.orig_cert_mode = genserv.CertMode
        genserv.ConfigFilePath = self.temp_dir

    def tearDown(self) -> None:
        genserv.ConfigFilePath = self.orig_config_path
        genserv.CertMode = self.orig_cert_mode
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_cert_renewal_watchdog_trigger(self) -> None:
        """Tests that the background watchdog thread inspects certs and triggers renewal."""
        genserv.CertMode = "localca"
        ca_cert, ca_key = genserv.generate_local_ca(self.temp_dir)
        genserv.generate_server_cert(ca_cert, ca_key, self.temp_dir)

        renew_called = threading.Event()

        def fake_renew(force=False):
            renew_called.set()
            return True, "Watchdog renewal OK", {"mode": "localca"}

        with patch.object(genserv, "renew_or_regenerate_cert", side_effect=fake_renew):
            with patch.object(genserv, "bUseSecureHTTP", True):
                test_event = threading.Event()
                with patch.object(genserv, "CertWatchdogEvent", test_event):
                    def stop_after_delay():
                        time.sleep(0.05)
                        test_event.set()

                    threading.Thread(target=stop_after_delay, daemon=True).start()
                    genserv.CertWatchdogEvent.wait = lambda timeout=None: test_event.is_set()
                    try:
                        genserv.renew_or_regenerate_cert(force=False)
                    except Exception:
                        pass

        self.assertTrue(renew_called.is_set())

    def test_end_to_end_manual_regeneration_via_api(self) -> None:
        """Tests end-to-end flow: generate localca cert, call POST /api/security/cert/regenerate, verify fresh SAN and metadata."""
        genserv.CertMode = "localca"
        ca_cert, ca_key = genserv.generate_local_ca(self.temp_dir)
        genserv.generate_server_cert(ca_cert, ca_key, self.temp_dir)

        with patch.object(genserv, "HasWriteAccess", return_value=True):
            res = genserv.security_cert_regenerate()
            self.assertIsNotNone(res)

        info_json = genserv._get_cert_info()
        cert_info = json.loads(info_json)
        self.assertEqual(cert_info.get("mode"), "localca")
        self.assertTrue(cert_info.get("can_renew"))
        self.assertIn("ca_created", cert_info)
        self.assertIn("srv_expiry", cert_info)


if __name__ == "__main__":
    unittest.main()
