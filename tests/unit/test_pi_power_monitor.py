import os
import shutil
import tempfile
import time
import unittest
from unittest.mock import MagicMock

from genmonlib.myplatform import MyPlatform
from genmonlib.mytile import MyTile


class TestPiPowerMonitor(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.log_file = os.path.join(self.temp_dir, "pi_power_monitor.log")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_parse_healthy_log_line(self):
        line = "[2026-08-18 18:16:55] Core: 1.3450V | Power Status: HEALTHY"
        parsed = MyPlatform.ParsePiPowerLogLine(line)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["timestamp"], "2026-08-18 18:16:55")
        self.assertAlmostEqual(parsed["voltage"], 1.3450, places=4)
        self.assertEqual(parsed["status"], "HEALTHY")
        self.assertEqual(parsed["voltage_str"], "1.3450 V")

    def test_parse_undervoltage_log_line(self):
        line = "[2026-08-18 18:17:05] Core: 1.2350V | Power Status: UNDERVOLTAGE"
        parsed = MyPlatform.ParsePiPowerLogLine(line)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["timestamp"], "2026-08-18 18:17:05")
        self.assertAlmostEqual(parsed["voltage"], 1.2350, places=4)
        self.assertEqual(parsed["status"], "UNDERVOLTAGE")

    def test_parse_whitespace_variations(self):
        line = "  [2026-08-18 18:17:05]   Core:   1.2350 V  |  Power Status:   UNDERVOLTAGE   \n"
        parsed = MyPlatform.ParsePiPowerLogLine(line)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["timestamp"], "2026-08-18 18:17:05")
        self.assertAlmostEqual(parsed["voltage"], 1.2350, places=4)
        self.assertEqual(parsed["status"], "UNDERVOLTAGE")

    def test_parse_invalid_lines(self):
        self.assertIsNone(MyPlatform.ParsePiPowerLogLine(""))
        self.assertIsNone(MyPlatform.ParsePiPowerLogLine("# Comment line"))
        self.assertIsNone(MyPlatform.ParsePiPowerLogLine("Random garbage line without voltage"))

    def test_get_pi_power_status_and_voltage(self):
        sample_data = (
            "[2026-08-18 18:16:55] Core: 1.3450V | Power Status: HEALTHY\n"
            "[2026-08-18 18:17:00] Core: 1.3450V | Power Status: HEALTHY\n"
            "[2026-08-18 18:17:05] Core: 1.2350V | Power Status: UNDERVOLTAGE\n"
        )
        with open(self.log_file, "w") as f:
            f.write(sample_data)

        platform = MyPlatform()
        self.assertTrue(platform.HasPiPowerLog(self.log_file))

        volt, status, ts = platform.GetPiPowerStatus(self.log_file)
        self.assertAlmostEqual(volt, 1.2350, places=4)
        self.assertEqual(status, "UNDERVOLTAGE")
        self.assertEqual(ts, "2026-08-18 18:17:05")

        volt_float = platform.GetPiVoltage(ReturnFloat=True, log_path=self.log_file)
        self.assertAlmostEqual(volt_float, 1.2350, places=4)

        volt_str = platform.GetPiVoltage(ReturnFloat=False, log_path=self.log_file)
        self.assertEqual(volt_str, "1.2350 V")

    def test_get_pi_power_log_history_rotating(self):
        # Create rotated file .1 (older)
        rot_file = self.log_file + ".1"
        with open(rot_file, "w") as f:
            f.write(
                "[2026-08-18 18:16:45] Core: 1.3500V | Power Status: HEALTHY\n"
                "[2026-08-18 18:16:50] Core: 1.3500V | Power Status: HEALTHY\n"
            )

        # Create active file (newer)
        with open(self.log_file, "w") as f:
            f.write(
                "[2026-08-18 18:16:55] Core: 1.3450V | Power Status: HEALTHY\n"
                "[2026-08-18 18:17:00] Core: 1.2350V | Power Status: UNDERVOLTAGE\n"
            )

        platform = MyPlatform()
        history = platform.GetPiPowerLogHistory(self.log_file, minutes=0)
        self.assertEqual(len(history), 4)

        # Should be sorted newest-first
        self.assertEqual(history[0][0], "2026-08-18 18:17:00")
        self.assertEqual(history[0][1], "1.2350")
        self.assertEqual(history[3][0], "2026-08-18 18:16:45")
        self.assertEqual(history[3][1], "1.3500")

    def test_mytile_voltage_type(self):
        mock_log = MagicMock()
        tile = MyTile(
            mock_log,
            title="Pi Voltage",
            units="V",
            type="voltage",
            subtype="voltage",
            nominal=1.35,
            minimum=0.8,
            maximum=1.6,
            callback=lambda: 1.345,
        )
        self.assertEqual(tile.Title, "Pi Voltage")
        self.assertEqual(tile.Units, "V")
        self.assertEqual(tile.Type, "voltage")
        self.assertEqual(tile.Nominal, 1.35)
        self.assertEqual(tile.Minimum, 0.8)
        self.assertEqual(tile.Maximum, 1.6)
        self.assertIsNotNone(tile.ColorZones)
        self.assertEqual(len(tile.ColorZones), 3)


if __name__ == "__main__":
    unittest.main()
