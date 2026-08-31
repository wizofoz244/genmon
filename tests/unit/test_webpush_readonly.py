#!/usr/bin/env python3
"""Unit tests verifying read-only authenticated users can manage Web Push subscriptions."""

import unittest
from unittest.mock import MagicMock, patch

import tests.conftest
import genserv


class TestWebPushReadOnly(unittest.TestCase):
    """Test suite for WebPush API access control."""

    @patch("genserv.LoginActive", return_value=True)
    def test_is_authenticated_when_logged_in(self, mock_login_active):
        """Verify IsAuthenticated returns True for logged in readonly user."""
        genserv.session.get = lambda k, d=None: {"logged_in": True, "write_access": False}.get(k, d)
        self.assertTrue(genserv.IsAuthenticated())
        self.assertFalse(genserv.HasWriteAccess())

    @patch("genserv.LoginActive", return_value=True)
    def test_is_authenticated_when_logged_out(self, mock_login_active):
        """Verify IsAuthenticated returns False for logged out user."""
        genserv.session.get = lambda k, d=None: {"logged_in": False}.get(k, d)
        self.assertFalse(genserv.IsAuthenticated())

    @patch("genserv.IsAuthenticated", return_value=True)
    @patch("genserv.request")
    @patch("addon.genwebpush.AddSubscription")
    def test_authenticated_user_can_subscribe(self, mock_add_sub, mock_req, mock_auth):
        """Verify that an authenticated user can subscribe to web push."""
        mock_req.get_json.return_value = {
            "endpoint": "https://fcm.googleapis.com/fcm/send/test12345",
            "keys": {"p256dh": "key1", "auth": "key2"},
            "device_name": "Test Phone"
        }
        res = genserv.webpush_subscribe()
        mock_add_sub.assert_called_once()

    @patch("genserv.IsAuthenticated", return_value=False)
    def test_unauthenticated_user_blocked_from_subscribe(self, mock_auth):
        """Verify that an unauthenticated user is rejected with 401 Unauthorized."""
        res = genserv.webpush_subscribe()
        self.assertIsInstance(res, tuple)
        self.assertEqual(res[1], 401)

    @patch("genserv.IsAuthenticated", return_value=True)
    @patch("genserv.request")
    @patch("addon.genwebpush.RemoveSubscription")
    def test_authenticated_user_can_unsubscribe(self, mock_remove_sub, mock_req, mock_auth):
        """Verify that an authenticated user can unsubscribe their device."""
        mock_req.get_json.return_value = {"endpoint": "https://fcm.googleapis.com/fcm/send/test12345"}
        res = genserv.webpush_unsubscribe()
        mock_remove_sub.assert_called_once_with("https://fcm.googleapis.com/fcm/send/test12345")

    @patch("genserv.IsAuthenticated", return_value=True)
    @patch("genserv.request")
    @patch("addon.genwebpush.UpdateSubscriptionName")
    def test_authenticated_user_can_update_device_name(self, mock_update_name, mock_req, mock_auth):
        """Verify that an authenticated user can update their device name."""
        mock_req.get_json.return_value = {"endpoint": "https://fcm.googleapis.com/fcm/send/test12345", "device_name": "New Name"}
        res = genserv.webpush_update_name()
        mock_update_name.assert_called_once_with("https://fcm.googleapis.com/fcm/send/test12345", "New Name")

    @patch("genserv.IsAuthenticated", return_value=True)
    @patch("genserv.request")
    @patch("addon.genwebpush.SendWebPushPayload", return_value=(True, None))
    def test_authenticated_user_can_send_test(self, mock_send, mock_req, mock_auth):
        """Verify that an authenticated user can send a test notification."""
        mock_req.get_json.return_value = {"endpoint": "https://fcm.googleapis.com/fcm/send/test12345"}
        res = genserv.webpush_test()
        mock_send.assert_called_once()

    @patch("genserv.IsAuthenticated", return_value=True)
    @patch("genserv.HasWriteAccess", return_value=False)
    @patch("genserv.request")
    def test_readonly_user_blocked_from_changing_global_preferences(self, mock_req, mock_write, mock_auth):
        """Verify that modifying global server notification preferences still requires write access."""
        mock_req.method = "POST"
        mock_req.get_json.return_value = {"notify_outage": False}
        res = genserv.webpush_preferences()
        self.assertIsInstance(res, tuple)
        self.assertEqual(res[1], 403)


if __name__ == "__main__":
    unittest.main()
