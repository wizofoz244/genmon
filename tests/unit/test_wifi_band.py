#!/usr/bin/env python3
"""Unit test suite for WiFi band detection and tile integration in Genmon."""

import sys
import unittest
from unittest.mock import MagicMock, patch

import tests.conftest
from genmonlib.myplatform import MyPlatform
from genmonlib.mytile import MyTile


class TestWiFiBand(unittest.TestCase):
    """Test cases for MyPlatform.GetWiFiBand and MyTile ExtraCallback integration."""

    def setUp(self):
        self.log = MagicMock()
        self.platform = MyPlatform(self.log)

    def test_get_wifi_band_24ghz_iw(self):
        """Tests GetWiFiBand returns '2.4 GHz' from iw link output."""
        iw_output = b"Connected to 00:11:22:33:44:55 (on wlan0)\n\tSSID: TestNet\n\tfreq: 2437\n\tsignal: -55 dBm"
        with patch.object(self.platform, "IsOSLinux", return_value=True):
            with patch("subprocess.check_output", return_value=iw_output):
                band = self.platform.GetWiFiBand("wlan0")
                self.assertEqual(band, "2.4 GHz")

    def test_get_wifi_band_5ghz_iw(self):
        """Tests GetWiFiBand returns '5 GHz' from iw link output."""
        iw_output = b"Connected to 00:11:22:33:44:55 (on wlan0)\n\tSSID: TestNet\n\tfreq: 5240\n\tsignal: -62 dBm"
        with patch.object(self.platform, "IsOSLinux", return_value=True):
            with patch("subprocess.check_output", return_value=iw_output):
                band = self.platform.GetWiFiBand("wlan0")
                self.assertEqual(band, "5 GHz")

    def test_get_wifi_band_6ghz_iw(self):
        """Tests GetWiFiBand returns '6 GHz' from iw link output."""
        iw_output = b"Connected to 00:11:22:33:44:55 (on wlan0)\n\tSSID: TestNet\n\tfreq: 6115\n\tsignal: -48 dBm"
        with patch.object(self.platform, "IsOSLinux", return_value=True):
            with patch("subprocess.check_output", return_value=iw_output):
                band = self.platform.GetWiFiBand("wlan0")
                self.assertEqual(band, "6 GHz")

    def test_get_wifi_band_iwconfig_fallback(self):
        """Tests GetWiFiBand falls back to iwconfig output when iw link fails."""
        iwconfig_output = b"wlan0 IEEE 802.11 ESSID:\"TestNet\"\n Mode:Managed Frequency:5.24 GHz Access Point: 00:11:22:33:44:55\n Link Quality=50/70 Signal level=-60 dBm"

        def mock_check_output(cmd):
            if cmd[0] == "iw":
                raise RuntimeError("iw failed")
            return iwconfig_output

        with patch.object(self.platform, "IsOSLinux", return_value=True):
            with patch("subprocess.check_output", side_effect=mock_check_output):
                band = self.platform.GetWiFiBand("wlan0")
                self.assertEqual(band, "5 GHz")

    def test_mytile_extra_callback_integration(self):
        """Tests MyTile GetGUIInfo calls extra_callback and includes 'band' in GUIInfo."""
        mock_signal_cb = MagicMock(return_value=-65)
        mock_band_cb = MagicMock(return_value="5 GHz")

        tile = MyTile(
            self.log,
            title="WiFi Signal",
            units="dBm",
            type="wifi",
            callback=mock_signal_cb,
            callbackparameters=(),
            extra_callback=mock_band_cb,
        )

        gui_info = tile.GetGUIInfo()
        self.assertEqual(gui_info["title"], "WiFi Signal")
        self.assertEqual(gui_info["value"], "-65")
        self.assertEqual(gui_info.get("band"), "5 GHz")
        mock_band_cb.assert_called_once()


if __name__ == "__main__":
    unittest.main()
