# Genmon Network Watchdog & Auto-Reboot (`net_watchdog.sh`)

`net_watchdog.sh` is an automated network monitoring, recovery, and failover script designed for Raspberry Pi systems running Genmon (specifically optimized for USB Wi-Fi adapters like `wlan0` and Ethernet interfaces).

Generators are frequently placed outdoors or in metal enclosures where Wi-Fi signal fluctuations, access point reboots, or USB driver lockups can cause temporary network loss. `net_watchdog.sh` monitors connection health to your local router/gateway and executes a **multi-stage recovery pipeline** to restore connectivity without corrupting Genmon data or wearing out SD card storage.

---

## 1. Execution Flow & Architecture

```
 +-------------------------------------------------------------------------------+
 |                              Cron Schedule (every 3 min)                       |
 +-------------------------------------------------------------------------------+
                                         |
                                         v
 +-------------------------------------------------------------------------------+
 |                         1. File Lock & Path Initialization                    |
 |                    (Ensures no overlapping Cron executions)                    |
 +-------------------------------------------------------------------------------+
                                         |
                                         v
 +-------------------------------------------------------------------------------+
 |                  2. Auto-Detect Router IP & Network Interface                 |
 |                (Fallback to wlan0 / 192.168.1.1 if route is down)            |
 +-------------------------------------------------------------------------------+
                                         |
                                         v
 +-------------------------------------------------------------------------------+
 |                         3. Disable Wi-Fi Power Save                           |
 |               (Prevents USB Wi-Fi dongles from sleeping idle)                 |
 +-------------------------------------------------------------------------------+
                                         |
                                         v
 +-------------------------------------------------------------------------------+
 |                         4. Ping Gateway (3 packets, 5s)                        |
 +-------------------------------------------------------------------------------+
             /                                                 \
        [ SUCCESS ]                                        [ FAILURE ]
           /                                                     \
          v                                                       v
 Clear Failure State & Exit                        Wait 15s & Retry Ping (2nd Check)
                                                   (Filters transient router blips)
                                                                  |
                                                              [ STILL DOWN ]
                                                                  |
                                                                  v
                                              Check Soft Reset Count (< MAX_RESET_ATTEMPTS)
                                             /                                          \
                                       [ YES (< 2) ]                               [ NO (>= 2) ]
                                            /                                              \
                                           v                                                v
                   STEP 1: Soft Network & USB Driver Reset               STEP 2: Graceful System Reboot
                   - Unbind/Rebind USB Hub if wlan0 missing             - Stop genmon.service cleanly
                   - Restart nmcli / dhcpcd / wpa_supplicant             - Sync disk write buffers
                   - Increment reset counter & exit                     - Issue /sbin/reboot
```

---

## 2. Key Capabilities & Edge Case Protections

### 1. Access Point & Mesh Router Boot Window
Many home mesh Wi-Fi routers (UniFi, Eero, Orbi, pfSense) take **2 to 4 minutes** to complete a reboot. `net_watchdog.sh` enforces a `MAX_RESET_ATTEMPTS=2` threshold over consecutive Cron runs. This grants your network access point a **~6-minute grace window** to finish booting up before the Pi considers triggering a full system reboot.

### 2. The "Empty Gateway" Route Trap
When a network connection drops completely, standard commands like `ip route show default` return an empty string. Basic scripts fail with syntax errors when passing empty arguments to `ping`. `net_watchdog.sh` validates IP formatting via regex; if no default route exists, it falls back cleanly to `FALLBACK_ROUTER_IP`.

### 3. USB Wi-Fi Dongle Hardware Lockups
Cheap or high-gain USB Wi-Fi adapters can experience hardware-level firmware freezes where the interface (`wlan0`) completely disappears from `/sys/class/net/`. Soft network commands (`nmcli`, `ip link`) will fail. The script detects missing interfaces and automatically unbinds and rebinds the USB bus controller (`/sys/bus/usb/drivers/usb/unbind`), effectively power-cycling the USB port.

### 4. Genmon Journal & Log Protection
Triggering a abrupt system reboot while Genmon is actively communicating over serial or updating maintenance logs (`maintlog.json`) can lead to JSON file corruption. Before rebooting, `net_watchdog.sh` issues `systemctl stop genmon` and calls `sync` to flush all pending write operations to storage.

### 5. Flash Storage (SD Card / SSD) Lifespan Protection
If your router suffers a multi-hour power outage or ISP blackout, continuous reboots every 6 minutes will wear out flash memory cells. The script tracks consecutive reboots in `/var/tmp/net_watchdog_reboot_count` and pauses reboots after `MAX_CONSECUTIVE_REBOOTS=3`, resuming soft network resets until the router returns.

### 6. Overlapping Cron Lock Control
If a network restart command takes 15–20 seconds to complete, Cron could launch a second instance of the watchdog script simultaneously. `net_watchdog.sh` uses `flock` file locking on `/tmp/net_watchdog.lock` to ensure only one instance executes at a time.

---

## 3. Configuration Parameters

The top section of `net_watchdog.sh` contains user-configurable parameters:

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `FALLBACK_ROUTER_IP` | `"192.168.1.1"` | Static IP address of your router/gateway to ping if auto-detection fails. |
| `INTERFACE_FALLBACK` | `"wlan0"` | Fallback network interface name (`wlan0`, `eth0`, `end0`, `wlan1`). |
| `MAX_LOG_LINES` | `500` | Maximum line count for `/var/log/net-watchdog.log` before auto-trimming. |
| `MAX_RESET_ATTEMPTS` | `2` | Number of soft network resets to attempt before triggering a reboot (~6 min window). |
| `MAX_CONSECUTIVE_REBOOTS` | `3` | Maximum consecutive system reboots allowed before pausing to protect SD card. |

---

## 4. Cron Setup & Installation

### Step 1: Place Script in Genmon Directory
Ensure the script is located in your Genmon directory (e.g. `/home/genmonpi/genmon/net_watchdog.sh`) and has execution permissions:

```bash
chmod +x /home/genmonpi/genmon/net_watchdog.sh
```

### Step 2: Configure Root Crontab
Because network interface management and system reboots require superuser privileges, the script must be scheduled under **root's crontab**:

```bash
sudo crontab -e
```

Add the following schedule line:

```cron
# Run Genmon Network Watchdog every 3 minutes
*/3 * * * * /home/genmonpi/genmon/net_watchdog.sh
```

---

## 5. Inspection & Logs

The script logs all operational events and recovery steps to `/var/log/net-watchdog.log`.

### Viewing Real-Time Logs
```bash
sudo tail -f /var/log/net-watchdog.log
```

### Sample Log Output
```text
2026-08-02 16:15:00 - WARNING: Failed to ping 192.168.1.1 on wlan0 (Attempt 1/2). Initiating soft network reset...
2026-08-02 16:18:00 - INFO: Recovered on 2nd ping check (transient glitch/router reboot).
2026-08-02 16:18:00 - SUCCESS: Connected to 192.168.1.1 on wlan0. Clearing error states.
```
