#!/usr/bin/env python3
"""Integration test suite for Modbus simulation and controller data parsing."""

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import tests.conftest
from genmonlib.generac_evolution import Evolution
from genmonlib.modbus_file import ModbusFile
from genmonlib.mytile import MyTile


class TestModbusControllerIntegration(unittest.TestCase):
    """Integration tests between Modbus register simulation and Generac Evolution Controller state."""

    def setUp(self) -> None:
        self.log = MagicMock()
        self.test_data = {
            "Registers": {
                "0001": "0001",  # Engine State: Ready / Off / Running
                "0002": "0000",  # No Alarm
                "0007": "0E10",  # RPM: 3600 (0x0E10)
                "0008": "0258",  # Frequency: 60.0 Hz (600 / 0x0258)
                "0009": "0960",  # Utility Voltage: 240.0 V (2400 / 0x0960)
                "000a": "0082",  # Battery Voltage: 13.0 V (130 / 0x0082)
                "0052": "0000",  # Digital Inputs
                "0053": "0001",  # Digital Outputs
            },
            "Strings": {
                "01f4": "3001234567"  # Serial Number
            },
            "FileData": {},
            "Coils": {},
            "Inputs": {},
        }
        self.temp_file = tempfile.NamedTemporaryFile("w", delete=False, suffix=".json")
        json.dump(self.test_data, self.temp_file)
        self.temp_file.close()

    def tearDown(self) -> None:
        if os.path.exists(self.temp_file.name):
            os.remove(self.temp_file.name)

    def test_modbus_file_data_loading(self) -> None:
        """Tests that ModbusFile correctly parses JSON registers and strings."""
        modbus_sim = ModbusFile(
            updatecallback=None,
            inputfile=self.temp_file.name,
        )
        self.assertTrue(modbus_sim.ReadJSONFile(self.temp_file.name))
        self.assertEqual(modbus_sim.Registers.get("0001"), "0001")
        self.assertEqual(modbus_sim.Registers.get("0007"), "0E10")
        self.assertEqual(modbus_sim.Strings.get("01f4"), "3001234567")

    @patch("genmonlib.myclient.ClientInterface")
    def test_controller_simulation_tile_integration(self, mock_client_cls) -> None:
        """Tests that Evolution controller initialized with ModbusFile returns correct tile data."""
        mock_config = MagicMock()
        mock_config.HasOption.return_value = False
        mock_config.ReadValue.side_effect = lambda key, **kwargs: kwargs.get("default", None)

        evolution = Evolution(
            log=self.log,
            config=mock_config,
            simulation=True,
            simulationfile=self.temp_file.name,
        )

        evolution.EngineState = "Ready"
        evolution.UtilityVoltage = 240.0
        evolution.BatteryVoltage = 13.4
        evolution.LineFreq = 60.0
        evolution.EngineRPM = 3600

        tile = MyTile(
            self.log,
            title="Utility Voltage",
            units="V",
            type="linevolts",
            nominal=240,
            callback=lambda: evolution.UtilityVoltage,
            callbackparameters=(),
        )

        gui_info = tile.GetGUIInfo()
        self.assertEqual(gui_info["title"], "Utility Voltage")
        self.assertEqual(gui_info["value"], "240")
        self.assertEqual(gui_info["text"], "240 V")


if __name__ == "__main__":
    unittest.main()
