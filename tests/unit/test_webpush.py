#!/usr/bin/env python3
"""Unit test suite for genwebpush.py (Web Push / PWA Notifications).

Validates cryptographic VAPID key generation, key validation, Apple APNs
JWT token generation, payload construction, and subscription store management
per Google Python Style Guide.
"""

from __future__ import annotations

import base64
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import tests.conftest
from addon.genwebpush import (
    AddSubscription,
    b64urldecode,
    b64urlencode,
    GenerateAppleJWT,
    GenerateVapidKeyPair,
    GetSubscriptionsList,
    OnAlarm,
    OnExercise,
    OnOutage,
    RawVapidKeyToSec1Pem,
    RemoveSubscription,
    SendWebPushPayload,
    UpdateSubscriptionName,
    ValidateVapidKeys,
)


class TestWebPush(unittest.TestCase):
    """Unit tests for Web Push VAPID cryptography and event handling."""

    def setUp(self) -> None:
        """Sets up temporary subscription storage and mocks for testing."""
        self.temp_sub_file = tempfile.NamedTemporaryFile(
            "w", delete=False, suffix=".json"
        )
        json.dump([], self.temp_sub_file)
        self.temp_sub_file.close()

    def tearDown(self) -> None:
        """Cleans up temporary files after test completion."""
        if os.path.exists(self.temp_sub_file.name):
            os.remove(self.temp_sub_file.name)

    def test_base64_url_encoding_and_decoding(self) -> None:
        """Tests unpadded base64url encoding and decoding with variable length bytes."""
        sample_bytes = b"Hello, Genmon WebPush 2026!"
        encoded = b64urlencode(sample_bytes)
        self.assertFalse(encoded.endswith("="))
        decoded = b64urldecode(encoded)
        self.assertEqual(decoded, sample_bytes)

        # Test padding recovery with unpadded base64 strings
        raw_hex = bytes.fromhex("0102030405060708090a0b0c0d0e0f10")
        enc_no_pad = base64.urlsafe_b64encode(raw_hex).decode("ascii").rstrip("=")
        self.assertEqual(b64urldecode(enc_no_pad), raw_hex)

    def test_vapid_keypair_generation_and_validation(self) -> None:
        """Tests that generated VAPID keypairs are valid NIST P-256 EC keys."""
        pub, priv = GenerateVapidKeyPair()
        self.assertTrue(len(pub) > 0, "Public key must not be empty.")
        self.assertTrue(len(priv) > 0, "Private key must not be empty.")
        self.assertTrue(ValidateVapidKeys(pub, priv), "Keypair must validate successfully.")

        # Invalid or mismatched keys must return False
        self.assertFalse(ValidateVapidKeys(pub, "invalid_private_key"))
        self.assertFalse(ValidateVapidKeys("invalid_public_key", priv))

    def test_raw_vapid_key_to_sec1_pem_conversion(self) -> None:
        """Tests conversion of 32-byte raw private keys to RFC 5915 SEC1 PEM format."""
        pub, priv = GenerateVapidKeyPair()
        pem = RawVapidKeyToSec1Pem(priv)
        self.assertIn("-----BEGIN EC PRIVATE KEY-----", pem)
        self.assertIn("-----END EC PRIVATE KEY-----", pem)
        # Re-conversion of already-formatted PEM should be idempotent
        self.assertEqual(RawVapidKeyToSec1Pem(pem), pem)

    def test_apple_jwt_generation_claims(self) -> None:
        """Tests generation of RFC 8292 compliant JWT Authorization header for Apple APNs."""
        pub, priv = GenerateVapidKeyPair()
        sub = "mailto:test@example.com"
        aud = "https://web.push.apple.com"

        auth_header = GenerateAppleJWT(priv, sub, aud)
        self.assertIsNotNone(auth_header)
        self.assertTrue(auth_header.startswith("vapid t="))
        self.assertIn(", k=", auth_header)

        # Extract and verify JWT token payload claims
        token = auth_header.split(" ")[1].split(",")[0].replace("t=", "")
        parts = token.split(".")
        self.assertEqual(len(parts), 3, "JWT must have header, payload, and signature components.")

        payload_b64 = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
        payload_dict = json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
        self.assertEqual(payload_dict["sub"], sub)
        self.assertEqual(payload_dict["aud"], aud)
        self.assertIn("exp", payload_dict)

    def test_subscription_management_lifecycle(self) -> None:
        """Tests adding, updating, listing, and removing subscriptions."""
        with patch("addon.genwebpush.GetSubscriptionsFile", return_value=self.temp_sub_file.name):
            sub1 = {
                "endpoint": "https://fcm.googleapis.com/fcm/send/test_endpoint_1",
                "keys": {"p256dh": "key1", "auth": "auth1"},
                "device_name": "Test Android",
                "user_agent": "Mozilla/5.0 (Linux; Android 14)",
            }
            self.assertTrue(AddSubscription(sub1))

            subs = GetSubscriptionsList()
            self.assertEqual(len(subs), 1)
            self.assertEqual(subs[0]["device_name"], "Test Android")
            self.assertEqual(subs[0]["service"], "Google Push (FCM)")

            # Update device name
            self.assertTrue(UpdateSubscriptionName(sub1["endpoint"], "Updated Phone"))
            subs = GetSubscriptionsList()
            self.assertEqual(subs[0]["device_name"], "Updated Phone")

            # Remove subscription
            RemoveSubscription(sub1["endpoint"], notify_device=False)
            subs = GetSubscriptionsList()
            self.assertEqual(len(subs), 0)

    @patch("addon.genwebpush.SendWebPushPayload")
    def test_event_dispatch_handlers(self, mock_send) -> None:
        """Tests that outage, exercise, and alarm events trigger formatted push payloads."""
        mock_config = MagicMock()
        mock_config.ReadValue.return_value = True

        with patch("addon.genwebpush.config", mock_config):
            # Test Outage Active & Restored
            OnOutage(active=True)
            mock_send.assert_called_with("Genmon Utility Outage", "Utility Power OUTAGE Detected!", category="outage")

            OnOutage(active=False)
            mock_send.assert_called_with("Genmon Utility Outage", "Utility Power RESTORED.", category="outage")

            # Test Exercise
            OnExercise(active=True)
            mock_send.assert_called_with("Genmon Generator Exercise", "Generator Started Scheduled Exercise", category="exercise")

            # Test Alarm
            OnAlarm(active=True)
            mock_send.assert_called_with("🚨 Genmon Generator ALARM!", "ALARM DETECTED on Generator Controller!", category="error")


if __name__ == "__main__":
    unittest.main()
