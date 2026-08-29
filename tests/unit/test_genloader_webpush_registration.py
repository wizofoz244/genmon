#!/usr/bin/env python3
"""Unit tests for genwebpush registration in genloader and genserv."""

import unittest
from unittest.mock import MagicMock, patch

import tests.conftest
from genloader import Loader


class TestGenloaderWebPushRegistration(unittest.TestCase):
    """Test suite for genwebpush auto-registration and loader config management."""

    @patch("genmonlib.mysupport.MySupport.SetupAddOnProgram")
    def setUp(self, mock_setup):
        mock_setup.return_value = (MagicMock(), "/tmp", "127.0.0.1", 8800, "/tmp", MagicMock())
        self.loader = Loader()
        self.loader.config = MagicMock()
        self.loader.config.HasSection.return_value = False
        self.loader.config.HasOption.return_value = False
        self.loader.config.GetSections.return_value = ["genmon", "genserv"]

    def test_dependency_registry_has_genwebpush(self):
        """Verify genwebpush is present in DependencyRegistry."""
        registry = self.loader.GetDependencyRegistry()
        addon_modules = [m for addon in registry.get("addons", []) for m in addon.get("modules", [])]
        self.assertIn("genwebpush", addon_modules)

    def test_update_if_needed_registers_genwebpush(self):
        """Verify UpdateIfNeeded injects genwebpush when not in config."""
        self.loader.config.HasSection.return_value = False
        with patch.object(self.loader, "AddEntry") as mock_add:
            self.loader.UpdateIfNeeded()
            mock_add.assert_any_call(
                section="genwebpush",
                module="genwebpush.py",
                conffile="genwebpush.conf",
                args="",
                priority="2",
                enable="True",
            )

    def test_add_entry_sets_enable_flag(self):
        """Verify AddEntry writes custom enable value."""
        self.loader.AddEntry(section="genwebpush", module="genwebpush.py", enable="True")
        self.loader.config.WriteValue.assert_any_call("enable", "True", section="genwebpush")


if __name__ == "__main__":
    unittest.main()
