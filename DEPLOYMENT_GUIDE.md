# Complete Genmon Setup, Backup & Deployment Guide

This document captures the complete architecture, data processing scripts, automated backup routines, custom add-ons, web UI optimization, GitHub fork management, and Raspberry Pi systemd deployment for this Genmon generator monitoring system.

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
- Unit Test Suite: `python3 -m unittest addon/test_genmaint_sync.py`

---

## 4. Automated Backup Routines to Mac Server

The Raspberry Pi backs up data automatically to an SMB network share hosted on a Mac server (`192.168.128.15`).

### SMB Share Mount Configuration (`/etc/fstab`)
- **Mac Server IP**: `192.168.128.15`
- **Share Name**: `PiBackup`
- **Mount Point**: `/mnt/pibackup`
- **Credentials File**: `/etc/smbcredentials_pibackup`
  ```text
  username=YOUR_SMB_USERNAME
  password=YOUR_SMB_PASSWORD
  ```
  Set restrictive permissions: `sudo chmod 600 /etc/smbcredentials_pibackup`
- **`/etc/fstab` Resilient Entry**:
  ```fstab
  //192.168.128.15/PiBackup /mnt/pibackup cifs credentials=/etc/smbcredentials_pibackup,uid=genmonpi,gid=genmonpi,file_mode=0777,dir_mode=0777,noperm,hard,echo_interval=60,vers=3.0,x-systemd.automount,_netdev 0 0
  ```
- **Mount Options Breakdown**:
  - `uid=genmonpi,gid=genmonpi,file_mode=0777,dir_mode=0777,noperm`: Grants full unprivileged read/write access to user `genmonpi` and `root` without client-side permission blocks.
  - `hard`: Pauses and retries I/O operations automatically during brief network drops instead of throwing immediate `Input/Output error`.
  - `echo_interval=60`: Sends SMB keepalive echoes every 60 seconds to prevent Wi-Fi router session timeouts.
  - `vers=3.0`: Enables SMB 3.0 protocol resilient handles so file writes survive temporary Wi-Fi reconnects.
- **Reload Command**:
  ```bash
  sudo systemctl daemon-reload && sudo mount -a
  ```

---

### Production Backup Helper Scripts

The repository includes production backup scripts in `/home/genmonpi/genmon/`:

#### 1. Daily Genmon Data Archive (`/home/genmonpi/genmon/backup_to_mac.sh`)
- Archives configuration files (`/etc/genmon`), database logs (`maintlog.json`), and sync states (`maint_sync_state.json`).
- **Archive File**: `/mnt/pibackup/daily/genmon_daily_master.tar.gz`
- **Integrity & Resiliency**: Pre-checks archive header with `tar -tzf`, auto-heals corrupt archives, and executes network retries (`retry_cmd`).
- **Retention Policy**: Retains 7 daily snapshots (`genmon_daily_YYYY-MM-DD_HHMMSS.tar.gz`).
- **Log File**: `/home/genmonpi/backup.log`
- **Cron Schedule**: Daily at 4:00 AM
  ```cron
  0 4 * * * /home/genmonpi/genmon/backup_to_mac.sh
  ```

#### 2. Weekly Live SD Card Image (`/home/genmonpi/genmon/sdcard_backup_to_mac.sh`)
- Creates a full live bootable system image: `/mnt/pibackup/genmon_sdcard_master.img`.
- **Pre-Flight Corruption Health Checks**: MBR partition table inspection and loopback `e2fsck -n` ext4 superblock validation.
- **Auto-Healing Replacement**: Automatic removal and re-initialization of corrupted/truncated master images.
- **Stale Mount Auto-Recovery**: Detects stale mounts (`No such device` / `Stale file handle`) and executes lazy unmount (`umount -l -f`) and auto-remount.
- **Network Hiccup Resiliency**: 3-attempt exponential backoff retry loop (`retry_cmd`).
- **Non-Interactive Prompt Pipeline**: Automated `printf "${MASTER_IMG}\n\n\ny\n"` for `image-backup`.
- **Signal Trap Cleanup**: Emergency handler (`trap cleanup EXIT INT TERM`) detaching orphan loop devices and temporary mounts.
- **Disk Space & Package Audits**: Pre-flight verification of 10+ GB free space and system package dependencies (`kpartx`, `rsync`, `parted`, `bc`, `dosfstools`, `e2fsck`).
- **Retention Policy**: Retains 4 weekly snapshots (`genmon_sdcard_YYYY-MM-DD_HHMMSS.img`).
- **Log File**: `/home/genmonpi/sdcard_backup.log`
- **Cron Schedule**: Weekly on Sunday at 4:00 AM
  ```cron
  0 4 * * 0 /home/genmonpi/genmon/sdcard_backup_to_mac.sh
  ```

