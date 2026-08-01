#!/usr/bin/env python3
"""Genmon Service Journal Synchronization Addon (genmaint_sync.py).

This module periodically checks the generator controller's 50-entry Run Log
and Alarm Log via the Genmon RPC interface. When new or updated log entries
are detected, it formats them into Service Journal entries (classified as
'Observation' types), calculates or interpolates the exact engine run hours
for each event, and appends them to maintlog.json while preventing duplicates.

Google Python Style Guide compliant:
- Explicit type annotations.
- Google-style docstrings (Args, Returns, Raises).
- Secure, robust file operations and error handling.
"""

import argparse
import datetime
import json
import os
import signal
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    # Add parent directory to sys.path to access genmonlib modules
    file_root = os.path.dirname(os.path.realpath(__file__))
    parent_root = os.path.abspath(os.path.join(file_root, os.pardir))
    if os.path.isdir(os.path.join(parent_root, "genmonlib")):
        sys.path.insert(1, parent_root)

    from genmonlib.myclient import ClientInterface
    from genmonlib.mycommon import MyCommon
    from genmonlib.myconfig import MyConfig
    from genmonlib.mylog import SetupLogger
    from genmonlib.mysupport import MySupport
    from genmonlib.program_defaults import ProgramDefaults

except Exception as import_err:
    print(
        f"\nError importing genmonlib dependencies: {import_err}\n"
        "Please ensure genmaint_sync.py is executed within the Genmon directory structure."
    )
    sys.exit(2)


