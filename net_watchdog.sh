#!/bin/bash
# ==============================================================================
# Production-Grade Network Watchdog for Genmon & USB Wi-Fi (Raspberry Pi)
# ==============================================================================

# Ensure Cron environment has access to all standard system binaries
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

# Prevent overlapping script execution using File Locking
LOCK_FILE="/tmp/net_watchdog.lock"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    # Another instance is actively running (e.g., waiting on network reset timeout)
    exit 0
fi

# ==============================================================================
# CONFIGURATION
# ==============================================================================
FALLBACK_ROUTER_IP="192.168.1.1"   # Set your router's static IP fallback here
INTERFACE_FALLBACK="wlan0"           # USB Wi-Fi adapter (wlan0)
MAX_LOG_LINES=500
MAX_RESET_ATTEMPTS=2                # Soft-reset network N times (~6 mins) before rebooting
MAX_CONSECUTIVE_REBOOTS=3           # Max reboots before pausing to protect SD card

LOG_FILE="/var/log/net-watchdog.log"
RESET_COUNT_FILE="/tmp/net_watchdog_reset_count"
REBOOT_COUNT_FILE="/var/tmp/net_watchdog_reboot_count"

# Helper for log file management
log_msg() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
    if [ -f "$LOG_FILE" ] && [ "$(wc -l < "$LOG_FILE")" -gt "$MAX_LOG_LINES" ]; then
        tail -n "$MAX_LOG_LINES" "$LOG_FILE" > "$LOG_FILE.tmp" && mv "$LOG_FILE.tmp" "$LOG_FILE"
    fi
}

# Gateway & Interface Auto-Detection
DETECTED_IP=$(ip route show default 2>/dev/null | awk '/default/ {print $3}' | head -n 1)
DETECTED_IF=$(ip route show default 2>/dev/null | awk '/default/ {print $5}' | head -n 1)

# Validate IP format using regex
IP_REGEX="^([0-9]{1,3}\.){3}[0-9]{1,3}$"
if [[ "$DETECTED_IP" =~ $IP_REGEX ]]; then
    ROUTER_IP="$DETECTED_IP"
else
    ROUTER_IP="$FALLBACK_ROUTER_IP"
fi

if [ -n "$DETECTED_IF" ]; then
    INTERFACE="$DETECTED_IF"
else
    INTERFACE="$INTERFACE_FALLBACK"
fi

# Disable Wi-Fi Power Saving (Prevents USB Wi-Fi sleeping when idle)
if command -v iw &> /dev/null && [ -d "/sys/class/net/$INTERFACE" ]; then
    iw dev "$INTERFACE" set power_save off 2>/dev/null
fi

# 1. Ping Test - Attempt 1
if ping -c 3 -W 5 "$ROUTER_IP" > /dev/null 2>&1; then
    # Connection Healthy: Clear error & reset counters
    if [ -f "$RESET_COUNT_FILE" ] || [ -f "$REBOOT_COUNT_FILE" ]; then
        log_msg "SUCCESS: Connected to $ROUTER_IP on $INTERFACE. Clearing error states."
        rm -f "$RESET_COUNT_FILE" "$REBOOT_COUNT_FILE"
    fi
    exit 0
fi

# 2. Brief Router Reboot / Transient Glitch. Wait 15s and retry ping before acting
sleep 15
if ping -c 3 -W 5 "$ROUTER_IP" > /dev/null 2>&1; then
    log_msg "INFO: Recovered on 2nd ping check (transient glitch/router reboot)."
    rm -f "$RESET_COUNT_FILE" "$REBOOT_COUNT_FILE" 2>/dev/null
    exit 0
fi

# 3. Read current soft reset count
RESET_COUNT=$(cat "$RESET_COUNT_FILE" 2>/dev/null || echo 0)

# STEP 1: Attempt Soft Network & USB Reset if below max reset limit
if [ "$RESET_COUNT" -lt "$MAX_RESET_ATTEMPTS" ]; then
    RESET_COUNT=$((RESET_COUNT + 1))
    echo "$RESET_COUNT" > "$RESET_COUNT_FILE"

    log_msg "WARNING: Failed to ping $ROUTER_IP on $INTERFACE (Attempt $RESET_COUNT/$MAX_RESET_ATTEMPTS). Initiating soft network reset..."

    # If USB Wi-Fi dongle hardware disappeared from OS (/sys/class/net/wlan0 missing)
    if [ ! -d "/sys/class/net/$INTERFACE" ]; then
        log_msg "WARNING: Interface $INTERFACE disappeared! Attempting USB hub driver rebind..."
        for usb_dev in /sys/bus/usb/drivers/usb/*-*; do
            if [ -e "$usb_dev" ]; then
                echo "$(basename "$usb_dev")" > /sys/bus/usb/drivers/usb/unbind 2>/dev/null
                sleep 1
                echo "$(basename "$usb_dev")" > /sys/bus/usb/drivers/usb/bind 2>/dev/null
            fi
        done
        sleep 5
    fi

    # Reset Network Stack
    if command -v nmcli &> /dev/null; then
        timeout 15 nmcli radio wifi off 2>/dev/null
        timeout 15 nmcli networking off 2>/dev/null
        sleep 3
        timeout 15 nmcli networking on 2>/dev/null
        timeout 15 nmcli radio wifi on 2>/dev/null
    else
        timeout 10 ip link set "$INTERFACE" down 2>/dev/null
        sleep 2
        timeout 10 ip link set "$INTERFACE" up 2>/dev/null
        timeout 15 systemctl restart wpa_supplicant 2>/dev/null
        timeout 15 systemctl restart dhcpcd 2>/dev/null || timeout 15 systemctl restart systemd-networkd 2>/dev/null
    fi
    exit 0
fi

# STEP 2: Network resets failed after N attempts (~6 mins total). Evaluate System Reboot
REBOOT_COUNT=$(cat "$REBOOT_COUNT_FILE" 2>/dev/null || echo 0)
REBOOT_COUNT=$((REBOOT_COUNT + 1))
echo "$REBOOT_COUNT" > "$REBOOT_COUNT_FILE"

if [ "$REBOOT_COUNT" -gt "$MAX_CONSECUTIVE_REBOOTS" ]; then
    log_msg "CRITICAL: Router $ROUTER_IP unreachable after $MAX_CONSECUTIVE_REBOOTS reboots. Pausing reboots to protect SD card."
    # Reset soft-reset counter so it cycles network resets instead of endless reboots
    rm -f "$RESET_COUNT_FILE"
    exit 0
fi

log_msg "CRITICAL: Router $ROUTER_IP unreachable on $INTERFACE after $MAX_RESET_ATTEMPTS resets (~6+ mins). Initiating graceful reboot (Reboot $REBOOT_COUNT/$MAX_CONSECUTIVE_REBOOTS)..."

# Safely stop Genmon service before rebooting to prevent log file corruption
log_msg "Stopping Genmon service cleanly..."
systemctl stop genmon 2>/dev/null || systemctl stop startgenmon 2>/dev/null

# Clean reset count state for fresh boot
rm -f "$RESET_COUNT_FILE"

# Flush write buffers to disk to protect SD card / SSD
sync
sleep 2

# Execute Reboot
/sbin/reboot -f || /sbin/reboot