---

## 5. Web UI Optimization & FOUC Prevention

To prevent **Flash of Unstyled Content (FOUC)** when loading the Genmon web interface (such as a white flash before dark mode loads):
- **CSS Preloading**: Core stylesheet `css/genmon.css` is preloaded via `<link rel="preload" href="css/genmon.css" as="style">` in template `<head>` sections.
- **Visibility Transition**: Inline CSS and DOM ready scripts enforce `visibility: hidden; opacity: 0;` until stylesheets and theme initialization complete, fading in smoothly via `.fouc-ready` class.

---

## 6. Manual Backup Execution & Live Terminal Console

A dedicated **Run Backups** page (`#backups`) in the left navigation sidebar allows triggering manual backup routines and viewing real-time terminal output:
- **Tabbed Interface**:
  - 📦 **Daily Backup Routine** Tab (`backup_to_mac.sh`)
  - 💾 **Weekly SD Card Routine** Tab (`sdcard_backup_to_mac.sh`)
- **Live Execution Console**: High-tech green streaming output window (`#br-console`) with auto-scrolling line updates.
- **Interactive Controls**: ▶ **Run Backup**, 🛑 **Stop Execution**, and **Clear Console** buttons.
- **Backend Runner**: Flask `BackupRunner` class executing non-blocking background threads with `subprocess.Popen` line-by-line output streaming.

---

## 7. Web UI Script & Add-on Log Viewer

A dedicated **Script Logs** page (`#scriptlogs`) in the left navigation sidebar allows real-time inspection of background automated scripts and add-on services:
- **Monitored Logs**:
  - 🔄 **Maintenance Sync Log** (`/etc/genmon/genmaint_sync.log`)
  - 📦 **Daily Backup Log** (`/home/genmonpi/backup.log`)
  - 💾 **Weekly SD Card Log** (`/home/genmonpi/sdcard_backup.log`)
  - 📡 **Network Watchdog Log** (`/var/log/net-watchdog.log`)
- **Interactive Features**:
  - Status badges on tab buttons (`OK`, `WARN`, `ERROR`).
  - **× Clear Log** button with safety confirmation modal to truncate logs on disk.
  - **Acknowledge Errors** button to clear alert badges on the main Dashboard **Script Logs Status** tile.
  - Built-in search filtering and syntax highlighting (errors in **Red**, warnings in **Yellow**, normal info in **Green**).

---

## 7. GitHub Fork & Git Workflow

