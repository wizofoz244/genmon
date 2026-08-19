# Complete Genmon Setup, Backup & Deployment Guide

This document captures the complete architecture, data processing scripts, automated backup routines, custom add-ons, web UI optimization, GitHub fork management, test framework, and Raspberry Pi systemd deployment for this Genmon generator monitoring system.

---

## 1. System Architecture & Component Map

```
 +-----------------------------------------------------------------------------------+
 |                             Mac Server (192.168.128.15)                           |
 |                                                                                   |
 |  SMB Share: //192.168.128.15/pibackup  <======================================+   |
 +-------------------------------------------------------------------------------+---|
                                                                                 |
                                                                  CIFS / SMB     |
 +-------------------------------------------------------------------------------+---|
 |                          Raspberry Pi (genmonpi)                              |   |
 |                                                                               |   |
 |  Mount Point: /mnt/pibackup <=================================================+   |
 |                                                                                   |
 |  +--------------------+         Socket RPC          +-------------------------+   |
 |  |   Genmon Daemon    | <-------------------------> |     genmaint_sync       |   |
 |  |    (genmond)       | (port 9082 / generator:*)   |  Add-on Daemon Service  |   |
 |  +--------------------+                             +-------------------------+   |
 |            |                                                     |                |
 |            v                                                     v                |
 |  /etc/genmon/maintlog.json  <------------------------------------+                |
 |  /etc/genmon/outage.txt                                                           |
 |  /etc/genmon/outage_summary.csv                                                   |
 |                                                                                   |
 |  +-----------------------------------------------------------------------------+  |
 |  | Cron Automated Tasks                                                        |  |
 |  |  - Every 3 Mins:      /home/genmonpi/genmon/net_watchdog.sh (Network Watchdog) |  |
 |  |  - Daily @ 4:00 AM:  /home/genmonpi/genmon/backup_to_mac.sh (Genmon Archive)    |  |
 |  |  - Sunday @ 4:00 AM: /home/genmonpi/genmon/sdcard_backup_to_mac.sh (SD Card) |  |
 |  +-----------------------------------------------------------------------------+  |
 +-----------------------------------------------------------------------------------+
```

---

## 2. Maintenance Journal & Outage Log Data Pipeline

### Maintenance Log (`maintlog.json`)
- **Location**: `/etc/genmon/maintlog.json` (and synced to local workspace)
- **Data Conversion Scripts**:
  - `process_all_maint_data.py`: Parses historical exports (`statusHistory.csv`) and merges user service logs.
  - `update_all_logs.py`: Updates engine run hours for all entries based on session runtimes.
  - `merge_maintlog_full.py`: Deduplicates and combines full maintenance history.
- **Entry Schema**:
  ```json
  {
      "date": "MM/DD/YYYY HH:MM",
      "type": "Maintenance | Check | Repair | Observation",
      "hours": 138.9,
      "comment": "Description of event or service item"
  }
  ```
- **Engine Hours Baseline & Scaling**:
  - Accounts for controller replacement on **06/20/2026** (reference target of **138.9 hours**).
  - Scaled using cumulative runtime from engine run sessions (Exercise, Utility Loss, Manual).

### Outage Tracking & Fuel Estimation (`outage.txt` & `outage_summary.csv`)
- **Locations**: `/etc/genmon/outage.txt`, `/etc/genmon/outage_summary.csv`
- **Scripts**: `build_outagelog.py`, `build_outagelog_with_fuel.py`
- **Fuel Rate**: `200.0 cubic feet / hour` (Natural Gas).
- **Outage Duration Format**: `X day, HH:MM:SS`
- **Rules**: 5-minute weekly exercise sessions are excluded from outage fuel totals.

---

## 3. Automated Controller Run & Alarm Log Sync (`addon/genmaint_sync.py`)

A standalone add-on daemon that monitors the generator controller's 50-entry **Run Log** and **Alarm Log** via Genmon's RPC socket interface.

