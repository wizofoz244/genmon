#!/bin/bash
# -------------------------------------------------------------------------------
# Weekly Live SD Card Image Backup Script with Corruption Protection & Auto-Healing
# -------------------------------------------------------------------------------

LOG_FILE="/home/genmonpi/sdcard_backup.log"
TARGET_DIR="/mnt/pibackup"
MASTER_IMG="${TARGET_DIR}/genmon_sdcard_master.img"
BACKUP_UTIL="/usr/local/bin/image-backup"

# Helper for formatted log messages: [YYYY-MM-DD HH:MM:SS] [LEVEL] Message
log() {
    local level="${1:-INFO}"
    shift
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$level] $*" | tee -a "$LOG_FILE"
}

# Emergency Signal Trap & Resource Cleanup
cleanup() {
    local rc=$?
    # Unmount temporary image backup mount points if left behind
    if mountpoint -q /tmp/img-backup-mnt 2>/dev/null; then
        sudo umount -l -f /tmp/img-backup-mnt 2>/dev/null
    fi
    # Detach any orphan loop devices associated with backup images
    for dev in $(losetup -a 2>/dev/null | grep "genmon_sdcard" | cut -d: -f1); do
        sudo losetup -d "$dev" 2>/dev/null
    done
    if [ $rc -ne 0 ] && [ $rc -ne 130 ]; then
        log "WARN" "Cleaned up temporary mounts and loop devices after abnormal exit."
    fi
}
trap cleanup EXIT INT TERM

