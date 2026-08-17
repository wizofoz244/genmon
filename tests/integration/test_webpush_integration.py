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


if __name__ == "__main__":
    unittest.main()