### Key Capabilities
- **Classification**: Automatically converts all controller run and alarm events into `type: "Observation"` entries.
- **Engine Run Hours**:
  - Assigns live engine run hours for current events.
  - Back-interpolates engine hours for past buffered events by calculating run session durations between event timestamp and present.
- **State Tracking & Deduplication**: Maintains persistent state in `/etc/genmon/maint_sync_state.json` to prevent duplicate records across reboots.
- **Atomic Writes**: Uses temporary files and `os.replace` to prevent file corruption.

### Command Line Interface
```bash
sudo python3 /home/genmonpi/genmon/addon/genmaint_sync.py -c /etc/genmon [options]
```
- `-1`, `--oneshot`: Perform a single sync pass and exit.
- `-d`, `--dry-run`: Preview log parsing and run hour calculations without modifying files.
- `-r`, `--recalculate-hours`: Recalculate engine run hours for existing `Observation` entries with `0.0` hours.
- `-i`, `--interval`: Polling interval in seconds (default: `60`).

### Documentation & Unit Tests
- Add-on Documentation: [addon/README_genmaint_sync.md](file:///Users/oz/Develop/genmon/addon/README_genmaint_sync.md)
- Unit Test Suite: `python3 -m unittest discover -s tests -p "test_*.py"`

---

## 4. Automated Backup Routines to Mac Server

### CIFS Mount Configuration (`/etc/fstab`)
```text
//192.168.128.15/pibackup /mnt/pibackup cifs credentials=/etc/smbcredentials,uid=1000,gid=1000,iocharset=utf8,vers=3.0,nofail,_netdev,x-systemd.automount,x-systemd.mount-timeout=30 0 0
```
- **Automount**: `x-systemd.automount` ensures mount is only triggered on demand.
- **Timeout**: `x-systemd.mount-timeout=30` prevents boot stalls if Mac is offline.

### Credentials File (`/etc/smbcredentials`)
```ini
username=pi
password=YOUR_SECURE_PASSWORD
domain=WORKGROUP
```
Permissions: `sudo chmod 600 /etc/smbcredentials`

---

### Daily Genmon Backup Script (`/home/genmonpi/genmon/backup_to_mac.sh`)
- **Execution**: Daily at 4:00 AM via Cron.
- **Archive Contents**: `/etc/genmon/*`, `/home/genmonpi/genmon/conf/*`, `maintlog.json`, `outage.txt`.
- **Retention**: Keeps the last 14 daily archives, purging older archives automatically.
- **Network Resilience**: 3-stage exponential backoff retry loop with automatic stale mount unmount/remount recovery.

---

### Weekly SD Card Image Backup Script (`/home/genmonpi/genmon/sdcard_backup_to_mac.sh`)
- **Execution**: Every Sunday at 4:00 AM via Cron.
- **Image Utility**: Utilizes `image-backup` to create direct, compressed, shrink-fit `.img` files.
- **Integrity Validation**: Runs loopback `e2fsck -fy` filesystem superblock check on newly created images to guarantee restoration integrity.
- **Auto-Replacement**: If a backup is corrupted, automatically creates a fresh replacement image.
- **Retention**: Maintains current backup plus previous generation fallback.

---

## 5. Web UI Manual Backups Console

Accessible from the top navigation bar under **Backups**:
- **Live Output Stream**: Shows real-time script output using server-sent chunks.
- **Tabbed Routines**: Run either the **Daily Backup Routine** or **Weekly SD Card Routine** on demand.
- **Disk & Mount Pre-Checks**: Inspects CIFS mount status and available disk space before starting image creation.

---

## 6. Web UI Optimization & FOUC Prevention

- **Single-Page Application Router**: Uses `history.replaceState` for zero-flicker client-side routing.
- **Flash of Unstyled Content (FOUC) Prevention**:
  - Inlines critical CSS directly within `index.html`.
  - Hides main container until stylesheet `load` event fires.
- **Content Security Policy (CSP)**:
  ```text
  default-src 'self' https: http: data: blob: 'unsafe-inline' 'unsafe-eval';
  style-src 'self' https: http: data: blob: 'unsafe-inline';
  ```
- **Asset Versioning**: Uses query parameters (`?v=2026.1`) to guarantee browser cache eviction across updates.

---

## 7. Script Logs Viewer & Dashboard Status Tile

### Script Logs Navigation & Viewer
- **URL**: `/#/logs`
- **Dashboard Status Tile**:
  - Live status indicator displaying aggregate error / warning health across all background scripts.
  - **Tile Click Navigation**: Clicking the Script Logs tile directly opens the Script Logs page.
- **Tabs Supported**:
  1. `Network Watchdog` (`/var/log/net-watchdog.log`)
  2. `Maint Log Sync` (`/etc/genmon/genmaint_sync.log`)
  3. `Daily Backup` (`/home/genmonpi/backup.log`)
  4. `SD Card Backup` (`/home/genmonpi/sdcard_backup.log`)
- **Error Highlighting**: Automatically detects and highlights `[ERROR]` and `[WARN]` entries.
- **Error Acknowledgment & Clear Log**: Provides buttons to acknowledge warnings or truncate log files.

---

## 8. Wi-Fi Band Detection (2.4 GHz / 5 GHz / 6 GHz)

- **Backend**: `MyPlatform.GetWiFiBand` in `genmonlib/myplatform.py` parses `iw dev <iface> link` (or `iwconfig`) to determine operating frequency.
- **Dashboard Signal Tile**: Displays operating frequency band alongside signal quality (e.g. `-65 dBm (2.4 GHz)`).
- **Platform Stats Modal**: Includes active Wi-Fi band in system status diagnostics.

---

## 9. Wi-Fi Reliability & 2.4 GHz Band Locking

Genmon requires a stable Wi-Fi connection with the generator controller. 2.4 GHz provides superior range and penetration through outdoor generator enclosures.

### Locking Wi-Fi to 2.4 GHz Only

#### NetworkManager (`nmcli` - Raspberry Pi OS Bookworm)
```bash
# Restrict connection to 2.4 GHz 802.11bg band
sudo nmcli connection modify "YOUR_SSID" 802-11-wireless.band bg
sudo nmcli connection modify "YOUR_SSID" 802-11-wireless.channel 0
sudo nmcli connection up "YOUR_SSID"
```

#### `wpa_supplicant.conf` (Raspberry Pi OS Bullseye)
```text
network={
    ssid="YOUR_SSID"
    psk="YOUR_PASSWORD"
    freq_list=2412 2417 2422 2427 2432 2437 2442 2447 2452 2457 2462
}
```

---

## 10. Network Watchdog & Auto-Reboot (`net_watchdog.sh`)

A production-grade network watchdog script (`/home/genmonpi/genmon/net_watchdog.sh`) running every 3 minutes via Cron.

### Key Protections
- **Phase 1**: Soft network stack restart (`nmcli` / `wpa_supplicant`).
- **Phase 2**: USB bus controller rebind if USB dongle locks up.
- **Phase 3**: Graceful system reboot if unreachable after 2 soft resets (~6 mins).
- **Wi-Fi Power Save**: Disables power management (`iw dev wlan0 set power_save off`).
- **Data Protection**: Safely stops `genmon.service` and flushes buffers prior to reboot.
- **SD Card Protection**: Limits consecutive reboots to `MAX_CONSECUTIVE_REBOOTS=3`.

```cron
*/3 * * * * /home/genmonpi/genmon/net_watchdog.sh
```

---

## 11. Tailscale Funnel & Remote HTTPS Deployment

Genmon offers first-class support for Tailscale HTTPS and Tailscale Funnel:

### Certificate Modes & Auto-Renewal
- **`cert_mode = tailscale`**: Automatically obtains and provisions Let's Encrypt certificates using the host's `tailscale cert` command.
- **90-Day Lifecycle & Auto-Renewal**: Because Tailscale/Let's Encrypt certificates have a strict 90-day validity period, Genmon runs a background **Certificate Renewal Watchdog** (checked every 12 hours) that automatically executes `tailscale cert` when `< 30 days` remain.
- **Manual Regeneration UI**: A dedicated **`[ 🔄 Renew / Regenerate Certificate ]`** action button in **Settings → Security Settings** allows admins to trigger immediate renewal or update network SAN lists on demand.
- **Tailscale Funnel**: Listens on public port `443` and proxies traffic to `https+insecure://127.0.0.1:8443`.

```bash
sudo tailscale funnel --bg https+insecure://127.0.0.1:8443
```

---

## 12. PWA Web Push Notification System (`addon/genwebpush.py`)

A standalone push notification daemon and PWA service worker integrating real-time alerts across iOS (Safari PWA), macOS, Android, and Windows.

### Key Capabilities & Architecture
- **VAPID RFC 8292 Key Generation**: Auto-generates and persists NIST P-256 EC VAPID keypairs in `genwebpush.conf`.
- **Apple APNs Compatible JWS**: Formats raw 64-byte `r || s` ES256 signatures and strict `vapid t=..., k=...` headers for Apple Web Push endpoints (`web.push.apple.com`).
- **AES-128-GCM Payload Encryption**: Uses `http_ece` and `pywebpush` for standard encrypted web push payloads.
- **Dynamic Device Management**: Automatically recognizes device models (iPhone, iPad, Mac, Android, Windows) and allows editing custom device names in the UI.
- **Real-Time Generator Event Triggers**:
  - 🚨 Generator Alarms (with specific fault code extraction)
  - ⚡ Utility Outages & Restorations
  - 🔄 Scheduled Exercise Start & Stop
  - 🟢 Generator Running & Stopped State Transitions
  - 📴 Switch Changes to OFF or MANUAL
  - ⛽ Fuel Level Warnings
  - 🌡️ Raspberry Pi Hardware Health (High Temp / Low Voltage)
  - ℹ️ Software Updates & System Notices

### UI Management
- Click **🔔 Push Alert Settings** in navigation to subscribe devices, customize device labels, set notification preferences, and configure the Apple APNs VAPID contact email.

---

## 13. Web UI Security & Session Management

- **Global Session Revocation ("Logout All Devices")**:
  - Available under the **Security** tab in settings.
  - Automatically regenerates the server session secret key, immediately revoking all active sessions across all devices.
- **Secure Cookie Expiration**:
  - Logout clears Flask session variables and forces `Set-Cookie` expiration with `Max-Age=0`.
- **Passkey / WebAuthn**:
  - Supports passwordless FIDO2 / WebAuthn passkey authentication.
- **MFA & Backup Codes**:
  - Time-based One-Time Password (TOTP) MFA with one-time emergency backup recovery codes.

---

## 14. Testing Framework & Continuous Integration

Genmon includes a comprehensive unit and integration test suite organized under `tests/`:

```
tests/
├── conftest.py                       # Common hardware mock setup & logger isolation
├── unit/
│   ├── test_wifi_band.py             # Wi-Fi band derivation & GUI tile integration
│   ├── test_net_watchdog.py          # Watchdog bash syntax, IP regex & log endpoints
│   ├── test_webpush.py               # VAPID cryptography, Apple APNs & push payloads
│   ├── test_pwa_security.py          # Session security & Logout All Devices
│   └── test_genmaint_sync.py         # Controller log parsing & engine run hour math
└── integration/
    ├── test_modbus_controller_integration.py # Simulated Modbus -> Evolution controller
    ├── test_genserv_web_integration.py       # Flask Web API endpoints & access control
    └── test_notification_integration.py     # GenNotify event dispatcher pipeline
```

### Running Tests
Execute the entire test suite via Python's native test runner:
```bash
python3 -m unittest discover -s tests -p "test_*.py"
```

### Standalone Backward-Compatible Runners
```bash
python3 test_wifi_band.py
python3 test_net_watchdog.py
python3 addon/test_genmaint_sync.py
```

### Continuous Integration (GitHub Actions)
- `.github/workflows/test.yml`: Runs the automated test suite across Python 3.9, 3.10, 3.11, and 3.12 on every push and pull request.
