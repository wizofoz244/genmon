# Genmon Web Push Notification System: Architecture & Walkthrough Guide

This document provides a comprehensive technical walkthrough and operational reference for Genmon's native Progressive Web App (PWA) Web Push Notification subsystem.

---

## 1. Executive Overview & Architecture

The Genmon Web Push Notification system enables real-time, encrypted push notifications delivered directly to desktop and mobile lockscreens (iOS, Android, macOS, Windows, Linux) without relying on third-party SaaS notification brokers (e.g., Pushover, Twilio, Slack).

### High-Level Architecture Diagram

```
 +---------------------------------------------------------------------------------------+
 |                                 Raspberry Pi (Genmon Host)                            |
 |                                                                                       |
 |  +-----------------------+     IPC Socket      +-----------------------------------+  |
 |  |     genmon.py         | -----------------> |       addon/genwebpush.py         |  |
 |  |  (Generator Monitor)  |                    |    (Web Push Daemon & Engine)     |  |
 |  +-----------------------+                    +-----------------------------------+  |
 |              |                                          |                     |       |
 |              v                                          | (Crypto / VAPID)    |       |
 |  +-----------------------+    Internal Flask Route      v                     v       |
 |  |      genserv.py       | <--------------------- /etc/genmon/        /etc/genmon/    |
 |  |   (Web UI & Server)   |                       genwebpush.conf   webpush_subscriptions|
 |  +-----------------------+                                            .json           |
 |              |                                                                        |
 |              | Internal HTTP (Port 8000)                                              |
 |              v                                                                        |
 |  +----------------------------------------------------+                               |
 |  | Tailscale Funnel / Reverse Proxy (HTTPS Port 443)  |                               |
 |  +----------------------------------------------------+                               |
 +---------------------------------------------------------------------------------------+
                                        |
                            Public Internet (W3C Web Push)
                                        |
     +----------------------------------+-----------------------------------+
     |                                  |                                   |
     v                                  v                                   v
+------------------------+  +------------------------+  +------------------------+
| Google FCM             |  | Apple APNs             |  | Mozilla Push Service   |
| (fcm.googleapis.com)   |  | (push.apple.com)       |  | (push.services.mozilla)|
+------------------------+  +------------------------+  +------------------------+
     |                                  |                                   |
     v                                  v                                   v
+------------------------+  +------------------------+  +------------------------+
| Android Devices        |  | iOS Devices (PWA)      |  | Desktop Browsers       |
| & Chrome Browsers      |  | & Safari (macOS)       |  | (Firefox, Edge, etc.)  |
+------------------------+  +------------------------+  +------------------------+
```

### Core Design Principles
1. **Zero External SaaS Dependencies**: All encryption, VAPID token generation, and push dispatches originate locally on the Raspberry Pi. No monthly subscriptions, external accounts, or rate-limited API keys are required.
2. **End-to-End Cryptographic Security**: Push payloads are signed using Voluntary Application Server Identification (VAPID, RFC 8292) and encrypted using NIST P-256 elliptic curve cryptography before transmission through push delivery gateways.
3. **Multi-Device Support**: Users can register multiple mobile phones, tablets, and desktop workstations with custom labels and per-device lifecycle tracking.
4. **Native Mobile Experience**: Operates seamlessly within standalone PWA installations on iOS (iOS 16.4+ Add-to-Home-Screen) and Android, vibrating and displaying badges on device lockscreens even when the browser is closed.

---

## 2. VAPID RFC 8292 Cryptographic Architecture

Web Push relies on the Voluntary Application Server Identification (VAPID) protocol defined in **RFC 8292**. VAPID allows application servers (Genmon) to authenticate themselves to push service endpoints (Google FCM, Apple APNs, Mozilla Autopush) without requiring proprietary vendor credentials.

### NIST P-256 Key Generation (`addon/genwebpush.py`)

When `genwebpush` or `genserv` initializes, `EnsureVapidKeys()` checks `/etc/genmon/genwebpush.conf` (or `conf/genwebpush.conf` fallback) for existing keys. If keys are missing, it executes an automated generation routine:

1. **Primary Method (`cryptography` Python Library)**:
   - Generates an Elliptic Curve (EC) private key using the `SECP256R1` curve (NIST P-256):
     ```python
     private_key = ec.generate_private_key(ec.SECP256R1())
     public_key = private_key.public_key()
     ```
   - Exports the raw 32-byte private integer and the 65-byte uncompressed EC point (`X962` format):
     ```python
     raw_priv = private_key.private_numbers().private_value.to_bytes(32, "big")
     raw_pub = public_key.public_bytes(
         serialization.Encoding.X962,
         serialization.PublicFormat.UncompressedPoint
     )
     ```
   - Encodes both keys using URL-safe Base64 with stripped padding (`.rstrip("=")`).

2. **Fallback Method (OpenSSL CLI)**:
   - If Python `cryptography` is unavailable, `genwebpush.py` falls back to the system OpenSSL binary:
     ```bash
     openssl ecparam -name prime256v1 -genkey -noout -out /tmp/vapid_priv.pem
     openssl ec -in /tmp/vapid_priv.pem -pubout -outform DER
     openssl ec -in /tmp/vapid_priv.pem -outform DER
     ```
   - Extracts the raw 65-byte uncompressed public key point and 32-byte private key slice from the DER structures.

3. **Configuration Storage**:
   The generated keys and claims are written back to `genwebpush.conf`:
   ```ini
   [genwebpush]
   vapid_public_key = BJ7x...<Base64URL 65-byte uncompressed point>...
   vapid_private_key = 8q2k...<Base64URL 32-byte raw scalar>...
   vapid_claims_sub = mailto:admin@genmon.local
   subscriptions_file = /etc/genmon/webpush_subscriptions.json
   ```

4. **Frontend Public Key Distribution**:
   - The browser requests `GET /api/webpush/vapid_key`.
   - The client-side script (`static/js/pwa-push.js`) converts the Base64URL public key into a `Uint8Array` via `urlBase64ToUint8Array()` and passes it to `registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: ... })`.

---

## 3. Subscription Persistence & Storage

### Storage File & Thread Locking
Subscriptions are persisted to disk in JSON format. The location is determined by `GetSubscriptionsFile()`:
1. Configured path in `subscriptions_file` (default: `/etc/genmon/webpush_subscriptions.json`).
2. Fallback path: `/etc/genmon/data/webpush_subscriptions.json` or `<project_root>/data/webpush_subscriptions.json`.

All read and write operations are guarded by a threading lock (`sub_lock = threading.Lock()`) to guarantee consistency during concurrent HTTP requests from `genserv.py` and event dispatches from `genwebpush.py`.

### Subscription Record Schema
```json
[
  {
    "endpoint": "https://fcm.googleapis.com/fcm/send/eA...7z",
    "keys": {
      "p256dh": "BNc...<Client Public Key>...",
      "auth": "A8...<Client Auth Secret>..."
    },
    "user_agent": "Mozilla/5.0 (Linux; Android 14; SM-S918U Build/UP1A...) AppleWebKit/537.36...",
    "device_name": "SM-S918U (Android)",
    "added_time": "2026-08-17T18:30:00.000Z"
  }
]
```

### Automatic Dead Endpoint Pruning (HTTP 404 / 410)
When a user clears browser data or revokes notification permissions, push delivery gateways return:
- **HTTP 404 Not Found**: Endpoint is invalid.
- **HTTP 410 Gone**: Subscription has expired or been cancelled.

During `SendWebPushPayload()`, any response matching `404` or `410` triggers immediate unregistration via `RemoveSubscription(endpoint)` without manual administrative cleanup.

---

## 4. Dynamic Device Labeling & Hardware Auto-Detection

To give operators full visibility into which physical devices are receiving generator alerts, Genmon combines client-side User-Agent parsing with backend push gateway categorization.

### Client-Side Hardware Model Detection (`static/js/pwa-push.js`)
When opening the Push Alert Preferences modal (`#pwa-push-modal`), `autoFillDeviceName()` inspects `navigator.userAgent`:

```javascript
getDefaultDeviceName: function() {
    var ua = navigator.userAgent;
    var match;
    // Android device model regex
    if (/android/i.test(ua)) {
        match = ua.match(/;\s*([^;]+)\s+Build\//i);
        return match ? match[1] + ' (Android)' : 'Android Phone';
    }
    // Apple iOS devices
    if (/iphone/i.test(ua)) return "iPhone";
    if (/ipad/i.test(ua)) return "iPad";
    // Desktop platforms
    if (/macintosh|mac os/i.test(ua)) return "Mac Desktop";
    if (/windows/i.test(ua)) return "Windows PC";
    return "Web Browser";
}
```

