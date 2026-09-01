# Walkthrough - Suppress Spurious Utility Outage Notifications on Genmon Restart

Resolved Issue #49: Eliminated false-alarm utility outage / restoration alerts dispatched upon daemon startup caused by uninitialized baseline states in `GenNotify` and transient 0V Modbus readings during serial port handshake.

## Key Changes

### Notification Polling Engine
#### [genmonlib/mynotify.py](file:///Users/oz/Develop/genmon/genmonlib/mynotify.py)
- **Baseline State Tracking**: Guarded initial state handling in `GetOutageState()`. When `self.LastOutageStatus is None` and `OutageState is False` (normal utility power on boot), initialize `self.LastOutageStatus = False` without calling `ProcessEventData("OUTAGE", False, None)`.
- **Active Outage Preservation**: If Genmon starts during a genuine active outage (`OutageState is True`), `ProcessEventData("OUTAGE", True, None)` continues to be called, ensuring alerts are dispatched when power is actually down.
- **Extended Baseline Guards**: Guarded initial uninitialized states for `SOFTWAREUPDATE` (`LastSoftwareUpdateStatus`) and `PISTATE` (`LastPiState`) to prevent spurious startup notifications.

### Outage Debouncing & Configuration
#### [genmonlib/controller.py](file:///Users/oz/Develop/genmon/genmonlib/controller.py)
- Defaulted `OutageNoticeDelay` to `5` seconds (fallback when not configured), preventing transient 0V ADC/handshake readings during Modbus initialization from tripping immediate false outage detections.
- Added defensive attribute fallbacks in `__init__` (`bDisablePlatformStats`, `UseMetric`, `debug`, `PreferredNetworkAdapter`).

#### [conf/genmon.conf](file:///Users/oz/Develop/genmon/conf/genmon.conf)
- Documented `outage_notice_delay = 5` in `conf/genmon.conf` explaining how the 5-second debounce filters transient ADC and communication readings.

### Test Suite
#### [tests/unit/test_notify_outage.py](file:///Users/oz/Develop/genmon/tests/unit/test_notify_outage.py)
- Added 5 new unit tests:
  1. `test_outage_baseline_suppresses_spurious_restoration_on_start`: Verifies starting with normal utility power does not invoke `onutilitychange` / `OnOutage(False)`.
  2. `test_active_outage_on_startup_is_dispatched`: Verifies starting during an active outage triggers `onutilitychange(True)`.
  3. `test_outage_and_restoration_lifecycle`: Verifies full lifecycle transitions (`False -> True` and `True -> False`).
  4. `test_software_update_and_pi_state_startup_suppression`: Verifies clean baseline suppression for update and Pi health.
  5. `test_default_outage_notice_delay_is_five_seconds`: Verifies the 5-second debounce fallback in `GeneratorController`.

---

## Verification Results

### Automated Tests
- **New Unit Tests**:
  ```bash
  python3 -m unittest tests/unit/test_notify_outage.py
  # Ran 5 tests in 0.012s -> OK
  ```
- **Full Test Suite**:
  ```bash
  python3 -m unittest discover -s tests
  # Ran 114 tests in 1.760s -> OK (0 failures, 0 errors)
  ```
- **Bytecode Compilation**:
  ```bash
  python3 -m py_compile genmonlib/mynotify.py genmonlib/controller.py tests/unit/test_notify_outage.py
  # Clean compilation, exit code 0
  ```
