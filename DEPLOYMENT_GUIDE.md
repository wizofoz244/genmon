# Genmon Custom Setup & Deployment Guide

This document captures the complete configuration, data processing pipeline, custom add-ons, GitHub fork management, and Raspberry Pi systemd deployment for this Genmon generator monitoring system.

---

## Architecture Overview

```
 +-------------------------------------------------------------------------+
 |                            Raspberry Pi                                 |
 |                                                                         |
 |  +--------------------+         Socket RPC          +----------------+  |
 |  |   Genmon Daemon    | <-------------------------> | genmaint_sync  |  |
 |  |    (genmond)       | (port 9082 / generator:*)   |  Add-on Daemon |  |
 |  +--------------------+                             +----------------+  |
 |            |                                                |           |
 |            v                                                v           |
 |  /etc/genmon/maintlog.json  <-------------------------------+           |
 |  /etc/genmon/outage.txt                                                 |
 |  /etc/genmon/outage_summary.csv                                         |
 +-------------------------------------------------------------------------+
```

---

## 1. Maintenance Journal & Outage Log Data Pipeline

### Maintenance Log (`maintlog.json`)
- **Location**: `/etc/genmon/maintlog.json`
- **Entry Schema**:
  ```json
  {
      "date": "MM/DD/YYYY HH:MM",
      "type": "Maintenance | Check | Repair | Observation",
      "hours": 138.9,
      "comment": "Description of event or service item"
  }
  ```
- **Engine Hours Calculation**:
  - Accounts for controller replacement on **06/20/2026** (baseline reference of **138.9 hours**).
  - Integrates cumulative runtime from engine sessions (Exercise, Utility Loss, Manual).

### Outage Log & Fuel Estimation (`outage.txt` & `outage_summary.csv`)
- **Locations**: `/etc/genmon/outage.txt`, `/etc/genmon/outage_summary.csv`
- **Fuel Rate**: `200.0 cubic feet / hour` (Natural Gas).
- Excludes 5-minute weekly exercise sessions from outage fuel calculations.

---

## 2. Automated Run & Alarm Log Sync (`addon/genmaint_sync.py`)

A standalone add-on daemon that monitors the generator controller's sliding 50-entry **Run Log** and **Alarm Log** via Genmon's RPC socket interface.

### Features
- **Classification**: Converts all new controller log events into `type: "Observation"` entries.
- **Engine Run Hours**: Assigns live engine run hours for current events and back-interpolates engine hours for buffered past events based on run session durations.
- **Deduplication**: Maintains state in `/etc/genmon/maint_sync_state.json` and checks existing `maintlog.json` records before appending.
- **Atomic Writes**: Uses temporary files and `os.replace` to protect files against power outages or abrupt shutdowns.

### CLI Options
```bash
sudo python3 ~/genmon/addon/genmaint_sync.py -c /etc/genmon [options]
```
- `-1`, `--oneshot`: Run a single pass and exit.
- `-d`, `--dry-run`: Preview calculations without modifying files.
- `-r`, `--recalculate-hours`: Update existing 0.0 hour `Observation` entries.
- `-i`, `--interval`: Set polling frequency (default: 60s).

---

## 3. GitHub Fork & Git Workflow

The project is maintained on a personal GitHub fork: **[`wizofoz244/genmon`](https://github.com/wizofoz244/genmon)**.

### Remote Configuration
- `origin`: `https://github.com/wizofoz244/genmon.git` (Personal Fork)
- `upstream`: `https://github.com/jgyates/genmon.git` (Official Repository)

### Development Workflow (Mac to Raspberry Pi)

1. **On your Mac**: Commit and push changes to your GitHub fork:
   ```bash
   git add .
   git commit -m "Describe your changes"
   git push origin master
   ```

2. **On your Raspberry Pi**: Pull updates from your GitHub fork:
   ```bash
   cd ~/genmon
   git pull origin master
   ```

---

## 4. Raspberry Pi Deployment & Systemd Service

### User Context
- **Raspberry Pi Username**: `genmonpi`
- **Genmon Directory**: `/home/genmonpi/genmon`
- **Config Directory**: `/etc/genmon`

### Systemd Service Setup (`genmaint_sync.service`)

The add-on is configured to start automatically on system boot after the network is online, continuously retrying until Genmon is available.

#### 1. Create `/etc/systemd/system/genmaint_sync.service`:
```bash
sudo bash -c 'cat << "EOF" > /etc/systemd/system/genmaint_sync.service
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
EOF'
```

#### 2. Enable & Start Service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable genmaint_sync.service
sudo systemctl start genmaint_sync.service
```

#### 3. Monitor Service Status & Logs:
```bash
# Check service status
sudo systemctl status genmaint_sync.service

# Live follow file log
sudo tail -f /etc/genmon/genmaint_sync.log

# Live follow systemd journal
sudo journalctl -u genmaint_sync.service -f
```

---

## 5. Maintenance & Troubleshooting Commands

- **Sync Check (One-shot test)**:
  ```bash
  sudo python3 /home/genmonpi/genmon/addon/genmaint_sync.py -c /etc/genmon --oneshot
  ```
- **Recalculate Zero-Hour Entries**:
  ```bash
  sudo python3 /home/genmonpi/genmon/addon/genmaint_sync.py -c /etc/genmon --oneshot --recalculate-hours
  ```
- **Syncing Upstream Genmon Core Updates**:
  ```bash
  git fetch upstream
  git merge upstream/master
  git push origin master
  ```