- **Examples of Auto-Detected Labels**:
  - `SM-S918U (Android)` (Samsung Galaxy S23 Ultra)
  - `Pixel 8 (Android)` (Google Pixel)
  - `iPhone` (Apple iOS)
  - `Mac Desktop` (Apple Safari / Chrome on macOS)
  - `Windows PC` (Microsoft Windows)
- Users can override the auto-detected model name with custom nicknames (e.g., `"Living Room Tablet"`, `"Oz's Work Phone"`) prior to clicking **Enable Push Alerts**.

### Backend Push Gateway Identification (`addon/genwebpush.py`)
`GetSubscriptionsList()` inspects the push endpoint URL and attaches visual badges and delivery service descriptors:

| Endpoint Substring | Visual Badge | Gateway Service | Typical Clients |
| :--- | :--- | :--- | :--- |
| `fcm.googleapis.com` | `📱 Android` / `💻 Desktop` | `Google Push (FCM)` | Chrome, Android, Edge |
| `apple.com` / `push.apple.com` | `📱 iOS Safari` / `💻 Mac Desktop` | `Apple Push (APNs)` | iOS 16.4+ PWA, Safari macOS |
| `mozilla.com` / `push.services.mozilla` | `🌐 Web Browser` | `Mozilla Push` | Mozilla Firefox |
| *other* | `🌐 Web Browser` | `Web Push` | Standard W3C Push Service |

---

## 5. Tailscale Funnel & Let's Encrypt HTTPS Deployment

### W3C Push API Secure Context Requirement
The W3C Web Push and Service Worker specifications mandate a **Secure Context** (`HTTPS` or `http://localhost`). Browsers strictly enforce the following security rules:
- **Chrome / Chromium**: Prohibits PushManager subscription on raw self-signed IP addresses (`https://192.168.x.x/`). Attempting to register on an IP results in `DOMException: Registration failed - push service error`.
- **Safari / iOS**: Requires HTTPS and explicit installation to the Home Screen (`standalone` display mode) before unlocking the `PushManager` API.

### Frontend Raw IP Warning
`pwa-push.js` actively detects raw IP addresses and notifies users:
```javascript
var isRawIp = /^(\d{1,3}\.){3}\d{1,3}$/.test(location.hostname);
if (location.protocol === 'https:' && isRawIp) {
    alert('Chrome Security Notice:\n\nChrome blocks Service Workers and Web Push on self-signed IP addresses (https://' + location.hostname + ').\n\nTo enable Web Push, please access Genmon via your Tailscale HTTPS domain (e.g. https://genmon.your-tailnet.ts.net) or HTTP.');
}
```

### Tailscale Funnel / Reverse Proxy Architecture
To satisfy browser security requirements with zero router port forwarding or dynamic DNS complexity, Genmon integrates with **Tailscale Funnel** and reverse proxies:

```
[ Mobile / Desktop Browser ]
            |
            v  (Public HTTPS Port 443 - Tailscale MagicDNS / Let's Encrypt TLS)
   https://genmon.your-tailnet.ts.net
            |
            v  (Tailscale Funnel TLS Termination)
  [ Raspberry Pi Host ]
            |
            v  (Internal Proxy Ingress)
   http://127.0.0.1:8000  (genserv.py Flask Server)
```

### Reverse Proxy CSRF Header Trust (`genserv.py`)
When requests pass through Tailscale Funnel or a reverse proxy (Caddy, Nginx), the browser sends an `Origin` or `Referer` header containing the public domain (e.g., `https://genmon.your-tailnet.ts.net`), while Flask receives the request on `127.0.0.1:8000`.

`genserv.py` (`csrf_check`) parses `X-Forwarded-Host` to validate CSRF tokens across proxies:
```python
trusted_hosts = {request.host}
fwd_host = request.headers.get("X-Forwarded-Host")
if fwd_host:
    for h in fwd_host.split(","):
        trusted_hosts.add(h.strip())
```
This ensures state-modifying requests (`POST /api/webpush/subscribe`, `POST /api/webpush/preferences`) succeed transparently through reverse proxies.