# Check for required system packages
check_dependencies() {
    local missing=()
    for pkg in kpartx rsync parted bc dosfstools e2fsck; do
        if ! command -v "$pkg" >/dev/null 2>&1; then
            missing+=("$pkg")
        fi
    done

    if [ ${#missing[@]} -ne 0 ]; then
        log "WARN" "Missing recommended backup utilities: ${missing[*]}"
        log "WARN" "Consider installing them: sudo apt-get update && sudo apt-get install -y ${missing[*]}"
    fi
}

# Check available disk space on backup target (requires at least 10GB free)
check_disk_space() {
    local target="$1"
    local free_kb
    free_kb=$(df -P "$target" 2>/dev/null | awk 'NR==2 {print $4}')
    if [ -n "$free_kb" ]; then
        local free_gb=$((free_kb / 1048576))
        log "INFO" "Available disk space on ${target}: ${free_gb} GB."
        if [ "$free_gb" -lt 10 ]; then
            log "WARN" "Low disk space on ${target} (${free_gb} GB available)! Recommend at least 10 GB."
        fi
    fi
}

# Check for stale network mount and attempt auto-remount recovery
check_and_fix_stale_mount() {
    local target="$1"

    # Test file write/stat access in target directory with sudo
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
log "INFO" "Starting Weekly SD Card Live Image Backup Procedure..."

# Ensure target mount directory exists and is healthy
if [ ! -d "$TARGET_DIR" ]; then
    log "ERROR" "Backup target directory ($TARGET_DIR) is not mounted or does not exist!"
    exit 1
fi

if ! check_and_fix_stale_mount "$TARGET_DIR"; then
    exit 1
fi

check_dependencies
check_disk_space "$TARGET_DIR"

# Function to test file integrity of master image (partition table + ext4 filesystem health)
check_image_integrity() {
    local img="$1"
    if [ ! -f "$img" ]; then
        return 1
    fi

    # Check minimum file size (must be at least 10MB)
    local size_bytes=$(stat -c%s "$img" 2>/dev/null || echo "0")
    if [ "$size_bytes" -lt 10485760 ]; then
        log "WARN" "Image file $img is too small (${size_bytes} bytes). Marked as corrupt!"
        return 1
    fi

    # Verify partition table / header using parted or fdisk
    if command -v parted >/dev/null 2>&1; then
        if ! parted -s "$img" print >/dev/null 2>&1; then
            log "WARN" "Partition header check failed for $img via parted!"
            return 1
        fi
    elif command -v fdisk >/dev/null 2>&1; then
        if ! fdisk -l "$img" >/dev/null 2>&1; then
            log "WARN" "Partition header check failed for $img via fdisk!"
            return 1
        fi
    fi

    # Verify inner ext4 filesystem integrity (catches bad superblock / corrupted root partition)
    if command -v losetup >/dev/null 2>&1; then
        local loop_dev
        loop_dev=$(losetup -fP --show "$img" 2>/dev/null)
        if [ -n "$loop_dev" ]; then
            local p2="${loop_dev}p2"
            if [ ! -b "$p2" ]; then
                p2="${loop_dev}2"
            fi

            if [ -b "$p2" ]; then
                if command -v e2fsck >/dev/null 2>&1; then
                    if ! e2fsck -n "$p2" >/dev/null 2>&1; then
                        log "WARN" "Ext4 superblock/filesystem corruption detected on root partition ($p2)!"
                        losetup -d "$loop_dev" 2>/dev/null
                        return 1
                    fi
                fi
            fi
            losetup -d "$loop_dev" 2>/dev/null
        fi
    fi

    return 0
}

# Pre-Check Target Master Image File for Corruption
if [ -f "$MASTER_IMG" ]; then
    log "INFO" "Checking health and integrity of master backup image: $MASTER_IMG..."
    if ! check_image_integrity "$MASTER_IMG"; then
        log "WARN" "CORRUPTION DETECTED! Master backup image ($MASTER_IMG) is corrupt, truncated, or invalid."
        log "WARN" "Removing corrupt master image to prevent backup failure..."
        rm -f "$MASTER_IMG"
        if [ $? -eq 0 ]; then
            log "INFO" "Successfully removed corrupt master image. A fresh full SD card image will be created."
        else
            log "ERROR" "Failed to remove corrupt master image ($MASTER_IMG). Aborting."
            exit 1
        fi
    else
        log "INFO" "Master backup image passed integrity pre-check."
    fi
fi

# Execute Image Backup Routine
if [ ! -f "$MASTER_IMG" ]; then
    log "INFO" "No existing valid master image found. Creating a NEW full SD card image..."
    if [ -x "$BACKUP_UTIL" ]; then
        log "INFO" "Invoking $BACKUP_UTIL for initial image creation..."
        printf "${MASTER_IMG}\n\n\ny\n" | "$BACKUP_UTIL" 2>&1 | tee -a "$LOG_FILE"
    else
        log "WARN" "$BACKUP_UTIL utility not found. Creating raw live system image fallback..."
        dd if=/dev/mmcblk0 of="$MASTER_IMG" bs=4M status=progress 2>&1 | tee -a "$LOG_FILE"
    fi
else
    log "INFO" "Performing incremental live backup update to master image..."
    if [ -x "$BACKUP_UTIL" ]; then
        log "INFO" "Invoking $BACKUP_UTIL for incremental update..."
        printf "\n\n\ny\n" | "$BACKUP_UTIL" "$MASTER_IMG" 2>&1 | tee -a "$LOG_FILE"
    else
        log "INFO" "Updating backup image via rsync..."
        rsync -aHAX --delete / "$MASTER_IMG" 2>&1 | tee -a "$LOG_FILE"
    fi
fi

RC=$?

# Verify post-execution status
if [ $RC -ne 0 ]; then
    log "ERROR" "Weekly SD Card Backup FAILED with exit code $RC."
    log "WARN" "Validating image integrity after failure..."
    if ! check_image_integrity "$MASTER_IMG"; then
        log "WARN" "Removing incomplete/corrupt image ($MASTER_IMG) so subsequent backup runs can start fresh."
        rm -f "$MASTER_IMG"
    fi
    exit $RC
fi

# Post-Backup Integrity Audit
log "INFO" "Validating completed backup image integrity..."
if check_image_integrity "$MASTER_IMG"; then
    log "INFO" "✓ Integrity Check Passed: SD Card Backup completed successfully."
    SNAPSHOT_NAME="${TARGET_DIR}/genmon_sdcard_$(date '+%Y-%m-%d_%H%M%S').img"
    cp "$MASTER_IMG" "$SNAPSHOT_NAME" 2>/dev/null && log "INFO" "Snapshot created: $SNAPSHOT_NAME"
    ls -t "${TARGET_DIR}"/genmon_sdcard_*.img 2>/dev/null | tail -n +5 | xargs -r rm -f
else
    log "ERROR" "Backup completed but output image failed post-execution integrity check!"
    rm -f "$MASTER_IMG"
    exit 1
fi

log "INFO" "=================================================="
exit 0
