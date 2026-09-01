# Task List - Suppress Spurious Utility Outage Notifications on Restart (Issue #49)

- [ ] 1. Update `genmonlib/mynotify.py` <!-- id: 1 -->
  - [ ] 1.1 In `GetOutageState()`, guard `LastOutageStatus is None and not OutageState` to set baseline `LastOutageStatus = False` without dispatching event <!-- id: 1.1 -->
  - [ ] 1.2 In `GetMonitorState()`, guard `LastSoftwareUpdateStatus` and `LastPiState` against uninitialized false-positive notifications <!-- id: 1.2 -->
- [ ] 2. Update `genmonlib/controller.py` and `conf/genmon.conf` <!-- id: 2 -->
  - [ ] 2.1 Set default `outage_notice_delay` to 5 seconds in `genmonlib/controller.py` <!-- id: 2.1 -->
  - [ ] 2.2 Add and document `outage_notice_delay = 5` in `conf/genmon.conf` <!-- id: 2.2 -->
- [ ] 3. Author Unit Tests <!-- id: 3 -->
  - [ ] 3.1 Create `tests/unit/test_notify_outage.py` verifying startup baseline suppression and active outage detection <!-- id: 3.1 -->
  - [ ] 3.2 Verify test coverage and pass status <!-- id: 3.2 -->
- [ ] 4. Documentation & Git Sync <!-- id: 4 -->
  - [ ] 4.1 Update `docs/WALKTHROUGH.md` <!-- id: 4.1 -->
  - [ ] 4.2 Auto-commit and push to `origin/fix/outage-notification-on-restart` <!-- id: 4.2 -->