---

## 6. Process Status Verification Script (`startgenmon.sh status`)

The `startgenmon.sh` control script provides an automated diagnostic status utility to verify running daemons and identify crashed or inactive processes.

### Command Execution
```bash
./startgenmon.sh status
# or with sudo privileges:
sudo ./startgenmon.sh status
```

### Terminal Traffic Light Badges & Output
The script queries process IDs using `pgrep -f` and outputs standardized ANSI color-coded status badges:

```text
==================================================================
           🚦 Genmon System Process Status Verification           
==================================================================
  genmon.py            🟢 [ RUNNING ]  (PID: 12450)
  genserv.py           🟢 [ RUNNING ]  (PID: 12478)
  genwebpush.py        🟢 [ RUNNING ]  (PID: 12510)
  genpushover.py       ⚪ [ INACTIVE / OFF ]
  genmqtt.py           ⚪ [ INACTIVE / OFF ]
  gengpio.py           ⚪ [ INACTIVE / OFF ]
==================================================================
 🟢 Status Verification Complete: 3 process(es) active and running.
```

### Badge Definitions
- `🟢 [ RUNNING ]` (Green ANSI `\033[1;32m`): Process is active and healthy with recorded PID.
- `🔴 [ STOPPED / FAILED ]` (Red ANSI `\033[1;31m`): A required core process (`genmon.py` or `genserv.py`) is halted or crashed.
- `⚪ [ INACTIVE / OFF ]` (White ANSI `\033[0;37m`): An optional add-on daemon (`genpushover.py`, `genmqtt.py`, `gengpio.py`) is disabled in configuration.

### Failure Diagnostics
If any core daemon fails, `startgenmon.sh status` automatically dumps the trailing 5 lines of `/var/log/genserv.log` to the console for instant troubleshooting.

---

## 7. Role-Based Access Control & Family Read-Only Mode

Genmon implements role-based access control (RBAC) to allow family members or non-technical operators to monitor generator status without the risk of modifying settings or unregistering devices.

### User Account Tiers (`conf/genmon.conf`)
- **Administrator (`http_user` / `http_pass`)**: Full read/write access.
- **Read-Only (`http_user_ro` / `http_pass_ro`)**: Limited monitoring access.

### Session Enforcement (`HasWriteAccess()`)
In `genserv.py`, `HasWriteAccess()` evaluates the active session:
```python
def HasWriteAccess():
    if not LoginActive():
        return True
    return session.get("write_access", False)
```

### Web Push API Endpoint Permissions

| Endpoint | Method | Permitted Roles | Behavior for Read-Only Session |
| :--- | :--- | :--- | :--- |
| `/api/webpush/vapid_key` | `GET` | Admin & Read-Only | Returns public VAPID key |
| `/api/webpush/subscriptions`| `GET` | Admin & Read-Only | Returns active device list |
| `/api/webpush/preferences`  | `GET` | Admin & Read-Only | Returns notification preferences |
| `/api/webpush/subscribe`    | `POST`| **Admin Only** | Returns `403 Forbidden` (`Unauthorized: Write access required`) |
| `/api/webpush/unsubscribe`  | `POST`| **Admin Only** | Returns `403 Forbidden` (`Unauthorized: Write access required`) |
| `/api/webpush/preferences`  | `POST`| **Admin Only** | Returns `403 Forbidden` (`Unauthorized: Write access required`) |
| `/api/webpush/test`         | `POST`| **Admin Only** | Returns `403 Forbidden` (`Unauthorized: Write access required`) |

---

## 8. REST API Reference

All Web Push endpoints use JSON payloads and are prefixed under `/api/webpush/`.

---

### 1. Get VAPID Public Key
Retrieves the application server's NIST P-256 public key for client-side subscription registration.

- **URL**: `/api/webpush/vapid_key`
- **Method**: `GET`
- **Auth**: None (or Read-Only / Admin)
- **Response Schema (`200 OK`)**:
  ```json
  {
    "status": "ok",
    "public_key": "BJ7xO3Z..."
  }
  ```

---

