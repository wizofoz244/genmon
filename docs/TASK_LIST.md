# Task List: Chart Formatting, Smoothing & Readability Enhancements

- [x] **Phase 1: Planning & Setup**
  - [x] Create GitHub Issue #43 <!-- id: 1 -->
  - [x] Create & switch to feature branch `feature/chart-formatting-smoothing` <!-- id: 2 -->
  - [x] Persist SDLC docs (`docs/IMPLEMENTATION_PLAN.md`, `docs/TASK_LIST.md`) <!-- id: 3 -->
- [x] **Phase 2: Implementation**
  - [x] Implement moving average / smoothing computation in `static/js/genmon.js` <!-- id: 4 -->
  - [x] Add view mode toggle (`Trend`, `Dual`, `Raw`) and persistence in `Store` <!-- id: 5 -->
  - [x] Optimize fill and Y-axis scaling/padding for Pi Voltage in `static/js/genmon.js` <!-- id: 6 -->
  - [x] Add live summary stats bar (`Cur`, `Min`, `Max`, `Avg`) to chart headers in `static/js/genmon.js` <!-- id: 7 -->
  - [x] Add styling for stats badges and mode toggle pills in `static/css/genmon.css` <!-- id: 8 -->
- [x] **Phase 3: Verification & Automated Tests**
  - [x] Run python compile / sanity checks (`python3 -m py_compile ...`) <!-- id: 9 -->
  - [x] Add automated GUI test suite validating chart controls, mode switching, and stats badges <!-- id: 10 -->
  - [x] Execute Playwright / GUI tests locally (Headless Chrome) <!-- id: 11 -->
- [x] **Phase 4: Remote Push & Review**
  - [x] Create walkthrough artifact (`docs/WALKTHROUGH.md`) <!-- id: 12 -->
  - [x] Commit and push to `origin/feature/chart-formatting-smoothing` <!-- id: 13 -->
  - [x] Output secondary machine sync commands <!-- id: 14 -->
