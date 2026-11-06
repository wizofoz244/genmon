#!/usr/bin/env python3
"""
Backup Progress Filter and Periodic Heartbeat Reporter.

Filters high-frequency progress output (such as rsync, dd, or image-backup)
and emits clean log messages at:
1. Defined percentage increments (default: every 5%, e.g., 5%, 10%, 15%...).
2. Defined time intervals (default: every 60 seconds) if progress is slow.
3. Preserves all standard informational, warning, and error messages.
"""

import argparse
import os
import re
import sys
import threading
import time
from typing import Optional


class BackupProgressFilter:
    """Filters stream progress and logs at 5% increments or 60s heartbeats."""

    def __init__(
        self,
        interval: int = 60,
        pct_step: int = 5,
        log_file: Optional[str] = None,
    ) -> None:
        """Initialize the progress filter.

        Args:
            interval: Seconds between periodic progress heartbeats.
            pct_step: Percentage delta required before logging a progress line.
            log_file: Optional path to write log lines to in addition to stdout.
        """
        self.interval = max(5, interval)
        self.pct_step = max(1, pct_step)
        self.log_file = log_file
        self.start_time = time.time()
        self.last_log_time = self.start_time
        self.last_pct = 0
        self.lock = threading.Lock()
        self.running = True

    def emit(self, msg: str) -> None:
        """Format and write message to stdout and optional log file.

        Args:
            msg: The message string to log.
        """
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        if not re.match(r"^\[\d{4}-\d{2}-\d{2}", msg):
            msg_low = msg.lower()
            if any(k in msg_low for k in ["error", "fatal", "critical", "exception", "failed"]):
                lvl = "ERROR"
            elif any(k in msg_low for k in ["warn", "warning"]):
                lvl = "WARN"
            else:
                lvl = "INFO"
            formatted = f"[{ts}] [{lvl}] {msg}"
        else:
            formatted = msg

        print(formatted, flush=True)

        if self.log_file:
            try:
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(formatted + "\n")
            except Exception:
                pass

    def heartbeat_loop(self) -> None:
        """Background thread that emits a heartbeat if no log output occurred for `interval`."""
        while self.running:
            time.sleep(2)
            with self.lock:
                if not self.running:
                    break
                now = time.time()
                if now - self.last_log_time >= self.interval:
                    elapsed = int(now - self.start_time)
                    m, s = divmod(elapsed, 60)
                    pct_info = f", {self.last_pct}%" if self.last_pct > 0 else ""
                    self.emit(f"Backup operation in progress (elapsed: {m}m {s:02d}s{pct_info})...")
                    self.last_log_time = now

    def process_line(self, line: str) -> None:
        """Process a single line from the incoming stream.

        Args:
            line: Raw line received from stdin.
        """
        clean = line.strip()
        if not clean:
            return

        now = time.time()
        m = re.search(r"(\d{1,3})%", clean)
        if m:
            pct = int(m.group(1))
            # Log on pct_step boundary (e.g. 5%, 10%, 15%...) or if interval elapsed with new pct
            if pct >= self.last_pct + self.pct_step or (
                now - self.last_log_time >= self.interval and pct != self.last_pct
            ):
                self.last_pct = (pct // self.pct_step) * self.pct_step
                self.last_log_time = now
                self.emit(f"Progress: {pct}% ({clean})")
        else:
            # Informational, warning, error, or prompt line
            self.last_log_time = now
            self.emit(clean)

    def run(self) -> None:
        """Read stdin handling both carriage return (\\r) and newline (\\n) delimiters."""
        hb_thread = threading.Thread(target=self.heartbeat_loop, daemon=True)
        hb_thread.start()

        buf = []
        try:
            while True:
                ch = sys.stdin.read(1)
                if not ch:
                    if buf:
                        with self.lock:
                            self.process_line("".join(buf))
                    break
                if ch in ("\r", "\n"):
                    if buf:
                        with self.lock:
                            self.process_line("".join(buf))
                        buf = []
                else:
                    buf.append(ch)
        finally:
            with self.lock:
                self.running = False


def main() -> None:
    """Parse CLI arguments and run the progress filter."""
    parser = argparse.ArgumentParser(
        description="Filter backup progress streams into 5% increments or 60s heartbeats."
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Seconds between periodic progress heartbeats (default: 60)",
    )
    parser.add_argument(
        "--pct-step",
        type=int,
        default=5,
        help="Percentage increment required to log progress (default: 5)",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Path to log file to append output to",
    )
    args = parser.parse_args()

    filter_app = BackupProgressFilter(
        interval=args.interval,
        pct_step=args.pct_step,
        log_file=args.log_file,
    )
    filter_app.run()


if __name__ == "__main__":
    main()
