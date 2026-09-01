# Implementation Plan: Chart Formatting, Smoothing & Visual Readability Improvements

Enhance the readability of Genmon telemetry charts (specifically Pi Voltage and CPU Temp), addressing the "barcode" effect on Pi Voltage caused by high-frequency DVFS stepping, aggressive area fill, and tight vertical axis scaling.

## Problem Analysis
In the current implementation:
1. **Pi Voltage "Barcode" Effect**: Raspberry Pi dynamic frequency & voltage scaling (DVFS) rapidly switches between idle (~1.20–1.23 V) and boost (~1.34–1.35 V). In a 6-hour or 24-hour view, hundreds/thousands of transitions with `tension: 0` and `fill: true` (`backgroundColor: rgba(59,130,246,.12)`) turn the graph into solid vertical blue bars.
2. **Hyper-Tight Y-Axis Scale**: Dynamic auto-scaling without padding limits the Y-axis span to ~0.15 V, causing a normal minor stepping variation to consume 100% of the vertical canvas height.
3. **No Trend Line / Moving Average**: Users cannot discern general power sag or long-term baseline shifts amidst the raw switching noise.
4. **No Key Statistics**: Users must visually inspect and hover over points to guess current, minimum, maximum, and average values.

---

## User Review Required

> [!IMPORTANT]
> - Default display mode for Voltage will be **Trend** (moving average) with an interactive toggle for **Raw** and **Dual** (faint raw stepping in background + bold trend line).
> - Summary stats (`Cur`, `Min`, `Max`, `Avg`) will be displayed in a compact stats bar directly below the chart title.

---

## Proposed Changes

### Frontend Telemetry & Chart Rendering

#### [MODIFY] [`static/js/genmon.js`](file:///Users/oz/Develop/genmon/static/js/genmon.js)
* **Moving Average Algorithm**: Add rolling window smoothing based on the selected time span (e.g. 5 min window for 1h/6h, 15 min for 24h, 1 hr for 7d/30d).
* **Format Mode Toggle**:
  * Add mode toggle pills (`Trend`, `Dual`, `Raw`) on voltage and temperature charts.
  * Persist the user's preference in `Store` (localStorage).
* **Area Fill Optimization**:
  * Set `fill: false` for raw voltage square waves so lines do not merge into solid vertical blocks.
  * Use a subtle gradient only on smooth trend lines.
* **Y-Axis Scale Bounds & Padding**:
  * For voltage charts, enforce a minimum visual span (e.g., minimum 0.35 V span) with 10% padding so small 0.1 V shifts do not fill 100% of the chart height.
* **Summary Stats Header**:
  * Compute `current`, `min`, `max`, and `avg` for the visible time window.
  * Render a clean inline badge (e.g. `Cur: 1.34 V | Min: 1.23 V | Max: 1.35 V | Avg: 1.31 V`).

#### [MODIFY] [`static/css/genmon.css`](file:///Users/oz/Develop/genmon/static/css/genmon.css)
* Add styling for the chart stats banner (`.chart-stats`, `.chart-stat-badge`).
* Add styling for the format toggle pills (`.chart-mode-btn`).

---

## Verification Plan

### Automated Tests
* Run unit and lint checks:
  ```bash
  python3 -m py_compile genserv.py genmon.py
  ```
* Run existing test suite to ensure no regressions:
  ```bash
  pytest tests/unit/
  ```

### Manual & GUI Verification
* Test chart rendering across all time spans (`1h`, `6h`, `24h`, `7d`, `30d`).
* Verify toggling between `Trend`, `Dual`, and `Raw` modes.
* Verify live summary stats accurately update when changing time spans.
* Verify dark and light themes render stats and lines with high contrast and zero clutter.
