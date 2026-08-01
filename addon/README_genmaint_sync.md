# Genmon Service Journal Sync Addon (`genmaint_sync.py`)

`genmaint_sync.py` is an automated synchronization add-on for Genmon. Generator controllers (such as Generac Evolution and Nexus models) store a sliding window of up to 50 historical entries in their internal **Run Log** and **Alarm Log**. 

This add-on monitors the controller via Genmon's RPC socket interface (`generator: logs_json` and `generator: status_json`). When new or updated log events occur on the controller, `genmaint_sync.py` automatically:
1. Parses and formats events from the **Run Log**, **Alarm Log**, and **Service Log**.
2. Classifies entries according to type:
   - Alarm and Run Log events $\rightarrow$ `Observation`
   - Service Log interval events (e.g. `interval reached`, `due`) $\rightarrow$ `Observation`
   - Service Log reset/maintenance events (e.g. `Reset Maintenance`, `performed`) $\rightarrow$ `Maintenance`
3. Calculates or interpolates exact **Engine Run Hours** for each event based on live engine runtime and session durations.
4. Appends the new entries to `maintlog.json` while maintaining persistent state to prevent duplicate records.

---

## Features

- **Automated Log Sync**: Periodically polls the 50-entry controller Run & Alarm logs.
- **Accurate Engine Run Hours**:
  - Live events receive the current live engine run hours reported by Genmon.
  - Historical buffered events have their run hours interpolated by calculating engine run time accumulated during intervening run sessions.
- **Deduplication & State Persistence**: Tracks processed event signatures in `maint_sync_state.json` and checks existing `maintlog.json` records before appending.
- **Atomic File Operations**: Uses temporary file writes and atomic replacements (`os.replace`) to prevent file corruption during power interruptions or system reboots.
- **Flexible Execution Modes**: Supports continuous daemon service, one-shot CLI execution, dry-run previews, and zero-hour recalculation.

---

## Command Line Usage

```bash
python3 addon/genmaint_sync.py [options]
```

### Options

| Option | Long Flag | Default | Description |
| :--- | :--- | :--- | :--- |
| `-a` | `--address` | `127.0.0.1` | Genmon server IP address or hostname. |
| `-p` | `--port` | `9082` | Genmon server RPC port. |
| `-c` | `--configpath` | `/etc/genmon` | Path to Genmon configuration directory containing `maintlog.json`. |
| `-i` | `--interval` | `60` | Polling interval in seconds for daemon mode. |
| `-1` | `--oneshot` | `False` | Run a single synchronization pass and exit. |
| `-d` | `--dry-run` | `False` | Parse and calculate entries without modifying `maintlog.json` or state files. |
| `-r` | `--recalculate-hours` | `False` | Recalculate engine run hours for existing `Observation` entries with `0.0` hours. |

---

## Usage Examples

### 1. Single Sync Pass (One-shot)
```bash
sudo python3 addon/genmaint_sync.py -c /etc/genmon --oneshot
```

### 2. Preview Changes (Dry Run)
```bash
sudo python3 addon/genmaint_sync.py -c /etc/genmon --oneshot --dry-run
```

### 3. Recalculate Existing Zero-Hour Entries
```bash
sudo python3 addon/genmaint_sync.py -c /etc/genmon --oneshot --recalculate-hours
```

---

## Systemd Autostart Configuration

To automatically run `genmaint_sync.py` as a background daemon when your system boots up:

### 1. Create `/etc/systemd/system/genmaint_sync.service`
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
*(Note: Replace `/home/genmonpi/genmon` with your actual Genmon installation path if different).*

### 2. Enable and Start the Service
```bash
sudo systemctl daemon-reload
sudo systemctl enable genmaint_sync.service
sudo systemctl start genmaint_sync.service
```

### 3. Check Status
```bash
sudo systemctl status genmaint_sync.service
```

---

## Logging & Monitoring

`genmaint_sync.py` records operation logs to two locations:

1. **Log File**: `/etc/genmon/genmaint_sync.log`
   ```bash
   sudo tail -f /etc/genmon/genmaint_sync.log
   ```
   *(Rotated automatically at 50KB with up to 5 backups preserved).*

2. **Systemd Journal**:
   ```bash
   sudo journalctl -u genmaint_sync.service -f
   ```

---

## Unit Testing

A comprehensive unit test suite is included in `addon/test_genmaint_sync.py`. Run tests using:

```bash
python3 -m unittest addon/test_genmaint_sync.py
```
