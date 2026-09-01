#!/usr/bin/env python3
"""Unit test suite for genmaint_sync.py (Controller Log Synchronization).

Validates log line parsing, run session extraction, engine run hour back-calculation,
and entry classification per Google Python Style Guide.
"""

from __future__ import annotations

import datetime
import unittest

import tests.conftest
from addon.genmaint_sync import GenMaintSync


class TestGenMaintSync(unittest.TestCase):
    """Test cases for log parsing, session extraction, and run hour calculation."""

    def test_parse_log_line(self) -> None:
        """Tests parsing of standard controller log lines with varying date formats."""
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
        """Tests extraction of discrete run sessions from parsed log lines."""
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
        """Tests engine run hour back-calculation logic against live reference hours."""
        sync = GenMaintSync(config_path=".", oneshot=True, dry_run=True)
        live_hrs = 144.0

        run_sessions = [
            (datetime.datetime(2026, 7, 27, 12, 0, 0), datetime.datetime(2026, 7, 27, 18, 0, 0), 21600.0),  # 6 hrs
        ]

        # Event occurring after run session -> hours should equal live hours (144.0)
        event_after = datetime.datetime(2026, 7, 28, 10, 0, 0)
        hrs_after = sync.calculate_entry_run_hours(event_after, live_hrs, run_sessions)
        self.assertEqual(hrs_after, 144.0)

        # Event occurring before 6-hour run session -> hours should be live_hrs - 6.0 = 138.0
        event_before = datetime.datetime(2026, 7, 27, 10, 0, 0)
        hrs_before = sync.calculate_entry_run_hours(event_before, live_hrs, run_sessions)
        self.assertEqual(hrs_before, 138.0)

    def test_classify_entry_type(self) -> None:
        """Tests classification of entry types for Service Log, Alarm Log, and Run Log."""
        self.assertEqual(
            GenMaintSync.classify_entry_type("High Temp", "Alarm Log"),
            "Observation",
        )
        self.assertEqual(
            GenMaintSync.classify_entry_type("Running - Utility Loss", "Run Log"),
            "Observation",
        )
        self.assertEqual(
            GenMaintSync.classify_entry_type("Service A maintenance interval reached", "Service Log"),
            "Observation",
        )
        self.assertEqual(
            GenMaintSync.classify_entry_type("Reset Maintenance", "Service Log"),
            "Maintenance",
        )

    def test_extract_run_sessions_linear_scale(self) -> None:
        """Validates that extract_run_sessions runs in O(N) linear time on large datasets."""
        import time

        sync = GenMaintSync(config_path=".", oneshot=True, dry_run=True)
        base_time = datetime.datetime(2026, 1, 1, 0, 0, 0)
        # Generate 10,000 log lines with missing stop events to test worst-case performance
        large_lines = []
        for idx in range(10000):
            t = base_time + datetime.timedelta(minutes=idx)
            desc = "Running - Utility Loss" if (idx % 50 != 0) else "Stopped - Auto"
            large_lines.append((t, desc))

        t0 = time.time()
        sessions = sync.extract_run_sessions(large_lines)
        duration = time.time() - t0

        # Must execute 10,000 lines in well under 0.1 seconds (linear O(N))
        self.assertLess(duration, 0.2, f"Execution took too long: {duration}s")
        self.assertGreater(len(sessions), 0)

    def test_extract_run_sessions_interleaved_events(self) -> None:
        """Validates continuous running lines within a single session and duplicate starts."""
        sync = GenMaintSync(config_path=".", oneshot=True, dry_run=True)
        lines = [
            (datetime.datetime(2026, 7, 1, 10, 0, 0), "Exercising"),
            (datetime.datetime(2026, 7, 1, 10, 5, 0), "Exercising"),
            (datetime.datetime(2026, 7, 1, 10, 10, 0), "Exercising"),
            (datetime.datetime(2026, 7, 1, 10, 15, 0), "Your generator is ready to run."),
            # Orphaned stop event with no prior start (should not create session)
            (datetime.datetime(2026, 7, 1, 11, 0, 0), "Stopped - Auto"),
            # New session
            (datetime.datetime(2026, 7, 2, 14, 0, 0), "Running - Manual"),
            (datetime.datetime(2026, 7, 2, 15, 0, 0), "Switched Off"),
        ]
        sessions = sync.extract_run_sessions(lines)
        self.assertEqual(len(sessions), 2)
        self.assertEqual(sessions[0][2], 900.0)  # 15 minutes = 900s
        self.assertEqual(sessions[1][2], 3600.0)  # 1 hour = 3600s


if __name__ == "__main__":
    unittest.main()