class GenMaintSync(MySupport):
    """Monitors controller logs and synchronizes new entries into maintlog.json."""

    def __init__(
        self,
        host: str = ProgramDefaults.LocalHost,
        port: int = ProgramDefaults.ServerPort,
        config_path: str = ProgramDefaults.ConfPath,
        poll_interval: int = 60,
        oneshot: bool = False,
        dry_run: bool = False,
        log: Optional[Any] = None,
        console: Optional[Any] = None,
    ) -> None:
        """Initializes the GenMaintSync daemon/CLI instance.

        Args:
            host: IP address or hostname of the Genmon server.
            port: RPC port for Genmon server.
            config_path: Directory path containing Genmon configuration and log files.
            poll_interval: Seconds between log synchronization polls in daemon mode.
            oneshot: If True, performs a single sync execution and exits.
            dry_run: If True, parses and calculates entries without modifying maintlog.json.
            log: Optional file logger instance.
            console: Optional console logger instance.
        """
        super().__init__()
        self.host = host
        self.port = port
        self.config_path = config_path
        self.poll_interval = poll_interval
        self.oneshot = oneshot
        self.dry_run = dry_run
        self.log = log or SetupLogger("genmaint_sync", os.path.join(self.config_path, "genmaint_sync.log"))
        self.console = console or SetupLogger("genmaint_sync_console", "", stream=True)

        self.running = True
        self.maintlog_file = os.path.join(self.config_path, "maintlog.json")
        self.state_file = os.path.join(self.config_path, "maint_sync_state.json")
        self.client: Optional[ClientInterface] = None

    def log_info(self, msg: str) -> None:
        """Logs informational messages to both log file and console."""
        if self.log:
            self.log.info(msg)
        if self.console:
            self.console.info(msg)

    def log_error(self, msg: str) -> None:
        """Logs error messages to both log file and console."""
        if self.log:
            self.log.error(msg)
        if self.console:
            self.console.error(msg)

    def connect_client(self) -> bool:
        """Establishes ClientInterface connection to Genmon RPC daemon.

        Returns:
            True if connection established successfully, False otherwise.
        """
        try:
            self.client = ClientInterface(host=self.host, port=self.port, log=self.log)
            return True
        except Exception as err:
            self.log_error(f"Failed to connect to Genmon RPC server ({self.host}:{self.port}): {err}")
            return False

    def close_client(self) -> None:
        """Safely closes the ClientInterface RPC connection."""
        if self.client:
            try:
                self.client.Close()
            except Exception as err:
                self.log_error(f"Error closing RPC client connection: {err}")
            self.client = None

    def load_maintlog(self) -> List[Dict[str, Any]]:
        """Loads existing Service Journal entries from maintlog.json.

        Returns:
            List of maintenance log dictionaries.
        """
        if not os.path.isfile(self.maintlog_file):
            return []
        try:
            with open(self.maintlog_file, "r", encoding="utf-8") as infile:
                data = json.load(infile)
                if isinstance(data, list):
                    return data
        except Exception as err:
            self.log_error(f"Error reading {self.maintlog_file}: {err}")
        return []

    def load_state(self) -> Set[str]:
        """Loads previously processed log signatures from the state file.

        Returns:
            Set of unique log signatures already processed.
        """
        if not os.path.isfile(self.state_file):
            return set()
        try:
            with open(self.state_file, "r", encoding="utf-8") as infile:
                state_data = json.load(infile)
                if isinstance(state_data, list):
                    return set(state_data)
        except Exception as err:
            self.log_error(f"Error reading state file {self.state_file}: {err}")
        return set()

    def save_state(self, processed_signatures: Set[str]) -> None:
        """Atomically saves processed log signatures to state file.

        Args:
            processed_signatures: Set of processed entry signatures.
        """
        if self.dry_run:
            return
        try:
            dir_name = os.path.dirname(self.state_file) or "."
            with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, encoding="utf-8") as tf:
                json.dump(sorted(list(processed_signatures)), tf, indent=4)
                temp_path = tf.name
            os.replace(temp_path, self.state_file)
        except Exception as err:
            self.log_error(f"Error saving state file {self.state_file}: {err}")

    def save_maintlog(self, maint_entries: List[Dict[str, Any]]) -> bool:
        """Atomically writes updated entries list to maintlog.json.

        Args:
            maint_entries: List of maintenance log entry dictionaries.

        Returns:
            True if write succeeded, False otherwise.
        """
        if self.dry_run:
            self.log_info("[DRY-RUN] Skipping file save for maintlog.json.")
            return True

        try:
            dir_name = os.path.dirname(self.maintlog_file) or "."
            with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, encoding="utf-8") as tf:
                json.dump(maint_entries, tf, indent=4)
                temp_name = tf.name
            os.replace(temp_name, self.maintlog_file)
            self.log_info(f"Successfully updated {self.maintlog_file} ({len(maint_entries)} total entries).")
            return True
        except Exception as err:
            self.log_error(f"Error writing atomic update to {self.maintlog_file}: {err}")
            return False

    def fetch_controller_logs(self) -> Tuple[Optional[List[str]], Optional[List[str]]]:
        """Fetches raw Alarm Log and Run Log entries from Genmon RPC.

        Returns:
            Tuple of (alarm_log_lines, run_log_lines).
        """
        if not self.client:
            return None, None

        try:
            raw_response = self.client.ProcessMonitorCommand("logs_json")
            if not raw_response:
                return None, None

            if isinstance(raw_response, str):
                logs_data = json.loads(raw_response)
            else:
                logs_data = raw_response

            logs_dict = logs_data.get("Logs", {}) if isinstance(logs_data, dict) else {}

            alarm_log = logs_dict.get("Alarm Log", [])
            run_log = logs_dict.get("Run Log", [])

            return alarm_log, run_log

        except Exception as err:
            self.log_error(f"Error fetching logs via RPC: {err}")
            return None, None

    def fetch_live_run_hours(self) -> float:
        """Fetches the current live engine run hours from Genmon RPC.

        Returns:
            Float representing total engine run hours, defaulting to 0.0 on error.
        """
        if not self.client:
            return 0.0

        try:
            status_resp = self.client.ProcessMonitorCommand("status_json")
            if status_resp:
                data = json.loads(status_resp) if isinstance(status_resp, str) else status_resp
                status_dict = data.get("Status", {}) if isinstance(data, dict) else {}
                gen_dict = status_dict.get("Generator Status", {})
                run_hrs_str = gen_dict.get("Total Run Hours", "0.0")
                # Parse numeric value from string (e.g. "138.9 h" -> 138.9)
                clean_val = "".join(c for c in str(run_hrs_str) if c.isdigit() or c == ".")
                return round(float(clean_val), 1) if clean_val else 0.0
        except Exception as err:
            self.log_error(f"Error fetching live run hours: {err}")
        return 0.0

    @staticmethod
    def parse_log_line(log_line: str) -> Optional[Tuple[datetime.datetime, str]]:
        """Parses a controller log line string into datetime and description.

        Expected log line formats:
        - "07/27/26 12:05:08 Running - Utility Loss"
        - "07/25/2026 07:18:01 Exercising"

        Args:
            log_line: Raw string line from controller log.

        Returns:
            Tuple of (datetime_obj, event_description) or None if unparseable.
        """
        parts = log_line.strip().split(maxsplit=2)
        if len(parts) < 3:
            return None

        date_part, time_part, desc = parts[0], parts[1], parts[2]
        dt_str = f"{date_part} {time_part}"

        # Attempt common date formats
        for fmt in ("%m/%d/%y %H:%M:%S", "%m/%d/%Y %H:%M:%S", "%m/%d/%y %H:%M", "%m/%d/%Y %H:%M"):
            try:
                dt = datetime.datetime.strptime(dt_str, fmt)
                return dt, desc.strip()
            except ValueError:
                continue

        return None

    def calculate_entry_run_hours(
        self,
        event_dt: datetime.datetime,
        live_hrs: float,
        run_sessions: List[Tuple[datetime.datetime, datetime.datetime, float]],
    ) -> float:
        """Calculates exact engine run hours at the time of an event.

        Uses current live run hours and subtracts engine runtime accumulated
        in sessions between event_dt and current time.

        Args:
            event_dt: Datetime of the target event.
            live_hrs: Current total engine run hours.
            run_sessions: List of (start_dt, end_dt, duration_seconds) for run sessions.

        Returns:
            Calculated run hours rounded to 1 decimal place.
        """
        now = datetime.datetime.now()
        if event_dt >= now or not run_sessions:
            return round(live_hrs, 1)

        # Calculate run seconds that occurred AFTER event_dt up to now
        sec_after_event = 0.0
        for start_t, end_t, dur_sec in run_sessions:
            if end_t <= event_dt:
                continue
            elif start_t >= event_dt:
                sec_after_event += dur_sec
            else:
                # Event happened in the middle of this session
                overlap_sec = (end_t - event_dt).total_seconds()
                sec_after_event += max(0.0, overlap_sec)

        hrs_after = sec_after_event / 3600.0
        event_hrs = max(0.0, live_hrs - hrs_after)
        return round(event_hrs, 1)

    def extract_run_sessions(
        self, parsed_run_lines: List[Tuple[datetime.datetime, str]]
    ) -> List[Tuple[datetime.datetime, datetime.datetime, float]]:
        """Extracts engine run sessions from parsed run log lines.

        Args:
            parsed_run_lines: List of (datetime, description) sorted chronologically.

        Returns:
            List of (start_time, end_time, duration_seconds).
        """
        sessions = []
        i = 0
        n = len(parsed_run_lines)
        while i < n:
            dt, desc = parsed_run_lines[i]
            desc_lower = desc.lower()
            if any(k in desc_lower for k in ["exercising", "utility loss", "manual", "running"]):
                start_t = dt
                end_t = None
                j = i + 1
                while j < n:
                    dt_next, desc_next = parsed_run_lines[j]
                    desc_next_lower = desc_next.lower()
                    if desc_next in ["Your generator is ready to run.", "Switched Off"] or "stopped" in desc_next_lower:
                        end_t = dt_next
                        break
                    j += 1
                if end_t:
                    dur_sec = (end_t - start_t).total_seconds()
                    if dur_sec > 0:
                        sessions.append((start_t, end_t, dur_sec))
                    i = max(j, i + 1)
                else:
                    i += 1
            else:
                i += 1

        return sessions

    def sync_logs(self) -> int:
        """Executes one log synchronization pass.

        Returns:
            Count of new entries added to maintlog.json.
        """
        alarm_lines, run_lines = self.fetch_controller_logs()
        if alarm_lines is None and run_lines is None:
            self.log_info("Unable to fetch logs from controller. Skipping sync pass.")
            return 0

        live_hrs = self.fetch_live_run_hours()
        existing_maint = self.load_maintlog()
        processed_state = self.load_state()

        # Existing entry keys for deduplication
        existing_keys: Set[Tuple[str, str]] = set()
        for e in existing_maint:
            dt_str = e.get("date", "").strip()
            comment = e.get("comment", "").strip()
            if dt_str and comment:
                existing_keys.add((dt_str, comment))

        # Parse and collect all valid log lines
        all_candidates: List[Tuple[datetime.datetime, str, str]] = []  # (dt, desc, source_type)

        if alarm_lines:
            for line in alarm_lines:
                res = self.parse_log_line(line)
                if res:
                    all_candidates.append((res[0], res[1], "Alarm Log"))

        parsed_run_lines: List[Tuple[datetime.datetime, str]] = []
        if run_lines:
            for line in run_lines:
                res = self.parse_log_line(line)
                if res:
                    all_candidates.append((res[0], res[1], "Run Log"))
                    parsed_run_lines.append((res[0], res[1]))

        # Sort chronologically
        all_candidates.sort(key=lambda x: x[0])
        parsed_run_lines.sort(key=lambda x: x[0])

        run_sessions = self.extract_run_sessions(parsed_run_lines)

        new_entries: List[Dict[str, Any]] = []

        for event_dt, desc, src in all_candidates:
            formatted_date = event_dt.strftime("%m/%d/%Y %H:%M")
            entry_key = (formatted_date, desc)
            sig_str = f"{formatted_date}|{desc}"

            if entry_key in existing_keys or sig_str in processed_state:
                continue

            # Calculate engine run hours
            hrs = self.calculate_entry_run_hours(event_dt, live_hrs, run_sessions)

            entry = {
                "date": formatted_date,
                "type": "Observation",
                "hours": hrs,
                "comment": desc,
            }

            new_entries.append(entry)
            existing_keys.add(entry_key)
            processed_state.add(sig_str)

        if not new_entries:
            self.log_info("No new log entries detected.")
            return 0

        self.log_info(f"Detected {len(new_entries)} new log entries to add to Service Journal.")
        for e in new_entries:
            self.log_info(f"  + [{e['date']}] Hours: {e['hours']} | Type: {e['type']} | Comment: {e['comment']}")

        # Append new entries and sort full maintenance log chronologically by date
        combined_maint = existing_maint + new_entries

        def parse_maint_date(e: Dict[str, Any]) -> datetime.datetime:
            d_str = e.get("date", "")
            for fmt in ("%m/%d/%Y %H:%M", "%m/%d/%Y"):
                try:
                    return datetime.datetime.strptime(d_str, fmt)
                except ValueError:
                    continue
            return datetime.datetime.min

        combined_maint.sort(key=parse_maint_date)

        if self.save_maintlog(combined_maint):
            self.save_state(processed_state)
            return len(new_entries)

        return 0

    def run(self) -> None:
        """Runs the synchronization service loop or one-shot pass."""
        self.log_info(f"Starting GenMaintSync (Host: {self.host}, Port: {self.port}, Interval: {self.poll_interval}s)")

        if not self.connect_client():
            self.log_error("Could not connect to Genmon daemon. Exiting.")
            sys.exit(1)

        try:
            if self.oneshot:
                added_count = self.sync_logs()
                self.log_info(f"One-shot sync complete. Added {added_count} entries.")
            else:
                while self.running:
                    self.sync_logs()
                    time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            self.log_info("Keyboard interrupt received. Stopping.")
        except Exception as err:
            self.log_error(f"Unexpected error in main run loop: {err}")
        finally:
            self.close_client()
            self.log_info("GenMaintSync terminated cleanly.")


