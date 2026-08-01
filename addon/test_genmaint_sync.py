#!/usr/bin/env python3
"""Unit test suite for genmaint_sync.py."""

import datetime
import unittest
from addon.genmaint_sync import GenMaintSync


class TestGenMaintSync(unittest.TestCase):
    """Test cases for log parsing and run hour calculations."""

    def test_parse_log_line(self) -> None:
        """Tests parsing of standard controller log lines."""
        line1 = "07/27/26 12:05:08 Running - Utility Loss"
        parsed1 = GenMaintSync.parse_log_line(line1)
        self.assertIsNotNone(parsed1)
        self.assertEqual(parsed1[0], datetime.datetime(2026, 7, 27, 12, 5, 8))
        self.assertEqual(parsed1[1], "Running - Utility Loss")

        line2 = "07/25/2026 07:18:01 Exercising"
        parsed2 = GenMaintSync.parse_log_line(line2)
        self.assertIsNotNone(parsed2)
        self.assertEqual(parsed2[0], datetime.datetime(2026, 7, 25, 7, 18, 1))
        self.assertEqual(parsed2[1], "Exercising")

    def test_extract_run_sessions(self) -> None:
        """Tests extraction of run sessions from parsed lines."""
        lines = [
            (datetime.datetime(2026, 7, 25, 7, 0, 0), "Exercising"),
            (datetime.datetime(2026, 7, 25, 7, 12, 0), "Your generator is ready to run."),
            (datetime.datetime(2026, 7, 27, 12, 0, 0), "Running - Utility Loss"),
            (datetime.datetime(2026, 7, 27, 18, 0, 0), "Stopped - Auto"),
        ]
        sync = GenMaintSync(config_path=".", oneshot=True, dry_run=True)
        sessions = sync.extract_run_sessions(lines)
        self.assertEqual(len(sessions), 2)
        self.assertEqual(sessions[0][2], 720.0)  # 12 minutes = 720s
        self.assertEqual(sessions[1][2], 21600.0)  # 6 hours = 21600s

    def test_calculate_entry_run_hours(self) -> None:
        """Tests engine run hour calculation logic."""
        sync = GenMaintSync(config_path=".", oneshot=True, dry_run=True)
        live_hrs = 144.0

        run_sessions = [
            (datetime.datetime(2026, 7, 27, 12, 0, 0), datetime.datetime(2026, 7, 27, 18, 0, 0), 21600.0),  # 6 hrs
        ]

        # Event after run session -> hours equal live hours
        event_after = datetime.datetime(2026, 7, 28, 10, 0, 0)
        hrs_after = sync.calculate_entry_run_hours(event_after, live_hrs, run_sessions)
        self.assertEqual(hrs_after, 144.0)

        # Event before 6-hour run session -> hours should be live_hrs - 6.0 = 138.0
        event_before = datetime.datetime(2026, 7, 27, 10, 0, 0)
        hrs_before = sync.calculate_entry_run_hours(event_before, live_hrs, run_sessions)
        self.assertEqual(hrs_before, 138.0)

    def test_classify_entry_type(self) -> None:
        """Tests classification of entry types for Service Log, Alarm Log, and Run Log."""
        self.assertEqual(GenMaintSync.classify_entry_type("High Temp", "Alarm Log"), "Observation")
        self.assertEqual(GenMaintSync.classify_entry_type("Running - Utility Loss", "Run Log"), "Observation")
        self.assertEqual(GenMaintSync.classify_entry_type("Service A maintenance interval reached", "Service Log"), "Observation")
        self.assertEqual(GenMaintSync.classify_entry_type("Reset Maintenance", "Service Log"), "Maintenance")


if __name__ == "__main__":
    unittest.main()
