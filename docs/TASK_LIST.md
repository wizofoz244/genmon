# Task List: Global Server-Side Script Log Error Acknowledgment

- [x] **Phase 1: Planning & Issue Tracking**
  - [x] Create GitHub Issue #47 <!-- id: 1 -->
  - [x] Create dedicated branch `feature/server-side-log-acknowledgment` <!-- id: 2 -->
  - [x] Persist SDLC documentation in `docs/` <!-- id: 3 -->
- [x] **Phase 2: Implementation**
  - [x] Implement thread-safe storage helpers (`get_script_log_acks_path`, `load_script_log_acks`, `save_script_log_ack`) in `genserv.py` <!-- id: 4 -->
  - [x] Support legacy `ui_prefs` migration from `genmon.conf` <!-- id: 5 -->
  - [x] Parse line timestamps against acknowledgment epoch in `get_script_logs_json` <!-- id: 6 -->
  - [x] Add `/cmd/ack_script_log?log=<key>` endpoint in `genserv.py` <!-- id: 7 -->
  - [x] Auto-acknowledge routines upon clearing in `clear_script_log_json` <!-- id: 8 -->
  - [x] Update frontend Script Logs page to call `/cmd/ack_script_log` and bind to server status <!-- id: 9 -->
  - [x] Update Dashboard health tile to use server-authoritative status, eliminating race conditions <!-- id: 10 -->
- [x] **Phase 3: Verification & Automated Tests**
  - [x] Author comprehensive unit tests (`tests/unit/test_server_log_ack.py`) <!-- id: 11 -->
  - [x] Author end-to-end browser GUI tests (`tests/gui/test_script_logs_gui.py`) <!-- id: 12 -->
  - [x] Execute full unit & GUI test suite (109 unit tests + 7 GUI tests passing 100%) <!-- id: 13 -->
  - [x] Compile and verify all Python syntax <!-- id: 14 -->
- [ ] **Phase 4: Remote Push & Review**
  - [x] Save walkthrough artifact (`docs/WALKTHROUGH.md`) <!-- id: 15 -->
  - [ ] Commit and push all changes to `origin/feature/server-side-log-acknowledgment` <!-- id: 16 -->
  - [ ] Proactively open Pull Request linking Issue #47 <!-- id: 17 -->

