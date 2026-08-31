import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock

from genmonlib.controller import GeneratorController
from genmonlib.myplatform import MyPlatform


class TestPiPowerMonitorIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.log_file = os.path.join(self.temp_dir, "pi_power_monitor.log")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_controller_sensor_names_and_history(self):
        # Create rotating log sample
        with open(self.log_file, "w") as f:
            f.write(
                "[2026-08-18 18:16:55] Core: 1.3450V | Power Status: HEALTHY\n"
                "[2026-08-18 18:17:00] Core: 1.3450V | Power Status: HEALTHY\n"
                "[2026-08-18 18:17:05] Core: 1.2350V | Power Status: UNDERVOLTAGE\n"
            )

        mock_config = MagicMock()
        mock_config.HasOption.return_value = False
        mock_config.ReadValue.side_effect = lambda key, return_type=None, default=None: {
            "useraspberrypicputempgauge": False,
            "uselinuxwifisignalgauge": False,
            "use_pi_power_monitor": True,
            "pi_power_log_path": self.log_file,
            "disablesensorlog": False,
            "sensorlogmax": 5.0,
            "max_sensorlog_entries": 8000,
        }.get(key, default)

        controller = GeneratorController(
            None,
            config=mock_config,
            ConfigFilePath=self.temp_dir,
        )
        controller.Platform = MyPlatform()
        controller.PiPowerLogPath = self.log_file
        controller.bUsePiPowerMonitorGauge = True

        sensor_names = controller.GetSensorNames()
        self.assertIn("Pi Voltage", sensor_names)

        # Test reading sensor log history from controller
        history = controller.ReadSensorLogFromFile("Pi Voltage", Minutes=0)
        self.assertEqual(len(history), 3)
        self.assertEqual(history[0][0], "2026-08-18 18:17:05")
        self.assertEqual(history[0][1], "1.2350")


if __name__ == "__main__":
    unittest.main()
