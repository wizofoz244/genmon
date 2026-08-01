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
- **Share Name**: `pibackup`
- **Mount Point**: `/mnt/pibackup`
- **Credentials File**: `/etc/wincredentials` (`username=pibackup`, `password=...`)
- **`/etc/fstab` entry**:
  ```fstab
  //192.168.128.15/pibackup /mnt/pibackup cifs credentials=/etc/wincredentials,iocharset=utf8,vers=3.0,nofail,x-systemd.automount 0 0
  ```

### Backup Script 1: Daily Genmon Data Archive (`/home/genmonpi/backup_to_mac.sh`)
- Uses `genmonmaint.sh` to generate compressed archive `genmon_backup_YYYY-MM-DD_HHMMSS.tar.gz`.
- Copies archive to `/mnt/pibackup/`.
- Removes local temporary files automatically (`rm -f`).
- **Retention Policy**: Deletes backup archives older than 30 days.
- **Log File**: `/home/genmonpi/backup.log`
- **Cron Schedule**: Daily at 4:00 AM
  ```cron
  0 4 * * * /home/genmonpi/backup_to_mac.sh
  ```

### Backup Script 2: Weekly Live SD Card Image (`/home/genmonpi/sdcard_backup_to_mac.sh`)
- Uses the `image-backup` utility (`/usr/local/bin/image-backup` from `RonR-RPi-image-utils`).
- Installed dependencies: `bc`, `kpartx`, `rsync`, `parted`, `dosfstools`, `e2fsprogs`.
- Creates live full system image: `/mnt/pibackup/genmon_sdcard_YYYY-MM-DD_HHMMSS.img`.
- **Retention Policy**: Retains the 4 most recent weekly SD card images.
- **Log File**: `/home/genmonpi/sdcard_backup.log`
- **Cron Schedule**: Weekly on Sunday at 4:00 AM
  ```cron
  0 4 * * 0 /home/genmonpi/sdcard_backup_to_mac.sh
  ```

---

## 5. Web UI Optimization & FOUC Prevention

To prevent **Flash of Unstyled Content (FOUC)** when loading the Genmon web interface (such as a white flash before dark mode loads):
- **CSS Preloading**: Core stylesheet `css/genmon.css` is preloaded via `<link rel="preload" href="css/genmon.css" as="style">` in template `<head>` sections.
- **Visibility Transition**: Inline CSS and DOM ready scripts enforce `visibility: hidden; opacity: 0;` until stylesheets and theme initialization complete, fading in smoothly via `.fouc-ready` class.

---

## 6. GitHub Fork & Git Workflow

The project is maintained on a personal GitHub fork: **[`wizofoz244/genmon`](https://github.com/wizofoz244/genmon)**.

### Remote Configuration
- `origin`: `https://github.com/wizofoz244/genmon.git` (Personal Fork)
- `upstream`: `https://github.com/jgyates/genmon.git` (Official Repository)

### Mac to Raspberry Pi Deployment Workflow

1. **On Mac**: Commit and push changes:
   ```bash
   git add .
   git commit -m "Description of updates"
   git push origin master
   ```

2. **On Raspberry Pi**: Pull updates:
   ```bash
   cd ~/genmon
   git pull origin master
   ```

3. **Syncing Upstream Genmon Updates**:
   ```bash
   git fetch upstream
   git merge upstream/master
   git push origin master
   ```

---

## 7. Raspberry Pi Systemd Service Deployment

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
