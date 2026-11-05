#!/bin/bash
# -------------------------------------------------------------------------------
# Weekly Live SD Card Image Backup Script with Corruption Protection & Auto-Healing
# -------------------------------------------------------------------------------

umask 022

LOG_FILE="/home/genmonpi/sdcard_backup.log"
TARGET_DIR="/mnt/pibackup"
MASTER_IMG="${TARGET_DIR}/genmon_sdcard_master.img"
BACKUP_UTIL="/usr/local/bin/image-backup"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FILTER_UTIL="${SCRIPT_DIR}/backup_progress_filter.py"

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
    # Unmount temporary image backup mount points if left behind (boot first, then root)
    if mountpoint -q /tmp/img-backup-mnt/boot 2>/dev/null; then
        sudo umount -l -f /tmp/img-backup-mnt/boot 2>/dev/null
    fi
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
    for cmd in kpartx rsync parted bc e2fsck; do
        if ! command -v "$cmd" >/dev/null 2>&1 && [ ! -x "/sbin/$cmd" ] && [ ! -x "/usr/sbin/$cmd" ]; then
            missing+=("$cmd")
        fi
    done
    if ! command -v fsck.fat >/dev/null 2>&1 && ! command -v dosfsck >/dev/null 2>&1 && [ ! -x /sbin/fsck.fat ] && [ ! -x /sbin/dosfsck ] && [ ! -x /usr/sbin/fsck.fat ] && [ ! -x /usr/sbin/dosfsck ]; then
        missing+=("dosfstools")
    fi

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

# Helper to detect if another backup script is running (excluding self and parent)
is_other_running() {
    local pattern="$1"
    for pid in $(pgrep -f "$pattern" 2>/dev/null); do
        if [ "$pid" != "$$" ] && [ "$pid" != "$PPID" ]; then
            return 0
        fi
    done
    return 1
}

log "INFO" "=================================================="
log "INFO" "Starting Weekly SD Card Live Image Backup Procedure..."

# Mutual Exclusion: Ensure daily backup is not running concurrently
if is_other_running "(^|[/ ])backup_to_mac\.sh"; then
    log "WARN" "Daily Genmon Backup is currently in progress. Skipping weekly backup to prevent I/O conflict."
    exit 0
fi

# Ensure target mount directory exists and is healthy
if [ ! -d "$TARGET_DIR" ]; then
    log "ERROR" "Backup target directory ($TARGET_DIR) is not mounted or does not exist!"
    exit 1
fi

if ! check_and_fix_stale_mount "$TARGET_DIR"; then
    exit 1
fi

# Ensure image-backup and mkfs do not attempt DISCARD on CIFS/SMB loop devices
configure_mkfs_nodiscard() {
    # 1. Update /etc/mke2fs.conf to disable discard by default on ext4 format
    if [ -w /etc/mke2fs.conf ] && ! grep -q "discard = false" /etc/mke2fs.conf 2>/dev/null; then
        if grep -q "\[defaults\]" /etc/mke2fs.conf 2>/dev/null; then
            sed -i '/\[defaults\]/a \\tdiscard = false' /etc/mke2fs.conf 2>/dev/null && \
                log "INFO" "Configured /etc/mke2fs.conf (discard = false) for network share compatibility."
        fi
    fi

    # 2. Patch image-backup utility to pass -E nodiscard to mkfs.ext4
    if [ -f "$BACKUP_UTIL" ] && [ -w "$BACKUP_UTIL" ]; then
        if grep -q "mkfs\.ext4" "$BACKUP_UTIL" && ! grep -q "nodiscard" "$BACKUP_UTIL"; then
            sed -i 's/mkfs\.ext4/mkfs.ext4 -E nodiscard/g' "$BACKUP_UTIL" 2>/dev/null && \
                log "INFO" "Patched $BACKUP_UTIL with '-E nodiscard' for CIFS/SMB compatibility."
        fi
    fi
}

