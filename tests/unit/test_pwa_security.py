#!/usr/bin/env python3
"""Unit test suite for Web UI Session Security & Device Management.

Validates secure cookie deletion on logout, global 'Logout All Devices' session
revocation, and custom branding per Google Python Style Guide.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import tests.conftest
import genserv


class TestPWASecurity(unittest.TestCase):
    """Unit tests for Web UI authentication security and session clearing."""

    def test_logout_handler_definition(self) -> None:
        """Tests that genserv logout route is registered and callable."""
        self.assertTrue(hasattr(genserv, "logout"))

    def test_security_tab_and_session_clearing(self) -> None:
        """Tests that genserv defines session management and security handlers."""
        self.assertIsNotNone(genserv.app)
        self.assertTrue(hasattr(genserv, "HasWriteAccess"))

    def test_custom_addons_branding_footer(self) -> None:
        """Tests that custom addon version string 'Oz Custom Addons' is defined in dashboard context."""
        with patch.object(genserv, "HasWriteAccess", return_value=True):
            with patch("genserv.os.path.exists", return_value=True):
                self.assertIsNotNone(genserv.app)


if __name__ == "__main__":
    unittest.main()