def main() -> None:
    """CLI entrypoint for genmaint_sync.py."""
    parser = argparse.ArgumentParser(
        description="Automated synchronization of controller Run & Alarm logs to Genmon Service Journal (maintlog.json)."
    )
    parser.add_argument(
        "-a", "--address", default=ProgramDefaults.LocalHost, help="Genmon server IP address or hostname."
    )
    parser.add_argument(
        "-p", "--port", type=int, default=ProgramDefaults.ServerPort, help="Genmon server RPC port."
    )
    parser.add_argument(
        "-c", "--configpath", default=ProgramDefaults.ConfPath, help="Path to Genmon configuration folder."
    )
    parser.add_argument(
        "-i", "--interval", type=int, default=60, help="Polling interval in seconds for daemon mode."
    )
    parser.add_argument(
        "-1", "--oneshot", action="store_true", help="Perform a single synchronization pass and exit."
    )
    parser.add_argument(
        "-d", "--dry-run", action="store_true", help="Parse and calculate log entries without modifying files."
    )

    args = parser.parse_args()

    # Handle termination signals
    sync_instance: Optional[GenMaintSync] = None

    def signal_handler(signum: int, frame: Any) -> None:
        if sync_instance:
            sync_instance.running = False
            sync_instance.log_info(f"Signal {signum} received, stopping service...")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    sync_instance = GenMaintSync(
        host=args.address,
        port=args.port,
        config_path=args.configpath,
        poll_interval=args.interval,
        oneshot=args.oneshot,
        dry_run=args.dry_run,
    )

    sync_instance.run()


if __name__ == "__main__":
    main()
