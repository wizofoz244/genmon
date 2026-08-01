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
 |  |  - Daily @ 4:00 AM:  /home/genmonpi/backup_to_mac.sh (Genmon Archive)       |  |
 |  |  - Sunday @ 4:00 AM: /home/genmonpi/sdcard_backup_to_mac.sh (SD Card Image)  |  |
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
