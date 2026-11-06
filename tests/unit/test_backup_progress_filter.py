#!/usr/bin/env python3
"""
Unit tests for backup_progress_filter.py.
"""

import io
import unittest
from unittest.mock import patch
from backup_progress_filter import BackupProgressFilter


class TestBackupProgressFilter(unittest.TestCase):
    """Test progress filtering and logging logic."""

    def test_percentage_increment_filtering(self):
        """Verify that progress is logged only at 5% increments."""
        messages = []
        filter_app = BackupProgressFilter(interval=60, pct_step=5)
        filter_app.emit = lambda msg: messages.append(msg)

        # Feed sequence of progress lines
        inputs = [
            "Initializing transfer...",
            "100M  1% 10MB/s 0:10",
            "200M  3% 10MB/s 0:09",
            "350M  5% 10MB/s 0:08",
            "400M  6% 10MB/s 0:08",
            "700M 10% 10MB/s 0:07",
            "800M 12% 10MB/s 0:06",
            "1.0G 15% 10MB/s 0:05",
            "Transfer completed.",
        ]
        for line in inputs:
            filter_app.process_line(line)

        self.assertIn("Initializing transfer...", messages)
        self.assertTrue(any("Progress: 5%" in m for m in messages))
        self.assertTrue(any("Progress: 10%" in m for m in messages))
        self.assertTrue(any("Progress: 15%" in m for m in messages))
        # Verify intermediate 1%, 3%, 6%, 12% are filtered out
        self.assertFalse(any("Progress: 1%" in m for m in messages))
        self.assertFalse(any("Progress: 3%" in m for m in messages))
        self.assertFalse(any("Progress: 6%" in m for m in messages))
        self.assertFalse(any("Progress: 12%" in m for m in messages))
        self.assertIn("Transfer completed.", messages)

    def test_run_with_carriage_returns(self):
        """Verify stream parsing with carriage returns from rsync/dd."""
        raw_stream = (
            "Starting\r"
            "50M 5% 10MB/s\r"
            "60M 6% 10MB/s\r"
            "100M 10% 10MB/s\r"
            "Done\n"
        )
        messages = []
        filter_app = BackupProgressFilter(interval=60, pct_step=5)
        filter_app.emit = lambda msg: messages.append(msg)

        with patch("sys.stdin", io.StringIO(raw_stream)):
            filter_app.run()

        self.assertIn("Starting", messages)
        self.assertTrue(any("Progress: 5%" in m for m in messages))
        self.assertTrue(any("Progress: 10%" in m for m in messages))
        self.assertFalse(any("Progress: 6%" in m for m in messages))
        self.assertIn("Done", messages)


if __name__ == "__main__":
    unittest.main()
