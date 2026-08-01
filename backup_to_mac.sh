#!/bin/bash
# -------------------------------------------------------------------------------
# Daily Genmon Configuration & Log Backup Script with Integrity Pre-Check
# -------------------------------------------------------------------------------

LOG_FILE="/home/genmonpi/backup.log"
GENMON_DIR="/home/genmonpi/genmon"
CONF_DIR="/etc/genmon"
TARGET_DIR="/mnt/pibackup/daily"
BACKUP_ARCHIVE="${TARGET_DIR}/genmon_daily_master.tar.gz"

log() {
    local level="${1:-INFO}"
    shift
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$level] $*" | tee -a "$LOG_FILE"
}

# Check for stale network mount and attempt auto-remount recovery
check_and_fix_stale_mount() {
    local target="$1"

    if ! timeout 5 sudo touch "${target}/.mount_test" >/dev/null 2>&1; then
        log "WARN" "Stale or unresponsive network mount detected at ${target} (No such device / Stale file handle)!"
        log "WARN" "Attempting lazy unmount and automatic remount..."

        sudo umount -l -f "$target" >/dev/null 2>&1
        sleep 2
        sudo mount "$target" >/dev/null 2>&1 || sudo mount -a >/dev/null 2>&1
        sleep 2

        if timeout 5 sudo touch "${target}/.mount_test" >/dev/null 2>&1; then
            sudo rm -f "${target}/.mount_test" >/dev/null 2>&1
            log "INFO" "✓ Successfully recovered and remounted ${target}."
            return 0
        else
            log "ERROR" "Failed to recover network mount ${target}. Host or network share is unreachable!"
            return 1
        fi
    else
        sudo rm -f "${target}/.mount_test" >/dev/null 2>&1
        return 0
    fi
}

log "INFO" "=================================================="
log "INFO" "Starting Daily Genmon Backup Procedure..."

if ! check_and_fix_stale_mount "$TARGET_DIR"; then
    exit 1
fi

mkdir -p "$TARGET_DIR" 2>/dev/null

# Integrity check for tar.gz archive
check_archive_integrity() {
    local archive="$1"
    if [ ! -f "$archive" ]; then
        return 1
    fi
    tar -tzf "$archive" >/dev/null 2>&1
    return $?
}

# Pre-Check Master Archive Integrity
if [ -f "$BACKUP_ARCHIVE" ]; then
    log "INFO" "Verifying integrity of existing master backup archive: $BACKUP_ARCHIVE..."
    if ! check_archive_integrity "$BACKUP_ARCHIVE"; then
        log "WARN" "CORRUPTION DETECTED! Existing master archive ($BACKUP_ARCHIVE) is corrupt or invalid."
        log "WARN" "Removing corrupt master archive..."
        rm -f "$BACKUP_ARCHIVE"
        log "INFO" "Removed corrupt master archive."
    else
        log "INFO" "Master archive passed integrity check."
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

# Create fresh daily backup archive
STAGING_TAR="/tmp/genmon_daily_$(date '+%Y-%m-%d_%H%M%S').tar.gz"
log "INFO" "Creating staging backup archive ($STAGING_TAR)..."

tar -czf "$STAGING_TAR" -C / "$CONF_DIR" "$GENMON_DIR/maintlog.json" "$GENMON_DIR/maint_sync_state.json" 2>> "$LOG_FILE"

sync_daily_backup() {
    cp "$STAGING_TAR" "$BACKUP_ARCHIVE" 2>> "$LOG_FILE"
}

if check_archive_integrity "$STAGING_TAR"; then
    log "INFO" "Staging archive integrity verified. Syncing to master backup target..."
    if retry_cmd sync_daily_backup; then
        rm -f "$STAGING_TAR"
        log "INFO" "✓ Daily Genmon Backup completed successfully ($BACKUP_ARCHIVE)."
    else
        log "ERROR" "Failed to sync daily backup archive to $BACKUP_ARCHIVE!"
        rm -f "$STAGING_TAR"
        exit 1
    fi
else
    log "ERROR" "Failed to create valid daily backup archive!"
    rm -f "$STAGING_TAR"
    exit 1
fi

# Retain 7 daily snapshots
SNAPSHOT="${TARGET_DIR}/genmon_daily_$(date '+%Y-%m-%d_%H%M%S').tar.gz"
cp "$BACKUP_ARCHIVE" "$SNAPSHOT" 2>/dev/null
ls -t "${TARGET_DIR}"/genmon_daily_*.tar.gz 2>/dev/null | tail -n +8 | xargs -r rm -f

log "INFO" "=================================================="
exit 0