### 2. Register Push Subscription
Persists a new browser push subscription to `/etc/genmon/webpush_subscriptions.json`.

- **URL**: `/api/webpush/subscribe`
- **Method**: `POST`
- **Auth**: Admin / Write Access Required (`403` if read-only)
- **Request Headers**: `Content-Type: application/json`
- **Request Payload**:
  ```json
  {
    "endpoint": "https://fcm.googleapis.com/fcm/send/eA...7z",
    "keys": {
      "p256dh": "BNc...<Client Public Key>...",
      "auth": "A8...<Client Auth Secret>..."
    },
    "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X)...",
    "device_name": "Oz's iPhone",
    "added_time": "2026-08-17T18:30:00.000Z"
  }
  ```
- **Response Schema (`200 OK`)**:
  ```json
  {
    "status": "ok"
  }
  ```
- **Error Response (`400 Bad Request`)**:
  ```json
  {
    "status": "error",
    "message": "Invalid subscription payload"
  }
  ```

---

### 3. Remove Push Subscription
Removes an active push subscription by endpoint URL.

- **URL**: `/api/webpush/unsubscribe`
- **Method**: `POST`
- **Auth**: Admin / Write Access Required (`403` if read-only)
- **Request Payload**:
  ```json
  {
    "endpoint": "https://fcm.googleapis.com/fcm/send/eA...7z"
  }
  ```
- **Response Schema (`200 OK`)**:
  ```json
  {
    "status": "ok"
  }
  ```

---

### 4. List Subscribed Devices
Returns all registered push devices with hardware labels and gateway service metadata.

- **URL**: `/api/webpush/subscriptions`
- **Method**: `GET`
- **Auth**: Admin & Read-Only
- **Response Schema (`200 OK`)**:
  ```json
  {
    "status": "ok",
    "count": 2,
    "subscriptions": [
      {
        "endpoint": "https://fcm.googleapis.com/fcm/send/eA...7z",
        "user_agent": "Mozilla/5.0 (Linux; Android 14; SM-S918U Build/...)",
        "device_name": "SM-S918U (Android)",
        "device_type": "📱 Android",
        "service": "Google Push (FCM)",
        "added_time": "2026-08-17T18:30:00.000Z"
      },
      {
        "endpoint": "https://web.push.apple.com/QCn...91",
        "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X)...",
        "device_name": "Oz's iPhone",
        "device_type": "📱 iOS Safari",
        "service": "Apple Push (APNs)",
        "added_time": "2026-08-17T18:32:00.000Z"
      }
    ]
  }
  ```

---

### 5. Get / Set Notification Preferences
Fetches or updates event notification filter toggles in `genwebpush.conf`.

- **URL**: `/api/webpush/preferences`
- **Method**: `GET` (Read) / `POST` (Update)
- **Auth**: `GET` (Admin & Read-Only), `POST` (Admin Only)
- **Request Payload (`POST`)**:
  ```json
  {
    "notify_outage": true,
    "notify_exercise": true,
    "notify_error": true,
    "notify_warning": true,
    "notify_off_manual": true,
    "notify_fuel": true,
    "notify_pi_state": true,
    "notify_sw_update": true,
    "notify_info": true
  }
  ```
- **Response Schema (`GET` / `POST` `200 OK`)**:
  ```json
  {
    "status": "ok",
    "preferences": {
      "notify_outage": true,
      "notify_exercise": true,
      "notify_error": true,
      "notify_warning": true,
      "notify_off_manual": true,
      "notify_fuel": true,
      "notify_pi_state": true,
      "notify_sw_update": true,
      "notify_info": true
    }
  }
  ```

---

### 6. Send Test Push Notification
Dispatches an immediate test push alert to a specified device endpoint.

- **URL**: `/api/webpush/test`
- **Method**: `POST`
- **Auth**: Admin / Write Access Required (`403` if read-only)
- **Request Payload**:
  ```json
  {
    "endpoint": "https://fcm.googleapis.com/fcm/send/eA...7z"
  }
  ```
- **Response Schema (`200 OK`)**:
  ```json
  {
    "status": "ok"
  }
  ```

---

## 9. PWA UI Modal & Push Management

The Web Push management interface is built directly into the main Genmon single-page application (`templates/index.html` and `static/js/pwa-push.js`).