The project is maintained on a personal GitHub fork: **[`wizofoz244/genmon`](https://github.com/wizofoz244/genmon)**.

### Remote Configuration
- `origin`: `https://github.com/wizofoz244/genmon.git` (Personal Fork)
- `upstream`: `https://github.com/jgyates/genmon.git` (Official Repository)

### Mac to Raspberry Pi Deployment Workflow

1. **On Mac**: Commit and push changes:
   ```bash
   git add .
   git commit -m "Description of updates"
   git push origin main
   ```

2. **On Raspberry Pi**: Pull updates:
   ```bash
   cd ~/genmon
   git checkout -b main origin/main 2>/dev/null || git checkout main
   git pull origin main
   ```

3. **Syncing Upstream Genmon Updates**:
   ```bash
   git fetch upstream
   git merge upstream/master
   git push origin main
   ```

---

## 8. Raspberry Pi Systemd Service Deployment

### System Information
- **User**: `genmonpi`
- **Path**: `/home/genmonpi/genmon`
- **Config Directory**: `/etc/genmon`

### Systemd Unit File (`/etc/systemd/system/genmaint_sync.service`)

```ini
[Unit]
Description=Genmon Service Journal Sync Addon
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /home/genmonpi/genmon/addon/genmaint_sync.py -c /etc/genmon
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Management Commands
```bash
# Reload systemd configuration
sudo systemctl daemon-reload

# Enable service on boot
sudo systemctl enable genmaint_sync.service

# Start / Restart service
sudo systemctl start genmaint_sync.service
sudo systemctl restart genmaint_sync.service

# View status
sudo systemctl status genmaint_sync.service

# View real-time logs
sudo tail -f /etc/genmon/genmaint_sync.log
sudo journalctl -u genmaint_sync.service -f
```

---

## 9. USB Wi-Fi Adapter Setup & 2.4 GHz Band Locking

Generators housed in heavy metal enclosures require maximum signal range and obstacle penetration. The **2.4 GHz Wi-Fi band** penetrates metal enclosures and exterior walls far better than 5 GHz signals.

### Disabling On-Board Raspberry Pi Wi-Fi (Using High-Gain USB Wi-Fi Adapter)

If an external high-gain USB Wi-Fi adapter is plugged in, disable the internal Raspberry Pi Wi-Fi and Bluetooth chips to avoid interface conflicts and save power:

1. Edit `/boot/firmware/config.txt` (or `/boot/config.txt` on older OS versions):
   ```bash
   sudo nano /boot/firmware/config.txt
   ```
2. Append the following lines at the bottom of the file:
   ```text
   # Disable on-board Wi-Fi and Bluetooth to use external USB Wi-Fi adapter
   dtoverlay=disable-wifi
   dtoverlay=disable-bt
   ```
3. Reboot the Raspberry Pi:
   ```bash
   sudo reboot
   ```

---

### Disabling 5 GHz Band (Locking Connection to 2.4 GHz Only)

#### Method A: NetworkManager (`nmcli` - Raspberry Pi OS Bookworm / Modern)

Restrict the Wi-Fi profile to the 2.4 GHz band (`bg` band):

```bash
# Restrict connection to 2.4 GHz 802.11bg band
sudo nmcli connection modify "YOUR_SSID" 802-11-wireless.band bg

# Set channel auto-selection for 2.4 GHz
sudo nmcli connection modify "YOUR_SSID" 802-11-wireless.channel 0

# Apply changes and reconnect
sudo nmcli connection up "YOUR_SSID"
```

#### Method B: `wpa_supplicant.conf` (Raspberry Pi OS Bullseye / Legacy)

Restrict scanning frequencies strictly to 2.4 GHz channels (Channels 1–11 / 2412–2462 MHz):

1. Edit `/etc/wpa_supplicant/wpa_supplicant.conf`:
   ```bash
   sudo nano /etc/wpa_supplicant/wpa_supplicant.conf
   ```
2. Add the `freq_list` parameter to your network configuration block:
   ```text
   network={
       ssid="YOUR_SSID"
       psk="YOUR_PASSWORD"
       freq_list=2412 2417 2422 2427 2432 2437 2442 2447 2452 2457 2462
   }
   ```
3. Reconfigure Wi-Fi interface:
   ```bash
   sudo wpa_cli -i wlan0 reconfigure
   ```

---

## 10. Automated Network Watchdog & Auto-Reboot (`net_watchdog.sh`)

A production-grade network watchdog script (`/home/genmonpi/genmon/net_watchdog.sh`) automatically recovers lost network connections and safely reboots the Raspberry Pi when connectivity cannot be restored.

### Key Capabilities & Edge Case Protections
- **Multi-Tiered Escalation**:
  - **Phase 1**: Attempts soft network stack restart (`nmcli` or `ip link` / `dhcpcd` / `wpa_supplicant`).
  - **Phase 2**: Detects USB driver lockups (disappearing `wlan0`) and unbinds/rebinds the USB bus controller.
  - **Phase 3**: Performs a graceful system reboot if connectivity remains down after `MAX_RESET_ATTEMPTS` (default: 2 soft resets over ~6+ minutes).
- **Access Point Reboot Window**: Gives Wi-Fi access points and mesh routers a ~6-minute grace period to finish booting before triggering a Pi reboot.
- **Wi-Fi Power Save Disabling**: Automatically executes `iw dev wlan0 set power_save off` to prevent USB Wi-Fi dongles from entering idle sleep mode.
- **Genmon Journal Protection**: Safely stops `genmon.service` and flushes disk write buffers (`sync`) prior to rebooting to prevent `maintlog.json` corruption.
- **SD Card Protection**: Limits consecutive reboots to `MAX_CONSECUTIVE_REBOOTS=3` to avoid wear on flash storage if the router is powered off long-term.
- **Concurrency & Lock Control**: Uses `flock` and command timeouts to prevent overlapping execution from Cron.

### Cron Installation Setup
```bash
sudo crontab -e
```
Add the following entry to execute the watchdog every 3 minutes:
```cron
*/3 * * * * /home/genmonpi/genmon/net_watchdog.sh
```

---

## 11. Tailscale Funnel & Remote HTTPS Deployment

Tailscale Funnel exposes the Genmon web interface to the public internet with a valid, automated Let's Encrypt certificate over HTTPS port 443.

### Recommended Port Architecture
- **Genmon HTTPS Backend (`genserv.py`)**: Configured to listen on port `8443` (to prevent port binding conflicts on privileged port 443).
- **Tailscale Funnel**: Listens on public port `443` and proxies traffic to `https+insecure://127.0.0.1:8443`.

### Setup Instructions

1. **Configure Genmon HTTPS Port in `/etc/genmon/genmon.conf`**:
   ```ini
   usehttps = True
   https_port = 8443
   http_user = YOUR_ADMIN_USERNAME
   http_pass = YOUR_ADMIN_PASSWORD
   ```
   Restart Genmon:
   ```bash
   sudo ./startgenmon.sh restart
   ```

2. **Configure Tailscale Funnel**:
   Run the background Funnel command:
   ```bash
   sudo tailscale funnel --bg https+insecure://127.0.0.1:8443
   ```

3. **Verify Funnel Status**:
   ```bash
   tailscale funnel status
   ```
   Expected output:
   ```text
   # Funnel on:
   #     - https://genmon.YOUR-TAILNET.ts.net

   https://genmon.YOUR-TAILNET.ts.net (Funnel on)
   |-- / proxy https+insecure://127.0.0.1:8443
   ```

4. **Verify Port Listeners on Raspberry Pi**:
   ```bash
   sudo ss -tulpn | grep -E 'python|genserv|443|8443'
   ```
   - `python` (`genserv`) listening on `0.0.0.0:8443`
   - `tailscaled` listening on `100.x.y.z:443`

---

## 12. PWA Web Push Notification System (`addon/genwebpush.py`)

A standalone push notification daemon and PWA service worker integrating real-time alerts on iOS (Safari PWA), macOS, Android (Chrome), and Windows.

### Key Capabilities & Architecture
- **VAPID RFC 8292 Key Generation**: Auto-generates and persists NIST P-256 EC VAPID keypairs in `genwebpush.conf`.
- **Apple APNs Compatible JWS**: Formats raw 64-byte `r || s` ES256 signatures and strict `vapid t=..., k=...` headers for Apple Web Push endpoints (`web.push.apple.com`).
- **AES-128-GCM Payload Encryption**: Uses `http_ece` and `pywebpush` for standard encrypted web push payloads.
- **Dynamic Device Management**: Automatically recognizes hardware models (iPhone, iPad, Mac Desktop, Android, Windows) and allows setting and editing custom device names in the UI.
- **Real-Time Generator Event Triggers**: Dispatches push notifications for:
  - 🚨 Generator Alarms (with specific fault code extraction)
  - ⚡ Utility Outages & Restorations
  - 🔄 Scheduled Exercise Start & Stop
  - 🟢 Generator Running & Stopped State Transitions
  - 📴 Switch Changes to OFF or MANUAL
  - ⛽ Fuel Level Warnings
  - 🌡️ Raspberry Pi Hardware Health (High Temp / Low Voltage)
  - ℹ️ Software Updates & System Notices

### UI Management
- Click the **🔔 Push Alert Settings** button in the top navigation bar to subscribe devices, customize device labels, set notification preferences, and configure the Apple APNs VAPID contact email.



