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

log "INFO" "=================================================="
log "INFO" "Starting Daily Genmon Backup Procedure..."

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

# Create fresh daily backup archive
STAGING_TAR="/tmp/genmon_daily_$(date '+%Y-%m-%d_%H%M%S').tar.gz"
log "INFO" "Creating staging backup archive ($STAGING_TAR)..."

tar -czf "$STAGING_TAR" -C / "$CONF_DIR" "$GENMON_DIR/maintlog.json" "$GENMON_DIR/maint_sync_state.json" 2>> "$LOG_FILE"

if check_archive_integrity "$STAGING_TAR"; then
    log "INFO" "Staging archive integrity verified. Syncing to master backup target..."
    mv "$STAGING_TAR" "$BACKUP_ARCHIVE"
    log "INFO" "✓ Daily Genmon Backup completed successfully ($BACKUP_ARCHIVE)."
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
