# Implementation Plan: Optimize GenMaintSync Log Extraction & Eliminate CPU Peg

Resolve the runaway ~100% CPU burn in `genmaint_sync.py` by converting quadratic session extraction to an $O(N)$ linear state machine and adding file mtime caching.

## Problem Analysis
1. **Quadratic $O(N^2)$ While Loop**: In `extract_run_sessions()`, an engine run event without a matching stop event triggered a forward scan across the entire dataset. In large or fragmented log files with thousands of lines, this resulted in millions of operations, pegging Raspberry Pi CPU at ~100%.
2. **Unbounded Historical Disk Re-scanning**: On every 300-second daemon poll interval, `fetch_file_logs()` re-globbed and re-read all rotated historical log files (`/var/log/genmon.log*`) from disk, repeating the entire quadratic calculation over and over.

---

## Proposed Changes

### Addon Daemon Optimization

#### [MODIFY] [`addon/genmaint_sync.py`](file:///Users/oz/Develop/genmon/addon/genmaint_sync.py)
* **$O(N)$ State Machine**: Replace nested while loop in `extract_run_sessions()` with a single-pass linear loop tracking `current_start` and matching transitions in $O(N)$ time.
* **Incremental `mtime` Caching**: In `fetch_file_logs()`, only scan rotated logs on initial startup; on subsequent daemon ticks, check `os.path.getmtime()` and skip reading unchanged files.
* **Preserve Run Sessions Cache**: Maintain `_cached_run_sessions` across polling passes so new events are computed against complete session history with zero redundant computation.

### Automated Unit Tests

#### [MODIFY] [`tests/unit/test_genmaint_sync.py`](file:///Users/oz/Develop/genmon/tests/unit/test_genmaint_sync.py)
* Add `test_extract_run_sessions_linear_scale` benchmarking 10,000 log lines in under 0.2s.
* Add `test_extract_run_sessions_interleaved_events` testing multiple continuous running events, orphaned stops, and gap handling.

---

## Verification Plan

### Automated Tests
* Execute full test suite:
  ```bash
  python3 -m unittest discover -s tests/unit
  python3 -m unittest tests/integration/test_genserv_web_integration.py
  ```
* Verify Python syntax compilation:
  ```bash
  python3 -m py_compile addon/genmaint_sync.py
  ```

### Live Daemon Verification
* Verify one-shot execution completes in milliseconds:
  ```bash
  python3 addon/genmaint_sync.py -c /etc/genmon -1
  ```
* Verify CPU utilization of `genmaint_sync.service` drops to 0.0% via `top`.
