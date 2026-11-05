#!/bin/bash
# -------------------------------------------------------------------------------
# Daily Genmon Configuration & Log Backup Script with Integrity Pre-Check
# -------------------------------------------------------------------------------

LOG_FILE="/home/genmonpi/backup.log"
GENMON_DIR="/home/genmonpi/genmon"
CONF_DIR="/etc/genmon"
TARGET_DIR="/mnt/pibackup"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FILTER_UTIL="${SCRIPT_DIR}/backup_progress_filter.py"

log() {
    local level="${1:-INFO}"
    shift
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$level] $*" | tee -a "$LOG_FILE"
}

# Check for stale network mount and attempt auto-remount recovery
check_and_fix_stale_mount() {
    local target="$1"
    local test_file="${target}/.mount_test_$$"

    # Lightweight stat check first to avoid blocking on write queues
    if timeout 15 stat "$target" >/dev/null 2>&1 && timeout 15 touch "$test_file" >/dev/null 2>&1; then
        rm -f "$test_file" >/dev/null 2>&1
        return 0
    fi

    log "WARN" "Network mount at ${target} is unresponsive or stale!"
    log "WARN" "Attempting recovery via systemd automount..."

    sudo umount -l -f "$target" >/dev/null 2>&1
    sleep 2
    sudo systemctl restart mnt-pibackup.automount >/dev/null 2>&1 || sudo mount "$target" >/dev/null 2>&1 || sudo mount -a >/dev/null 2>&1
    sleep 2

    if timeout 20 stat "$target" >/dev/null 2>&1 && timeout 20 touch "$test_file" >/dev/null 2>&1; then
        rm -f "$test_file" >/dev/null 2>&1
        log "INFO" "✓ Successfully recovered and remounted ${target}."
        return 0
    else
        log "ERROR" "Failed to recover network mount ${target}. Host or network share is unreachable!"
        return 1
    fi
}

log "INFO" "=================================================="
log "INFO" "Starting Daily Genmon Backup Procedure..."

# Mutual Exclusion: Ensure weekly SD card backup is not running concurrently
if pgrep -f "sdcard_backup_to_mac.sh" >/dev/null 2>&1; then
    log "WARN" "Weekly SD Card Backup is currently in progress. Skipping daily backup to prevent I/O conflict."
    exit 0
fi

if ! check_and_fix_stale_mount "$TARGET_DIR"; then
    exit 1
fi

# Integrity check for tar.gz archive
check_archive_integrity() {
    local archive="$1"
    if [ ! -f "$archive" ]; then
        return 1
    fi
    tar -tzf "$archive" >/dev/null 2>&1
    return $?
}

# Pre-Check Most Recent Daily Archive Integrity
LATEST_BACKUP=$(ls -t "${TARGET_DIR}"/genmon_daily_*.tar.gz 2>/dev/null | head -n 1)
if [ -n "$LATEST_BACKUP" ] && [ -f "$LATEST_BACKUP" ]; then
    log "INFO" "Verifying integrity of most recent daily archive: $LATEST_BACKUP..."
    if ! check_archive_integrity "$LATEST_BACKUP"; then
        log "WARN" "CORRUPTION DETECTED! Existing archive ($LATEST_BACKUP) is corrupt or invalid."
        rm -f "$LATEST_BACKUP"
        log "INFO" "Removed corrupt archive."
    else
        log "INFO" "Most recent daily archive passed integrity check."
    fi
fi

# Execute command with retry loop and exponential backoff for network resiliency
retry_cmd() {
    local max_attempts=3
    local delay=5
    local attempt=1
    local rc=0

    while [ $attempt -le $max_attempts ]; do
        "$@"
        rc=$?
        if [ $rc -eq 0 ]; then
            return 0
        fi

        log "WARN" "Daily backup operation failed with exit code $rc (Attempt $attempt/$max_attempts)."
        if [ $attempt -lt $max_attempts ]; then
            log "WARN" "Retrying in ${delay} seconds after verifying network mount health..."
            sleep $delay
            check_and_fix_stale_mount "$TARGET_DIR"
            delay=$((delay * 2))
        fi
        attempt=$((attempt + 1))
    done

    return $rc
}

# Create fresh daily backup archive (1 per day of the week)
BACKUP_DATE=$(date '+%Y-%m-%d_%H%M%S')
STAGING_TAR="/tmp/genmon_daily_${BACKUP_DATE}.tar.gz"
FINAL_ARCHIVE="${TARGET_DIR}/genmon_daily_${BACKUP_DATE}.tar.gz"

log "INFO" "Creating staging backup archive ($STAGING_TAR)..."

tar -czf "$STAGING_TAR" -C / "$CONF_DIR" "$GENMON_DIR/maintlog.json" "$GENMON_DIR/maint_sync_state.json" 2>> "$LOG_FILE"

sync_daily_backup() {
    if [ -f "$FILTER_UTIL" ] && command -v rsync >/dev/null 2>&1; then
        rsync --info=progress2 "$STAGING_TAR" "$FINAL_ARCHIVE" 2>&1 | python3 "$FILTER_UTIL" --log-file "$LOG_FILE" --interval 60 --pct-step 5
        return ${PIPESTATUS[0]}
    else
        cp "$STAGING_TAR" "$FINAL_ARCHIVE" 2>> "$LOG_FILE"
        return $?
    fi
}

if check_archive_integrity "$STAGING_TAR"; then
    log "INFO" "Staging archive integrity verified. Syncing to backup target..."
    if retry_cmd sync_daily_backup; then
        rm -f "$STAGING_TAR"
        log "INFO" "✓ Daily Genmon Backup completed successfully ($FINAL_ARCHIVE)."
    else
        log "ERROR" "Failed to sync daily backup archive to $FINAL_ARCHIVE!"
        rm -f "$STAGING_TAR"
        exit 1
    fi
else
    log "ERROR" "Failed to create valid daily backup archive!"
    rm -f "$STAGING_TAR"
    exit 1
fi

# Retain 7 daily snapshots (one per day of the week, deleting older ones)
log "INFO" "Applying retention policy: retaining the 7 most recent daily archives..."
ls -t "${TARGET_DIR}"/genmon_daily_*.tar.gz 2>/dev/null | tail -n +8 | xargs -r rm -f

# Clean up legacy master archive if present from earlier script versions
rm -f "${TARGET_DIR}/genmon_daily_master.tar.gz" 2>/dev/null

log "INFO" "=================================================="
exit 0