### Accessing the Interface
1. In the web application header bar, click the **Bell Icon (`#pwa-push-btn`)**.
2. The modal `#pwa-push-modal` opens with live subscription status and device management controls.

### Event Toggle Switches
Operators can individually enable or disable alerts across 8 distinct generator event categories:

| Switch / Key | UI Label | Trigger Condition |
| :--- | :--- | :--- |
| `notify_outage` | ⚡ Power Outage / Utility Restored | Grid power failure or utility power return |
| `notify_exercise` | 🏋️ Exercise Started / Stopped | Weekly/bi-weekly scheduled exercise cycles |
| `notify_error` | 🚨 Alarms & Controller Errors | Controller warning/fault codes, low oil pressure, overspeed |
| `notify_warning` | 🔧 Maintenance Service Required | Scheduled engine hours threshold or inspection due |
| `notify_off_manual` | 📴 Switch Changed to OFF or MANUAL | Physical generator control switch moved away from AUTO |
| `notify_fuel` | ⛽ Low Fuel Warnings | Propane / diesel fuel tank level warnings |
| `notify_pi_state` | 🌡️ Raspberry Pi Hardware Health | Host CPU thermal throttle (>80°C) or low voltage |
| `notify_sw_update` | ℹ️ Software Updates & System Notices| New Genmon release available |

### Instant Push Testing
Clicking the **Test** button dispatches an immediate test payload (`⚡ Genmon Test Push Alert`) to the current device's endpoint.

### Remote Device Removal Notification (`🔕 Web Push Device Removed`)
When an operator clicks **Remove** on a device in the subscribed devices list:
1. `addon/genwebpush.py` executes `RemoveSubscription(endpoint, notify_device=True)`.
2. A final push notification titled **"🔕 Web Push Device Removed"** (*"This device has been unsubscribed from Genmon alerts."*) is sent to the target device.
3. The device endpoint is deleted from `/etc/genmon/webpush_subscriptions.json`.

---

## 10. Troubleshooting, iOS Setup & Verification

### iOS PWA Installation (iOS 16.4+)
Apple requires Web Push notifications to be granted from standalone PWA instances rather than regular Safari browser tabs.

1. Open Safari on your iPhone/iPad and navigate to your Genmon HTTPS domain (e.g., `https://genmon.your-tailnet.ts.net`).
2. Tap the **Share Button** (square with up arrow).
3. Scroll down and select **Add to Home Screen**.
4. Launch Genmon from the new Home Screen icon.
5. Tap the **Bell Icon** in the header, enter an optional device label (e.g., `Oz's iPhone`), and tap **Enable Push Alerts**.
6. When prompted by iOS, tap **Allow Notifications**.

### Chrome SSL & Raw IP Resolution
- **Symptom**: Chrome displays `Push Subscription error: Registration failed - push service error`.
- **Cause**: Chrome blocks Service Workers and Web Push on raw IP HTTPS URLs (`https://192.168.x.x`).
- **Resolution**: Access Genmon via a valid domain with trusted TLS, such as **Tailscale Funnel** (`https://<node>.ts.net`) or configure a local DNS hostname with a Let's Encrypt certificate.

### Resetting VAPID Keys
If VAPID keys become compromised or need regeneration:
1. Stop Genmon services:
   ```bash
   sudo ./startgenmon.sh stop
   ```
2. Remove old keys from configuration:
   ```bash
   sudo sed -i '/vapid_public_key/d' /etc/genmon/genwebpush.conf
   sudo sed -i '/vapid_private_key/d' /etc/genmon/genwebpush.conf
   ```
3. Restart Genmon (new NIST P-256 keys will be generated automatically):
   ```bash
   sudo ./startgenmon.sh start
   ```
4. Re-subscribe client devices via the Web UI modal.

### Python Dependency Verification
Ensure `pywebpush` is installed for payload encryption:
```bash
pip3 install pywebpush
```

### Diagnostic Commands Summary
```bash
# Verify process health with colored badges
./startgenmon.sh status

# Monitor live push notification daemon logs
tail -f /var/log/genwebpush.log

# Monitor web server and API request logs
tail -f /var/log/genserv.log

# Run integration test suite
python3 -m unittest discover tests
```
