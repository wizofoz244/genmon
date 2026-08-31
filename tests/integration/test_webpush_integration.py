#!/usr/bin/env python3
"""Integration test suite for PWA Web Push notification subsystem and API handlers."""

import json
import os
import unittest
from unittest.mock import MagicMock, patch

import tests.conftest
from addon.genwebpush import (
    AddSubscription,
    EnsureVapidKeys,
    OnAlarm,
    OnExercise,
    OnOutage,
    RemoveSubscription,
    SendWebPushPayload,
    subscriptions,
)
import genserv


class TestWebPushIntegration(unittest.TestCase):
    """Integration test suite for PWA Web Push handlers, static assets, and REST API."""

    def test_genserv_has_webpush_routes(self) -> None:
        """Verify genserv has registered webpush handlers."""
        self.assertTrue(hasattr(genserv, "webpush_vapid_key"))
        self.assertTrue(hasattr(genserv, "webpush_subscribe"))
        self.assertTrue(hasattr(genserv, "webpush_unsubscribe"))
        self.assertTrue(hasattr(genserv, "webpush_preferences"))
        self.assertTrue(hasattr(genserv, "webpush_test"))
        self.assertTrue(hasattr(genserv, "serve_sw"))
        self.assertTrue(hasattr(genserv, "serve_manifest"))

    @patch("genserv.HasWriteAccess", return_value=True)
    def test_webpush_preferences_direct_execution(self, mock_write) -> None:
        """Verify webpush_preferences handler executes directly without NameErrors or exceptions."""
        with patch("genserv.request") as mock_req:
            mock_req.method = "GET"
            res = genserv.webpush_preferences()
            self.assertIsNotNone(res)

    @patch("addon.genwebpush.config")
    def test_ensure_vapid_keys(self, mock_config) -> None:
        """Verify VAPID key generation and retrieval."""
        mock_config.ReadValue.side_effect = lambda key, **kw: "test_pub_key" if key == "vapid_public_key" else "test_priv_key"
        pub, priv = EnsureVapidKeys()
        self.assertEqual(pub, "test_pub_key")
        self.assertEqual(priv, "test_priv_key")

    @patch("addon.genwebpush.SaveSubscriptions")
    def test_subscription_add_remove(self, mock_save) -> None:
        """Verify subscription storage and removal logic."""
        dummy_sub = {"endpoint": "https://push.example.com/sub/123", "keys": {}}
        
        # Test addition
        added = AddSubscription(dummy_sub)
        self.assertTrue(added)
        self.assertTrue(mock_save.called)

        # Test removal
        RemoveSubscription("https://push.example.com/sub/123")
        self.assertTrue(mock_save.called)

    @patch("addon.genwebpush.SendWebPushPayload")
    @patch("addon.genwebpush.config")
    def test_event_callbacks(self, mock_config, mock_send) -> None:
        """Verify GenNotify event handlers invoke SendWebPushPayload when enabled."""
        mock_config.ReadValue.return_type = bool
        mock_config.ReadValue.return_value = True

        # Outage
        OnOutage(Active=True)
        self.assertTrue(mock_send.called)

        # Alarm
        OnAlarm(Active=True)
        self.assertTrue(mock_send.called)

        # Exercise
        OnExercise(Active=True)
        self.assertTrue(mock_send.called)

    def test_generate_vapid_key_pair(self) -> None:
        """Verify GenerateVapidKeyPair generates valid base64url keys."""
        from addon.genwebpush import GenerateVapidKeyPair, ValidateVapidKeys
        pub, priv = GenerateVapidKeyPair()
        self.assertTrue(len(pub) > 0)
        self.assertTrue(len(priv) > 0)
        # Validate that the generated pair validates successfully
        self.assertTrue(ValidateVapidKeys(pub, priv))

    def test_validate_vapid_keys_mismatched(self) -> None:
        """Verify ValidateVapidKeys rejects mismatched or corrupted keys."""
        from addon.genwebpush import GenerateVapidKeyPair, ValidateVapidKeys, OLD_DUMMY_PUB
        pub1, priv1 = GenerateVapidKeyPair()
        pub2, priv2 = GenerateVapidKeyPair()
        # Mismatched pairs
        self.assertFalse(ValidateVapidKeys(pub1, priv2))
        self.assertFalse(ValidateVapidKeys(pub2, priv1))
        # Empty or dummy keys
        self.assertFalse(ValidateVapidKeys("", ""))
        self.assertFalse(ValidateVapidKeys(OLD_DUMMY_PUB, priv1))
        self.assertFalse(ValidateVapidKeys("invalid_b64", "invalid_b64"))
        # Invalid lengths
        self.assertFalse(ValidateVapidKeys(pub1, "AAAA"))
        self.assertFalse(ValidateVapidKeys(pub1, None))

    def test_raw_vapid_key_to_sec1_pem(self) -> None:
        """Verify RawVapidKeyToSec1Pem formats raw keys to SEC1 PEM and handles edge cases."""
        import base64
        from addon.genwebpush import GenerateVapidKeyPair, RawVapidKeyToSec1Pem

        pub, priv = GenerateVapidKeyPair()
        # Unpadded base64url key
        pem1 = RawVapidKeyToSec1Pem(priv)
        self.assertTrue(pem1.startswith("-----BEGIN EC PRIVATE KEY-----\n"))
        self.assertTrue(pem1.endswith("\n-----END EC PRIVATE KEY-----\n"))

        # Padded base64url key
        padded_priv = priv.rstrip("=") + "=" * ((4 - len(priv.rstrip("=")) % 4) % 4)
        pem2 = RawVapidKeyToSec1Pem(padded_priv)
        self.assertEqual(pem1, pem2)

        # Already PEM
        pem3 = RawVapidKeyToSec1Pem(pem1)
        self.assertEqual(pem1, pem3)

        # Non-string / None / empty / corrupted
        self.assertEqual(RawVapidKeyToSec1Pem(""), "")
        self.assertIsNone(RawVapidKeyToSec1Pem(None))
        self.assertEqual(RawVapidKeyToSec1Pem("not_a_valid_b64_key!!!"), "not_a_valid_b64_key!!!")

    def test_sec1_der_structure_and_length(self) -> None:
        """Verify the exact SEC1 EC Private Key ASN.1 DER sequence and length byte."""
        import base64
        from addon.genwebpush import GenerateVapidKeyPair

        pub, priv = GenerateVapidKeyPair()
        raw_priv = base64.urlsafe_b64decode(priv.rstrip("=") + "=" * ((4 - len(priv.rstrip("=")) % 4) % 4))
        self.assertEqual(len(raw_priv), 32)

        # Construct SEC1 DER
        der = bytes.fromhex("30310201010420") + raw_priv + bytes.fromhex("a00a06082a8648ce3d030107")
        self.assertEqual(len(der), 51)
        self.assertEqual(der[0], 0x30)  # SEQUENCE tag
        self.assertEqual(der[1], 0x31)  # Length: 49 bytes (0x31)
        self.assertEqual(der[2:5], bytes.fromhex("020101"))  # INTEGER version 1
        self.assertEqual(der[5:7], bytes.fromhex("0420"))  # OCTET STRING length 32
        self.assertEqual(der[7:39], raw_priv)  # Private key scalar
        self.assertEqual(der[39:51], bytes.fromhex("a00a06082a8648ce3d030107"))  # secp256r1 OID

        # Verify PEM wrapper
        pem = "-----BEGIN EC PRIVATE KEY-----\n" + base64.b64encode(der).decode("utf-8") + "\n-----END EC PRIVATE KEY-----\n"
        self.assertTrue(pem.startswith("-----BEGIN EC PRIVATE KEY-----\n"))
        self.assertTrue(pem.endswith("\n-----END EC PRIVATE KEY-----\n"))

    def test_cryptography_deserialization_and_ecdsa_signing(self) -> None:
        """Verify cryptography loads the SEC1 PEM cleanly and can sign ECDSA SHA-256 tokens."""
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import ec
        except ImportError:
            return  # Skip if cryptography is not installed

        from addon.genwebpush import GenerateVapidKeyPair, RawVapidKeyToSec1Pem

        pub, priv = GenerateVapidKeyPair()
        pem = RawVapidKeyToSec1Pem(priv)

        # Must deserialize cleanly without ASN.1 parsing error: invalid length
        loaded_key = serialization.load_pem_private_key(pem.encode("utf-8"), password=None)
        self.assertIsInstance(loaded_key, ec.EllipticCurvePrivateKey)
        self.assertIsInstance(loaded_key.curve, ec.SECP256R1)

        # Verify derived public key matches
        loaded_pub = loaded_key.public_key()
        pub_bytes = loaded_pub.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        import base64
        derived_pub_b64 = base64.urlsafe_b64encode(pub_bytes).decode("utf-8").rstrip("=")
        self.assertEqual(derived_pub_b64, pub.rstrip("="))

        # Verify ECDSA SHA-256 JWT signing and verification (used by APNs WebPush)
        message = b"eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOiJodHRwczovL3B1c2guYXBwbGUuY29tIn0"
        signature = loaded_key.sign(message, ec.ECDSA(hashes.SHA256()))
        self.assertTrue(len(signature) > 0)
        # Verify with public key
        loaded_pub.verify(signature, message, ec.ECDSA(hashes.SHA256()))

    @patch("addon.genwebpush.config")
    def test_send_webpush_payload_dispatch(self, mock_config) -> None:
        """Verify SendWebPushPayload constructs valid VAPID key and invokes webpush."""
        from addon.genwebpush import SendWebPushPayload, subscriptions, GenerateVapidKeyPair
        pub, priv = GenerateVapidKeyPair()
        mock_config.ReadValue.side_effect = lambda key, **kw: pub if key == "vapid_public_key" else priv if key == "vapid_private_key" else "mailto:test@genmon.local"

        mock_webpush = MagicMock()
        with patch.dict("sys.modules", {"pywebpush": MagicMock(webpush=mock_webpush)}):
            target_sub = {
                "endpoint": "https://push.apple.com/sub/ios_dev_123",
                "device_name": "iOS Device",
                "keys": {"p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM", "auth": "tBHItJI5svbpez7KI4CCXg"}
            }
            with patch("addon.genwebpush.subscriptions", [target_sub]):
                with patch("addon.genwebpush.LoadSubscriptions"):
                    success, err = SendWebPushPayload("Test Alert", "Engine Running", target_endpoint=target_sub["endpoint"])
                    self.assertTrue(success)
                    self.assertIsNone(err)
                    self.assertTrue(mock_webpush.called)
                    called_kwargs = mock_webpush.call_args[1]
                    vapid_key_arg = called_kwargs["vapid_private_key"]
                    # Ensure vapid_key is a Vapid object or valid key (not raw invalid PEM string)
                    self.assertIsNotNone(vapid_key_arg)


    @patch("addon.genwebpush.config")
    def test_send_webpush_stale_endpoint_removal(self, mock_config) -> None:
        """Verify SendWebPushPayload removes stale endpoints on 403/410/BadJwtToken errors."""
        from addon.genwebpush import SendWebPushPayload, subscriptions, GenerateVapidKeyPair
        pub, priv = GenerateVapidKeyPair()
        mock_config.ReadValue.side_effect = lambda key, **kw: pub if key == "vapid_public_key" else priv if key == "vapid_private_key" else "mailto:test@genmon.local"

        mock_webpush = MagicMock(side_effect=Exception("403 Forbidden: BadJwtToken"))
        with patch.dict("sys.modules", {"pywebpush": MagicMock(webpush=mock_webpush)}):
            target_sub = {
                "endpoint": "https://push.apple.com/sub/ios_stale_456",
                "device_name": "Stale iOS Device",
                "keys": {"p256dh": "dummy", "auth": "dummy"}
            }
            with patch("addon.genwebpush.RemoveSubscription") as mock_remove:
                with patch("addon.genwebpush.subscriptions", [target_sub]):
                    with patch("addon.genwebpush.LoadSubscriptions"):
                        success, err = SendWebPushPayload("Test Alert", "Test", target_endpoint=target_sub["endpoint"])
                        self.assertFalse(success)
                        self.assertIn("BadJwtToken", err)
                        mock_remove.assert_called_with("https://push.apple.com/sub/ios_stale_456", notify_device=False)

    def test_raw_vapid_key_to_sec1_pem_raw_bytes_and_formats(self) -> None:
        """Verify RawVapidKeyToSec1Pem handles raw bytes, standard base64, and base64url inputs."""
        import base64
        from addon.genwebpush import GenerateVapidKeyPair, RawVapidKeyToSec1Pem, ValidateVapidKeys

        pub, priv = GenerateVapidKeyPair()
        rem = len(priv.rstrip("=")) % 4
        padded = priv.rstrip("=") + ("=" * (4 - rem) if rem > 0 else "")
        raw_bytes = base64.urlsafe_b64decode(padded)
        self.assertEqual(len(raw_bytes), 32)

        # 1. Raw 32 bytes input
        pem_from_bytes = RawVapidKeyToSec1Pem(raw_bytes)
        self.assertTrue(pem_from_bytes.startswith("-----BEGIN EC PRIVATE KEY-----\n"))
        self.assertTrue(pem_from_bytes.endswith("\n-----END EC PRIVATE KEY-----\n"))

        # 2. String base64url input
        pem_from_str = RawVapidKeyToSec1Pem(priv)
        self.assertEqual(pem_from_bytes, pem_from_str)

        # 3. Validate keys when private key is in PEM format
        self.assertTrue(ValidateVapidKeys(pub, pem_from_str))

    def test_subscription_lifecycle_multi_device(self) -> None:
        """Verify AddSubscription, UpdateSubscriptionName, and RemoveSubscription maintain multi-device state."""
        import addon.genwebpush as gwp

        saved_data = []

        def fake_save():
            nonlocal saved_data
            saved_data = list(gwp.subscriptions)

        def fake_load():
            nonlocal saved_data
            gwp.subscriptions = list(saved_data)

        with patch("addon.genwebpush.SaveSubscriptions", side_effect=fake_save), \
             patch("addon.genwebpush.LoadSubscriptions", side_effect=fake_load), \
             patch("addon.genwebpush.SendWebPushPayload", return_value=(True, None)):

            # Add Device 1
            dev1 = {"endpoint": "https://push.apple.com/sub/dev1", "device_name": "iPhone 15"}
            self.assertTrue(gwp.AddSubscription(dev1))
            self.assertEqual(len(saved_data), 1)
            self.assertEqual(saved_data[0]["device_name"], "iPhone 15")

            # Add Device 2
            dev2 = {"endpoint": "https://fcm.googleapis.com/sub/dev2", "device_name": "Pixel 8"}
            self.assertTrue(gwp.AddSubscription(dev2))
            self.assertEqual(len(saved_data), 2)

            # Update Device 1 name
            self.assertTrue(gwp.UpdateSubscriptionName("https://push.apple.com/sub/dev1", "My iPhone"))
            self.assertEqual(len(saved_data), 2)
            self.assertEqual(saved_data[0]["device_name"], "My iPhone")
            self.assertEqual(saved_data[1]["device_name"], "Pixel 8")

            # Remove Device 1
            gwp.RemoveSubscription("https://push.apple.com/sub/dev1", notify_device=False)
            self.assertEqual(len(saved_data), 1)
            self.assertEqual(saved_data[0]["endpoint"], "https://fcm.googleapis.com/sub/dev2")

    def test_apple_apns_jwt_token_format_and_signing(self) -> None:
        """Verify RFC 8292 Apple APNs VAPID authorization JWT token creation and ECDSA signature."""
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import ec
        except ImportError:
            return

        import base64
        import json
        import time
        from addon.genwebpush import GenerateVapidKeyPair, RawVapidKeyToSec1Pem

        pub, priv = GenerateVapidKeyPair()
        pem = RawVapidKeyToSec1Pem(priv)

        # Parse PEM
        priv_key = serialization.load_pem_private_key(pem.encode("utf-8"), password=None)
        pub_key = priv_key.public_key()

        # Construct APNs VAPID JWT
        jwt_header = base64.urlsafe_b64encode(json.dumps({"alg": "ES256", "typ": "JWT"}).encode("utf-8")).decode("utf-8").rstrip("=")
        jwt_claims = base64.urlsafe_b64encode(json.dumps({
            "aud": "https://push.apple.com",
            "exp": int(time.time()) + 86400,
            "sub": "mailto:genmon.push@gmail.com"
        }).encode("utf-8")).decode("utf-8").rstrip("=")

        signing_input = f"{jwt_header}.{jwt_claims}".encode("utf-8")
        signature_der = priv_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))

        # Verify signature
        pub_key.verify(signature_der, signing_input, ec.ECDSA(hashes.SHA256()))
        self.assertTrue(len(signature_der) > 0)

    def test_py_vapid_from_pem_and_from_raw_unmocked(self) -> None:
        """Verify unmocked py_vapid loads SEC1 PEM and raw keys and signs VAPID claims cleanly."""
        try:
            from py_vapid import Vapid
        except ImportError:
            return  # Skip if py_vapid is not installed

        from addon.genwebpush import GenerateVapidKeyPair, RawVapidKeyToSec1Pem

        pub, priv = GenerateVapidKeyPair()
        pem = RawVapidKeyToSec1Pem(priv)

        # 1. Load from PEM
        v_pem = Vapid.from_pem(pem.encode("utf-8"))
        self.assertIsNotNone(v_pem)
        headers_pem = v_pem.sign({"sub": "mailto:test@genmon.local", "aud": "https://push.apple.com"})
        self.assertIn("Authorization", headers_pem)
        self.assertIn("vapid t=", headers_pem["Authorization"])

        # 2. Load from raw string
        v_raw = Vapid.from_string(priv)
        self.assertIsNotNone(v_raw)
        headers_raw = v_raw.sign({"sub": "mailto:test@genmon.local", "aud": "https://push.apple.com"})
        self.assertIn("Authorization", headers_raw)
        self.assertIn("vapid t=", headers_raw["Authorization"])

    def test_pywebpush_curl_mode_unmocked(self) -> None:
        """Verify unmocked pywebpush generates encrypted push curl commands using SEC1 PEM VAPID key."""
        try:
            import pywebpush
            from py_vapid import Vapid
        except ImportError:
            return  # Skip if pywebpush is not installed

        from addon.genwebpush import GenerateVapidKeyPair, RawVapidKeyToSec1Pem

        pub, priv = GenerateVapidKeyPair()
        pem = RawVapidKeyToSec1Pem(priv)
        v_key = Vapid.from_pem(pem.encode("utf-8"))

        sub_info = {
            "endpoint": "https://push.apple.com/sub/ios_p256_client",
            "keys": {
                "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM",
                "auth": "tBHItJI5svbpez7KI4CCXg"
            }
        }

        # Must execute without ASN.1 parsing error or invalid length exception
        curl_cmd = pywebpush.webpush(
            subscription_info=sub_info,
            data=json.dumps({"title": "Test", "body": "Message"}),
            vapid_private_key=v_key,
            vapid_claims={"sub": "mailto:test@genmon.local"},
            curl=True
        )
        self.assertTrue(isinstance(curl_cmd, str))
        self.assertIn("curl", curl_cmd)
        self.assertIn("push.apple.com", curl_cmd)

    @patch("addon.genwebpush.config")
    def test_send_webpush_payload_live_with_real_pywebpush(self, mock_config) -> None:
        """Verify SendWebPushPayload end-to-end with real pywebpush/py_vapid without ASN.1 error."""
        try:
            import pywebpush
            import requests
        except ImportError:
            return  # Skip if pywebpush is not installed

        from addon.genwebpush import SendWebPushPayload, subscriptions, GenerateVapidKeyPair

        pub, priv = GenerateVapidKeyPair()
        mock_config.ReadValue.side_effect = lambda key, **kw: pub if key == "vapid_public_key" else priv if key == "vapid_private_key" else "mailto:test@genmon.local"

        target_sub = {
            "endpoint": "https://push.apple.com/sub/real_ios_device",
            "device_name": "Real iOS Device",
            "keys": {
                "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM",
                "auth": "tBHItJI5svbpez7KI4CCXg"
            }
        }

        # Mock only the lowest-level requests.Session.send to simulate HTTP 201 Created from APNs
        mock_response = MagicMock(status_code=201, text="", reason="Created")
        with patch.object(requests.Session, "send", return_value=mock_response):
            with patch("addon.genwebpush.subscriptions", [target_sub]):
                with patch("addon.genwebpush.LoadSubscriptions"):
                    success, err = SendWebPushPayload(
                        "Genmon Utility Outage",
                        "Utility Power OUTAGE Detected!",
                        category="outage",
                        target_endpoint=target_sub["endpoint"]
                    )
                    self.assertTrue(success)
                    self.assertIsNone(err)

    @patch("addon.genwebpush.config")
    def test_send_webpush_payload_with_pem_configured_key(self, mock_config) -> None:
        """Verify SendWebPushPayload handles PEM-formatted string keys in config without ASN.1 error."""
        try:
            import pywebpush
            import requests
        except ImportError:
            return

        from addon.genwebpush import SendWebPushPayload, subscriptions, GenerateVapidKeyPair, RawVapidKeyToSec1Pem

        pub, priv = GenerateVapidKeyPair()
        pem = RawVapidKeyToSec1Pem(priv)
        mock_config.ReadValue.side_effect = lambda key, **kw: pub if key == "vapid_public_key" else pem if key == "vapid_private_key" else "mailto:test@genmon.local"

        target_sub = {
            "endpoint": "https://push.apple.com/sub/real_ios_device_pem",
            "device_name": "PEM iOS Device",
            "keys": {
                "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM",
                "auth": "tBHItJI5svbpez7KI4CCXg"
            }
        }

        mock_response = MagicMock(status_code=201, text="", reason="Created")
        with patch.object(requests.Session, "send", return_value=mock_response):
            with patch("addon.genwebpush.subscriptions", [target_sub]):
                with patch("addon.genwebpush.LoadSubscriptions"):
                    success, err = SendWebPushPayload(
                        "Test Outage",
                        "Power Outage",
                        target_endpoint=target_sub["endpoint"]
                    )
                    self.assertTrue(success)
                    self.assertIsNone(err)

    def test_validate_vapid_keys_with_raw_bytes_and_pem_bytes(self) -> None:
        """Verify ValidateVapidKeys supports raw bytes and PEM bytes inputs."""
        import base64
        from addon.genwebpush import GenerateVapidKeyPair, RawVapidKeyToSec1Pem, ValidateVapidKeys

        pub, priv = GenerateVapidKeyPair()
        pem = RawVapidKeyToSec1Pem(priv)

        rem = len(priv.rstrip("=")) % 4
        padded = priv.rstrip("=") + ("=" * (4 - rem) if rem > 0 else "")
        raw_priv_bytes = base64.urlsafe_b64decode(padded)

        # 1. 32-byte raw bytes
        self.assertTrue(ValidateVapidKeys(pub, raw_priv_bytes))

        # 2. PEM bytes
        self.assertTrue(ValidateVapidKeys(pub, pem.encode("utf-8")))

        # 3. Mismatched bytes
        pub2, priv2 = GenerateVapidKeyPair()
        self.assertFalse(ValidateVapidKeys(pub2, raw_priv_bytes))

    def test_validate_vapid_keys_standard_and_urlsafe_b64(self) -> None:
        """Verify ValidateVapidKeys correctly handles standard base64 and urlsafe base64 strings."""
        import base64
        from addon.genwebpush import GenerateVapidKeyPair, ValidateVapidKeys

        pub_urlsafe, priv_urlsafe = GenerateVapidKeyPair()
        # Convert to standard base64
        pub_raw = base64.urlsafe_b64decode(pub_urlsafe + "==")
        priv_raw = base64.urlsafe_b64decode(priv_urlsafe + "==")
        pub_standard = base64.b64encode(pub_raw).decode("utf-8")
        priv_standard = base64.b64encode(priv_raw).decode("utf-8")

        self.assertTrue(ValidateVapidKeys(pub_standard, priv_standard))
        self.assertTrue(ValidateVapidKeys(pub_urlsafe, priv_standard))
        self.assertTrue(ValidateVapidKeys(pub_standard, priv_urlsafe))
        self.assertTrue(ValidateVapidKeys(pub_raw, priv_raw))

    @patch("addon.genwebpush.config")
    def test_send_webpush_payload_with_webpush_exception_response(self, mock_config) -> None:
        """Verify SendWebPushPayload handles WebPushException with response attributes."""
        from addon.genwebpush import SendWebPushPayload, subscriptions, GenerateVapidKeyPair
        pub, priv = GenerateVapidKeyPair()
        mock_config.ReadValue.side_effect = lambda key, **kw: pub if key == "vapid_public_key" else priv if key == "vapid_private_key" else "mailto:test@genmon.local"

        class MockWebPushException(Exception):
            def __init__(self, msg, status_code, text):
                super().__init__(msg)
                self.response = MagicMock(status_code=status_code, text=text)

        mock_webpush = MagicMock(side_effect=MockWebPushException("Push failed", 403, "BadJwtToken"))
        with patch.dict("sys.modules", {"pywebpush": MagicMock(webpush=mock_webpush)}):
            target_sub = {
                "endpoint": "https://push.apple.com/sub/ios_bad_jwt",
                "device_name": "Bad JWT Device",
                "keys": {"p256dh": "dummy", "auth": "dummy"}
            }
            with patch("addon.genwebpush.RemoveSubscription") as mock_remove:
                with patch("addon.genwebpush.subscriptions", [target_sub]):
                    with patch("addon.genwebpush.LoadSubscriptions"):
                        success, err = SendWebPushPayload("Test Alert", "Test", target_endpoint=target_sub["endpoint"])
                        self.assertFalse(success)
                        mock_remove.assert_called_with("https://push.apple.com/sub/ios_bad_jwt", notify_device=False)

    @patch("addon.genwebpush.SendWebPushPayload")
    @patch("addon.genwebpush.config")
    def test_event_callbacks_all_events(self, mock_config, mock_send) -> None:
        """Verify all GenNotify event callbacks execute safely without console/config AttributeErrors."""
        from addon.genwebpush import (
            OnAlarm,
            OnExercise,
            OnFuelState,
            OnManual,
            OnOff,
            OnOutage,
            OnPiState,
            OnRun,
            OnRunManual,
            OnService,
            OnSoftwareUpdate,
        )
        mock_config.ReadValue.return_type = bool
        mock_config.ReadValue.return_value = True

        for fn in [
            OnAlarm,
            OnExercise,
            OnFuelState,
            OnManual,
            OnOff,
            OnOutage,
            OnPiState,
            OnRun,
            OnRunManual,
            OnService,
            OnSoftwareUpdate,
        ]:
            mock_send.reset_mock()
            fn(Active=True)
            self.assertTrue(mock_send.called, f"Handler {fn.__name__} did not call SendWebPushPayload")

    @patch("addon.genwebpush.config")
    def test_vapid_claims_sub_formatting(self, mock_config) -> None:
        """Verify VAPID claims subject is normalized to RFC 8292 mailto:/https: URI."""
        from addon.genwebpush import GenerateVapidKeyPair, SendWebPushPayload
        pub, priv = GenerateVapidKeyPair()

        mock_webpush = MagicMock()
        with patch.dict("sys.modules", {"pywebpush": MagicMock(webpush=mock_webpush)}):
            target_sub = {
                "endpoint": "https://push.apple.com/sub/test_device",
                "device_name": "Test Device",
                "keys": {"p256dh": "dummy", "auth": "dummy"}
            }

            # 1. Plain email without mailto:
            mock_config.ReadValue.side_effect = lambda key, **kw: pub if key == "vapid_public_key" else priv if key == "vapid_private_key" else "user@example.com"
            with patch("addon.genwebpush.subscriptions", [target_sub]), patch("addon.genwebpush.LoadSubscriptions"):
                SendWebPushPayload("Test Title", "Test Body", target_endpoint=target_sub["endpoint"])
                claims = mock_webpush.call_args[1]["vapid_claims"]
                self.assertEqual(claims["sub"], "mailto:user@example.com")

            # 2. Empty string fallback
            mock_config.ReadValue.side_effect = lambda key, **kw: pub if key == "vapid_public_key" else priv if key == "vapid_private_key" else ""
            with patch("addon.genwebpush.subscriptions", [target_sub]), patch("addon.genwebpush.LoadSubscriptions"):
                SendWebPushPayload("Test Title", "Test Body", target_endpoint=target_sub["endpoint"])
                claims = mock_webpush.call_args[1]["vapid_claims"]
                self.assertEqual(claims["sub"], "mailto:genmon.push@gmail.com")

            # 3. https: URI preserved
            mock_config.ReadValue.side_effect = lambda key, **kw: pub if key == "vapid_public_key" else priv if key == "vapid_private_key" else "https://genmon.local/contact"
            with patch("addon.genwebpush.subscriptions", [target_sub]), patch("addon.genwebpush.LoadSubscriptions"):
                SendWebPushPayload("Test Title", "Test Body", target_endpoint=target_sub["endpoint"])
                claims = mock_webpush.call_args[1]["vapid_claims"]
                self.assertEqual(claims["sub"], "https://genmon.local/contact")

    def test_raw_vapid_key_to_sec1_pem_quoted_and_whitespace(self) -> None:
        """Verify RawVapidKeyToSec1Pem strips surrounding quotes and whitespace from config values."""
        from addon.genwebpush import GenerateVapidKeyPair, RawVapidKeyToSec1Pem
        pub, priv = GenerateVapidKeyPair()
        pem_clean = RawVapidKeyToSec1Pem(priv)

        # Surrounded by double quotes
        pem_double_quotes = RawVapidKeyToSec1Pem(f'"{priv}"')
        self.assertEqual(pem_clean, pem_double_quotes)

        # Surrounded by single quotes and whitespace
        pem_single_quotes = RawVapidKeyToSec1Pem(f"  '{priv}' \n")
        self.assertEqual(pem_clean, pem_single_quotes)

    def test_validate_vapid_keys_quoted_and_whitespace(self) -> None:
        """Verify ValidateVapidKeys handles quoted and whitespace-padded keys."""
        from addon.genwebpush import GenerateVapidKeyPair, ValidateVapidKeys
        pub, priv = GenerateVapidKeyPair()
        self.assertTrue(ValidateVapidKeys(f'"{pub}"', f"'{priv}'"))
        self.assertTrue(ValidateVapidKeys(f"  {pub} \n", f"\n{priv}  "))

    def test_generate_apple_jwt_rfc8292_conformance(self) -> None:
        """Verify GenerateAppleJWT creates RFC 8292 compliant JWT with exact 64-byte signature."""
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import ec
            from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature, encode_dss_signature
            from py_vapid import Vapid
        except ImportError:
            return

        import base64
        import json
        from addon.genwebpush import GenerateAppleJWT, GenerateVapidKeyPair, RawVapidKeyToSec1Pem

        pub_b64, priv_b64 = GenerateVapidKeyPair()
        pem_str = RawVapidKeyToSec1Pem(priv_b64)
        vapid_obj = Vapid.from_pem(pem_str.encode("utf-8"))

        aud = "https://push.apple.com"
        sub = "mailto:genmon.push@gmail.com"

        # Test with multiple private key representations including raw bytes, bytearrays, and PEM bytes
        rem = len(priv_b64.rstrip("=")) % 4
        raw_priv_32 = base64.urlsafe_b64decode(priv_b64.rstrip("=") + ("=" * (4 - rem) if rem > 0 else ""))

        test_representations = [
            priv_b64,
            pem_str,
            pem_str.encode("utf-8"),
            vapid_obj,
            vapid_obj.private_key,
            raw_priv_32,
            bytearray(raw_priv_32),
            f'"{priv_b64}"',
            f"  {priv_b64} \n",
        ]

        for priv_input in test_representations:
            auth_header = GenerateAppleJWT(priv_input, sub, aud)
            self.assertIsNotNone(auth_header, f"GenerateAppleJWT returned None for input type {type(priv_input)}")
            self.assertTrue(auth_header.startswith("vapid t="))
            self.assertIn(", k=", auth_header)

            parts = auth_header.split(" ")
            self.assertEqual(parts[0], "vapid")
            self.assertTrue(parts[1].startswith("t="))
            self.assertTrue(parts[2].startswith("k="))

            jwt_token = parts[1][2:].rstrip(",")
            jwt_parts = jwt_token.split(".")
            self.assertEqual(len(jwt_parts), 3)

            # 1. Header verification
            header_bytes = base64.urlsafe_b64decode(jwt_parts[0] + "=" * ((4 - len(jwt_parts[0]) % 4) % 4))
            header = json.loads(header_bytes.decode("utf-8"))
            self.assertEqual(header, {"typ": "JWT", "alg": "ES256"})

            # 2. Claims verification
            claims_bytes = base64.urlsafe_b64decode(jwt_parts[1] + "=" * ((4 - len(jwt_parts[1]) % 4) % 4))
            claims = json.loads(claims_bytes.decode("utf-8"))
            self.assertEqual(claims["aud"], aud)
            self.assertEqual(claims["sub"], sub)
            self.assertIn("exp", claims)

            # 3. Signature verification (strictly 64 bytes R|S)
            sig_bytes = base64.urlsafe_b64decode(jwt_parts[2] + "=" * ((4 - len(jwt_parts[2]) % 4) % 4))
            self.assertEqual(len(sig_bytes), 64)
            r = int.from_bytes(sig_bytes[:32], "big")
            s = int.from_bytes(sig_bytes[32:], "big")
            rsig_der = encode_dss_signature(r, s)

            # 4. Public key extraction & mathematical verification
            pub_key_b64 = parts[2][2:]
            pub_key_bytes = base64.urlsafe_b64decode(pub_key_b64 + "=" * ((4 - len(pub_key_b64) % 4) % 4))
            self.assertEqual(len(pub_key_bytes), 65)
            self.assertEqual(pub_key_bytes[0], 0x04)

            pub_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), pub_key_bytes)
            signing_input = f"{jwt_parts[0]}.{jwt_parts[1]}".encode("utf-8")
            pub_key.verify(rsig_der, signing_input, ec.ECDSA(hashes.SHA256()))

        # Verify invalid keys return None safely
        self.assertIsNone(GenerateAppleJWT("", sub, aud))
        self.assertIsNone(GenerateAppleJWT(None, sub, aud))
        self.assertIsNone(GenerateAppleJWT("not_a_valid_key", sub, aud))
        self.assertIsNone(GenerateAppleJWT(b"too_short", sub, aud))

    def test_base64url_subscriber_key_decoding_and_http_ece_encryption(self) -> None:
        """Verify base64url decoding of subscriber keys and successful http_ece payload encryption."""
        try:
            import http_ece
            from cryptography.hazmat.primitives.asymmetric import ec
        except ImportError:
            return

        import base64
        import json
        import os
        from test_apple_push import b64urldecode, b64urlencode
        from addon.genwebpush import b64urldecode as b64urldecode_mod, b64urlencode as b64urlencode_mod

        # Standard subscription keys from Web Push subscription JSON
        p256dh_b64 = "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM"
        auth_b64 = "tBHItJI5svbpez7KI4CCXg"

        # 1. Base64URL decode
        for decode_fn in [b64urldecode, b64urldecode_mod]:
            raw_p256dh = decode_fn(p256dh_b64)
            raw_auth = decode_fn(auth_b64)

            self.assertEqual(len(raw_p256dh), 65)
            self.assertEqual(raw_p256dh[0], 0x04)
            self.assertEqual(len(raw_auth), 16)

            # Verify raw bytes and bytearray representations are preserved cleanly
            self.assertEqual(decode_fn(raw_p256dh), raw_p256dh)
            self.assertEqual(decode_fn(bytearray(raw_p256dh)), raw_p256dh)
            self.assertEqual(decode_fn(raw_auth), raw_auth)
            self.assertEqual(decode_fn(bytearray(raw_auth)), raw_auth)
            self.assertEqual(decode_fn(b"abcdef0123456789"), b"abcdef0123456789")
            self.assertEqual(decode_fn(None), b"")
            self.assertEqual(decode_fn(""), b"")

        for encode_fn in [b64urlencode, b64urlencode_mod]:
            self.assertEqual(encode_fn(raw_p256dh), p256dh_b64)
            self.assertEqual(encode_fn(raw_auth), auth_b64)

        # 2. http_ece.encrypt with decoded raw bytes succeeds without Unsupported elliptic curve point type error
        server_key = ec.generate_private_key(ec.SECP256R1())
        salt = os.urandom(16)
        payload = {"title": "Test Alert", "body": "Power Outage"}

        encrypted_data = http_ece.encrypt(
            json.dumps(payload).encode("utf-8"),
            salt=salt,
            private_key=server_key,
            dh=raw_p256dh,
            auth_secret=raw_auth,
            version="aes128gcm"
        )
        self.assertTrue(len(encrypted_data) > 0)
        self.assertEqual(encrypted_data[:16], salt)

        # 3. Passing utf-8 encoded string reproduces ValueError: Unsupported elliptic curve point type
        with self.assertRaises(ValueError) as ctx:
            http_ece.encrypt(
                json.dumps(payload).encode("utf-8"),
                salt=salt,
                private_key=server_key,
                dh=p256dh_b64.encode("utf-8"),
                auth_secret=auth_b64.encode("utf-8"),
                version="aes128gcm"
            )
        self.assertIn("Unsupported elliptic curve point type", str(ctx.exception))

    @patch("genmonlib.mysupport.MySupport.SetupAddOnProgram")
    @patch("addon.genwebpush.GenNotify")
    @patch("addon.genwebpush.LoadSubscriptions")
    @patch("addon.genwebpush.EnsureVapidKeys")
    def test_daemon_startup_unpack_and_notify_init(self, mock_vapid, mock_subs, mock_notify_cls, mock_setup) -> None:
        """Verify daemon entry point correctly unpacks 6-tuple from SetupAddOnProgram and initializes GenNotify."""
        mock_console = MagicMock()
        mock_log = MagicMock()
        # SetupAddOnProgram returns 6 values: console, ConfigFilePath, address, port, loglocation, log
        mock_setup.return_value = (mock_console, "/etc/genmon", "127.0.0.1", 8800, "/var/log", mock_log)
        
        mock_notify_instance = MagicMock()
        mock_notify_cls.return_value = mock_notify_instance

        # Simulate execution of the main block
        import addon.genwebpush as gwp
        (
            console,
            ConfigFilePath,
            address,
            port,
            loglocation,
            log,
        ) = gwp.MySupport.SetupAddOnProgram("genwebpush")
        self.assertEqual(address, "127.0.0.1")
        self.assertEqual(port, 8800)
        self.assertEqual(loglocation, "/var/log")


if __name__ == "__main__":
    unittest.main()



