#!/usr/bin/env python3
"""Unit tests for TLS and Tailscale certificate auto-renewal and regeneration."""

from __future__ import annotations

import datetime
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import tests.conftest
import genserv


class TestCertRenewal(unittest.TestCase):
    """Unit tests for TLS/Tailscale certificate renewal and regeneration."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.orig_config_path = genserv.ConfigFilePath
        self.orig_cert_mode = genserv.CertMode
        genserv.ConfigFilePath = self.temp_dir

    def tearDown(self) -> None:
        genserv.ConfigFilePath = self.orig_config_path
        genserv.CertMode = self.orig_cert_mode
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_tailscale_fqdn_detection(self) -> None:
        """Tests that _get_tailscale_fqdn correctly parses JSON from tailscale status."""
        mock_output = json.dumps({
            "Self": {"DNSName": "my-generator.tailnet-xyz.ts.net."}
        })
        with patch("shutil.which", return_value="/usr/bin/tailscale"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout=mock_output, stderr="")
                fqdn = genserv._get_tailscale_fqdn()
                self.assertEqual(fqdn, "my-generator.tailnet-xyz.ts.net")

    def test_tailscale_fqdn_missing_cli(self) -> None:
        """Tests that _get_tailscale_fqdn returns empty string when tailscale is unavailable."""
        with patch("shutil.which", return_value=None):
            with patch("os.path.isfile", return_value=False):
                fqdn = genserv._get_tailscale_fqdn()
                self.assertEqual(fqdn, "")

    def test_ensure_tailscale_cert_invocation(self) -> None:
        """Tests that _ensure_tailscale_cert invokes 'tailscale cert' command properly."""
        with patch.object(genserv, "_get_tailscale_fqdn", return_value="genmon.ts.net"):
            with patch("shutil.which", return_value="/usr/bin/tailscale"):
                with patch("subprocess.run") as mock_run:
                    mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
                    with patch("os.chmod"):
                        crt_path = os.path.join(self.temp_dir, "tailscale.crt")
                        key_path = os.path.join(self.temp_dir, "tailscale.key")
                        with open(crt_path, "w") as f:
                            f.write("mock-cert")
                        with open(key_path, "w") as f:
                            f.write("mock-key")

                        c, k = genserv._ensure_tailscale_cert(self.temp_dir, force=True)
                        self.assertEqual(c, crt_path)
                        self.assertEqual(k, key_path)
                        mock_run.assert_called_once()
                        cmd_args = mock_run.call_args[0][0]
                        self.assertIn("cert", cmd_args)
                        self.assertIn("genmon.ts.net", cmd_args)

    def test_get_cert_info_selfsigned(self) -> None:
        """Tests that _get_cert_info returns correct metadata for selfsigned mode."""
        genserv.CertMode = "selfsigned"
        genserv.generate_persistent_selfsigned(self.temp_dir)
        info_json = genserv._get_cert_info()
        info = json.loads(info_json)
        self.assertEqual(info.get("mode"), "selfsigned")
        self.assertTrue(info.get("can_renew"))
        self.assertIn("srv_expiry", info)
        self.assertGreater(info.get("days_remaining", 0), 300)

    def test_get_cert_info_localca(self) -> None:
        """Tests that _get_cert_info returns correct metadata for localca mode."""
        genserv.CertMode = "localca"
        ca_cert, ca_key = genserv.generate_local_ca(self.temp_dir)
        genserv.generate_server_cert(ca_cert, ca_key, self.temp_dir)
        info_json = genserv._get_cert_info()
        info = json.loads(info_json)
        self.assertEqual(info.get("mode"), "localca")
        self.assertTrue(info.get("can_renew"))
        self.assertIn("ca_created", info)
        self.assertIn("srv_expiry", info)
        self.assertGreater(info.get("days_remaining", 0), 300)

    def test_renew_or_regenerate_localca(self) -> None:
        """Tests that renew_or_regenerate_cert regenerates localca server certificate."""
        genserv.CertMode = "localca"
        ok, msg, info = genserv.renew_or_regenerate_cert(force=True)
        self.assertTrue(ok)
        self.assertIn("Local CA server certificate regenerated", msg)
        self.assertTrue(os.path.isfile(os.path.join(self.temp_dir, "server.crt")))
        self.assertTrue(os.path.isfile(os.path.join(self.temp_dir, "server.key")))

    def test_renew_or_regenerate_tailscale(self) -> None:
        """Tests renew_or_regenerate_cert in tailscale mode."""
        genserv.CertMode = "tailscale"
        crt_path = os.path.join(self.temp_dir, "tailscale.crt")
        key_path = os.path.join(self.temp_dir, "tailscale.key")
        with open(crt_path, "w") as f:
            f.write("mock-ts-cert")
        with open(key_path, "w") as f:
            f.write("mock-ts-key")

        with patch.object(genserv, "_ensure_tailscale_cert", return_value=(crt_path, key_path)):
            ok, msg, info = genserv.renew_or_regenerate_cert(force=True)
            self.assertTrue(ok)
            self.assertEqual(info.get("mode"), "tailscale")

    def test_routes_registered_in_genserv(self) -> None:
        """Tests that genserv registers cert regeneration and status REST routes."""
        self.assertTrue(hasattr(genserv, "security_cert_regenerate"))
        self.assertTrue(hasattr(genserv, "security_cert_info_endpoint"))
        self.assertTrue(hasattr(genserv, "StartCertRenewalWatchdog"))

    def test_check_and_alert_cert_expiration_under_3_days(self) -> None:
        """Tests that _check_and_alert_cert_expiration triggers push and email alerts when <= 3 days left."""
        genserv._last_cert_expiry_alert_date = None
        mock_info = {
            "mode": "tailscale",
            "days_remaining": 3,
            "srv_expiry": "2026-08-21",
        }
        with patch("addon.genwebpush.SendWebPushPayload") as mock_push:
            with patch("genmonlib.mymail.MyMail") as mock_mail_cls:
                mock_mail_inst = MagicMock()
                mock_mail_cls.return_value = mock_mail_inst
                genserv._check_and_alert_cert_expiration(mock_info)
                mock_push.assert_called_once()
                self.assertIn("TLS Certificate Expiring Soon", mock_push.call_args[1]["title"])
                mock_mail_inst.sendEmail.assert_called_once()
                self.assertIn("TLS Certificate Expiring", mock_mail_inst.sendEmail.call_args[0][0])

    def test_check_and_alert_cert_expiration_over_3_days_no_alert(self) -> None:
        """Tests that _check_and_alert_cert_expiration does not trigger alerts when > 3 days left."""
        genserv._last_cert_expiry_alert_date = None
        mock_info = {
            "mode": "localca",
            "days_remaining": 30,
            "srv_expiry": "2026-09-17",
        }
        with patch("addon.genwebpush.SendWebPushPayload") as mock_push:
            with patch("genmonlib.mymail.MyMail") as mock_mail_cls:
                genserv._check_and_alert_cert_expiration(mock_info)
                mock_push.assert_not_called()
                mock_mail_cls.assert_not_called()


if __name__ == "__main__":
    unittest.main()
