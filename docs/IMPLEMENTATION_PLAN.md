# Implementation Plan: Session Auth Loop, Service Worker Fallback & Connection Starvation Fixes

Resolve authentication loop redirects, Service Worker query parameter cache misses, Tailscale cloud proxy restarts, HTTP/1.1 connection pool starvation, and Android notification tag collapsing.

## Problem Analysis
1. **Unauthenticated API Responses**: When a session expired or unauthenticated API calls were made to `/cmd/<command>`, `genserv.py` rendered the full HTML login page with HTTP 200 OK. Client-side AJAX parsed this as success or string data, causing redirection loops back to `/` instead of cleanly logging out via `/logout`.
2. **Service Worker Query Parameter Cache Misses**: `caches.match(req)` in `static/sw.js` evaluated full request URLs including cache-busting `?v=...` query strings. Missing query string normalization caused asset cache misses.
3. **HTTP/1.1 6-Connection Starvation**: On initial dashboard load, Genmon fired 9+ simultaneous heavy AJAX queries (`power_log_json=43200`, `sensor_log_json`, `script_logs_json`, `services_status_json`, `gui_status_json`, `status_json`). Chrome restricts HTTP/1.1 to 6 concurrent sockets, starving queued status telemetry and tripping false "Connection Lost" banners.
4. **Tailscale Funnel 60s Proxy Downtime on Restart**: `startgenmon.sh restart` executed `tailscale funnel reset`, tearing down global Tailscale cloud edge proxies and TLS sessions on every restart.
5. **Android Notification Collapsing**: Static `tag: 'genmon-push-alert'` caused Android notification manager to overwrite earlier notifications in-place.
6. **Accessibility Form Labels**: Missing `for="..."` attributes on `<label>` elements in the Web Push preferences modal triggered DevTools accessibility warnings.

---

## Proposed Changes

### Backend Authentication & Daemon Control

#### [MODIFY] [`genserv.py`](file:///Users/oz/Develop/genmon/genserv.py)
* Return `401 Unauthorized` JSON payload (`{"status": "error", "message": "Authentication required", "auth": False}`) on unauthenticated `/cmd/<command>` requests.

#### [MODIFY] [`startgenmon.sh`](file:///Users/oz/Develop/genmon/startgenmon.sh)
* Preserve active Tailscale Funnel / Serve configuration on restart; add `-t` / `--tailscale-reset` opt-in flag.

#### [MODIFY] [`addon/genwebpush.py`](file:///Users/oz/Develop/genmon/addon/genwebpush.py)
* Add unique timestamped notification tags (`genmon-{category}-{timestamp}`) to push payloads.

### Frontend UI, Telemetry & Service Worker

#### [MODIFY] [`static/js/genmon.js`](file:///Users/oz/Develop/genmon/static/js/genmon.js)
* Detect 401 HTTP status and invoke `window.location.replace('/logout')`.
* Increase `ajaxTimeout` from 10s to 25s for WAN/Funnel stability.
* Stagger heavy 30-day chart and auxiliary tile requests to prevent HTTP/1.1 socket exhaustion.
* Eliminate redundant startup status telemetry polling.

#### [MODIFY] [`static/sw.js`](file:///Users/oz/Develop/genmon/static/sw.js)
* Add `{ ignoreSearch: true }` to `caches.match()`.
* Update notification tag to unique timestamped identifier.
* Bump cache name to `genmon-v16`.

#### [MODIFY] [`static/js/pwa-push.js`](file:///Users/oz/Develop/genmon/static/js/pwa-push.js)
* Defer secondary modal preference fetches to prioritize initial page boot bandwidth.

#### [MODIFY] [`templates/index.html`](file:///Users/oz/Develop/genmon/templates/index.html)
* Add explicit `for="..."` attributes linking all 13 form labels in `#pwa-push-modal` to input IDs.

---

## Verification Plan

### Automated Tests
* Execute unit test suite and integration tests:
  ```bash
  python3 -m unittest discover -s tests/unit
  python3 -m unittest tests/integration/test_genserv_web_integration.py
  ```
* Verify Python syntax compilation:
  ```bash
  python3 -m py_compile genserv.py addon/genwebpush.py
  ```
* Validate bash script syntax:
  ```bash
  bash -n startgenmon.sh
  ```
