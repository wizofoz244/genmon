# Implementation Plan - Suppress Spurious Utility Outage Notifications on Restart

Address spurious "Genmon Utility Outage" push notifications dispatched to subscribers upon Genmon daemon restart (Issue #49).

## Problem & Background

When Genmon restarts (via `startgenmon.sh restart`, web UI restart, or service restart), users occasionally receive a push notification titled **"Genmon Utility Outage"** (typically with body **"Utility Power RESTORED."**, or transiently **"Utility Power OUTAGE Detected!"** followed seconds later by restoration).

### Root Causes
1. **Uninitialized `LastOutageStatus` in `GenNotify` (`genmonlib/mynotify.py`)**:
   - `GenNotify` starts with `self.LastOutageStatus = None`.
   - On the first polling cycle, if utility power is normal (`OutageState = False`), `ProcessEventData` checks `lastvalue == eventdata` (`None == False`), which evaluates to `False`.
   - It treats this startup baseline reading as an event transition, invoking `OnOutage(False)` -> `SendWebPushPayload("Genmon Utility Outage", "Utility Power RESTORED.", category="outage")`.
2. **Transient 0V Reading on Serial Modbus Startup Handshake (`genmonlib/controller.py`, `genmonlib/generac_evolution.py`)**:
   - Register `0009` (Utility Voltage) can momentarily report 0V or encounter a port sync delay during `InitDevice`.
   - With `outage_notice_delay = 0` (default), `0V < 143V` immediately sets `self.SystemInOutage = True`, triggering an active outage alert before nominal voltage (240V) is read seconds later.

## Proposed Changes

### 1. Notification Event Dispatch Engine (`genmonlib/mynotify.py`)
- In `GetOutageState()`, guard the initial poll when `self.LastOutageStatus is None`.
  - If `OutageState is False` (utility power normal on boot), initialize `self.LastOutageStatus = False` without calling `ProcessEventData("OUTAGE", False, None)`.
  - If `OutageState is True` (daemon booted during a real active outage), dispatch `ProcessEventData("OUTAGE", True, None)` so active outage alerts are preserved.
- Apply similar initial-baseline guards for `SOFTWAREUPDATE` and `PISTATE` to prevent spurious startup alerts.

### 2. Controller Outage Filtering (`genmonlib/controller.py` & `conf/genmon.conf`)
- In `genmonlib/controller.py`, update the default `outage_notice_delay` fallback from `0` to `5` seconds to filter momentary 0V ADC/handshake readings.
- In `conf/genmon.conf`, document `outage_notice_delay = 5`.

### 3. Unit & Integration Tests (`tests/unit/test_notify_outage.py`)
- Author comprehensive tests in `tests/unit/test_notify_outage.py`:
  - Verify clean startup with normal utility power (`OutageState = False`) does NOT dispatch `onutilitychange` / `OnOutage(False)`.
  - Verify startup during active outage (`OutageState = True`) DOES dispatch `onutilitychange(True)`.
  - Verify subsequent transitions (`False -> True` and `True -> False`) properly dispatch outage and restoration callbacks.
  - Verify `outage_notice_delay` default filters transient 0V readings.

## Verification Plan

### Automated Tests
- Run `python3 -m unittest tests/unit/test_notify_outage.py`
- Run full test suite `python3 -m unittest discover -s tests`
- Run `python3 -m py_compile genmonlib/mynotify.py genmonlib/controller.py`

### Manual / Integration Verification
- Inspect output logs and ensure 0 regression across existing 109 tests.