check_dependencies
check_disk_space "$TARGET_DIR"
configure_mkfs_nodiscard

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

        log "WARN" "Backup operation failed with exit code $rc (Attempt $attempt/$max_attempts)."
        if [ $attempt -lt $max_attempts ]; then
            log "WARN" "Retrying in ${delay} seconds after cleaning up temporary mounts and verifying network mount health..."
            cleanup 2>/dev/null
            sleep $delay
            check_and_fix_stale_mount "$TARGET_DIR"
            delay=$((delay * 2))
        fi
        attempt=$((attempt + 1))
    done

    return $rc
}

# Execute Image Backup Routine
run_backup_step() {
    local filter_cmd=(cat)
    if [ -f "$FILTER_UTIL" ] && command -v python3 >/dev/null 2>&1; then
        filter_cmd=(python3 "$FILTER_UTIL" --log-file "$LOG_FILE" --interval 60 --pct-step 5)
    else
        filter_cmd=(tee -a "$LOG_FILE")
    fi

    if [ ! -f "$MASTER_IMG" ] || ! check_image_integrity "$MASTER_IMG"; then
        log "INFO" "No existing valid master image found (or existing image is invalid). Creating a NEW full SD card image..."
        rm -f "$MASTER_IMG" 2>/dev/null
        if [ -x "$BACKUP_UTIL" ]; then
            log "INFO" "Invoking $BACKUP_UTIL for initial image creation (with 4000 MB incremental headroom)..."
            printf "${MASTER_IMG}\n\n4000\ny\n" | "$BACKUP_UTIL" -o --info=progress2 2>&1 | "${filter_cmd[@]}"
            local step_rc=${PIPESTATUS[1]}
            if [ $step_rc -ne 0 ]; then
                log "WARN" "Initial image creation failed. Cleaning up incomplete master image file..."
                rm -f "$MASTER_IMG" 2>/dev/null
            else
                chmod 755 "$MASTER_IMG" 2>/dev/null || true
            fi
            chmod 755 "$LOG_FILE" 2>/dev/null || true
            return $step_rc
        else
            log "WARN" "$BACKUP_UTIL utility not found. Creating raw live system image fallback..."
            dd if=/dev/mmcblk0 of="$MASTER_IMG" bs=4M status=progress 2>&1 | "${filter_cmd[@]}"
            local step_rc=${PIPESTATUS[0]}
            if [ $step_rc -ne 0 ]; then
                log "WARN" "Raw image creation failed. Cleaning up incomplete master image file..."
                rm -f "$MASTER_IMG" 2>/dev/null
            else
                chmod 755 "$MASTER_IMG" 2>/dev/null || true
            fi
            chmod 755 "$LOG_FILE" 2>/dev/null || true
            return $step_rc
        fi
    else
        log "INFO" "Performing incremental live backup update to master image..."
        if [ -x "$BACKUP_UTIL" ]; then
            log "INFO" "Invoking $BACKUP_UTIL for incremental update..."
            printf "\n\n\ny\n" | "$BACKUP_UTIL" -o --info=progress2 "$MASTER_IMG" 2>&1 | "${filter_cmd[@]}"
            local step_rc=${PIPESTATUS[1]}
            chmod 755 "$MASTER_IMG" 2>/dev/null || true
            chmod 755 "$LOG_FILE" 2>/dev/null || true
            return $step_rc
        else
            log "INFO" "Updating backup image via rsync..."
            rsync -aHAX --info=progress2 --timeout=60 --contimeout=30 --delete / "$MASTER_IMG" 2>&1 | "${filter_cmd[@]}"
            local step_rc=${PIPESTATUS[0]}
            chmod 755 "$MASTER_IMG" 2>/dev/null || true
            chmod 755 "$LOG_FILE" 2>/dev/null || true
            return $step_rc
        fi
    fi
}

retry_cmd run_backup_step
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
    chmod 755 "$MASTER_IMG" 2>/dev/null || true
    chmod 755 "$LOG_FILE" 2>/dev/null || true
    log "INFO" "✓ Integrity Check Passed: SD Card Backup completed successfully ($MASTER_IMG)."
else
    log "ERROR" "Backup completed but output image failed post-execution integrity check!"
    rm -f "$MASTER_IMG"
    exit 1
fi

log "INFO" "=================================================="
exit 0
