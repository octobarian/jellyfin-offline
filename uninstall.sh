#!/bin/bash
# RV Media Player Uninstall Script for Ubuntu
# This script removes the RV Media Player application from an Orange Pi running Ubuntu

# Exit on error
set -e

# ANSI color codes for better readability
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Log function
log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    error "Please run this script as root (use sudo)"
fi

# Configuration
APP_DIR="/opt/rv-media-player"
MEDIA_DIR="/media"
SYSTEMD_SERVICE_FILE="/etc/systemd/system/rv-media-player.service"
SYSTEMD_OPTIMIZE_SERVICE_FILE="/etc/systemd/system/rv-media-player-optimize.service"
SYSTEMD_WEB_SERVICE_FILE="/etc/systemd/system/rv-media-player-web.service"

log "Starting RV Media Player uninstallation..."

# Step 1: Stop and disable services
log "Stopping and disabling RV Media Player services..."
systemctl stop rv-media-player.service 2>/dev/null || true
systemctl stop rv-media-player-optimize.service 2>/dev/null || true
systemctl stop rv-media-player-web.service 2>/dev/null || true

systemctl disable rv-media-player.service 2>/dev/null || true
systemctl disable rv-media-player-optimize.service 2>/dev/null || true
systemctl disable rv-media-player-web.service 2>/dev/null || true

# Step 2: Remove systemd service files
log "Removing systemd service files..."
rm -f "$SYSTEMD_SERVICE_FILE"
rm -f "$SYSTEMD_OPTIMIZE_SERVICE_FILE"
rm -f "$SYSTEMD_WEB_SERVICE_FILE"

systemctl daemon-reload

# Step 3: Remove application directory
if [ -d "$APP_DIR" ]; then
    log "Removing application directory: $APP_DIR"
    
    # Ask user if they want to backup configuration
    read -p "Do you want to backup configuration files before removal? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        BACKUP_DIR="/tmp/rv-media-player-backup-$(date +%Y%m%d_%H%M%S)"
        log "Creating backup at: $BACKUP_DIR"
        mkdir -p "$BACKUP_DIR"
        
        # Backup configuration files
        if [ -d "$APP_DIR/config" ]; then
            cp -r "$APP_DIR/config" "$BACKUP_DIR/"
            success "Configuration backed up to: $BACKUP_DIR/config"
        fi
        
        # Backup logs
        if [ -d "$APP_DIR/logs" ]; then
            cp -r "$APP_DIR/logs" "$BACKUP_DIR/"
            success "Logs backed up to: $BACKUP_DIR/logs"
        fi
    fi
    
    # Remove the application directory
    rm -rf "$APP_DIR"
    success "Application directory removed"
else
    warning "Application directory not found: $APP_DIR"
fi

# Step 4: Ask about media directory
read -p "Do you want to remove media directories at $MEDIA_DIR? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    log "Removing media directories..."
    rm -rf "$MEDIA_DIR/movies" "$MEDIA_DIR/tv-shows" "$MEDIA_DIR/downloads" "$MEDIA_DIR/local"
    success "Media directories removed"
else
    log "Media directories preserved"
fi

# Step 5: Remove media user
if id "media" &>/dev/null; then
    read -p "Do you want to remove the 'media' user account? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        log "Removing media user..."
        userdel media 2>/dev/null || warning "Could not remove media user"
        success "Media user removed"
    else
        log "Media user preserved"
    fi
else
    log "Media user not found"
fi

# Step 6: Remove system configuration files
log "Removing system configuration files..."

# Remove sysctl optimizations
rm -f /etc/sysctl.d/99-rv-media-player.conf

# Remove security limits
rm -f /etc/security/limits.d/rv-media-player.conf

# Step 7: Ask about package removal
read -p "Do you want to remove packages that were installed for RV Media Player? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    log "Removing packages..."
    warning "This will remove packages that might be used by other applications!"
    read -p "Are you sure you want to continue? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # Remove media packages
        apt remove -y \
            vlc \
            ffmpeg \
            mediainfo \
            gstreamer1.0-tools \
            gstreamer1.0-plugins-base \
            gstreamer1.0-plugins-good \
            gstreamer1.0-plugins-bad \
            gstreamer1.0-plugins-ugly \
            gstreamer1.0-libav \
            libavcodec-extra \
            2>/dev/null || warning "Some packages could not be removed"
        
        # Remove hardware acceleration packages
        apt remove -y \
            mesa-utils \
            va-driver-all \
            vdpau-driver-all \
            libva2 \
            libvdpau1 \
            2>/dev/null || warning "Some hardware acceleration packages could not be removed"
        
        # Clean up
        apt autoremove -y
        apt autoclean
        
        success "Packages removed and system cleaned"
    else
        log "Package removal skipped"
    fi
else
    log "Package removal skipped"
fi

# Step 8: Restore system settings
log "Restoring system settings..."

# Restore CPU governor to default
for cpu in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
    if [ -f "$cpu" ]; then
        echo "ondemand" > "$cpu" 2>/dev/null || true
    fi
done

# Restore swappiness to default
echo 60 > /proc/sys/vm/swappiness 2>/dev/null || true

# Step 9: Re-enable services that were disabled
log "Re-enabling system services..."
services_to_enable=("unattended-upgrades")
for service in "${services_to_enable[@]}"; do
    systemctl enable "$service.service" 2>/dev/null || true
done

# Step 10: Clean up temporary files
log "Cleaning up temporary files..."
rm -rf /tmp/rv-media-player-*

success "RV Media Player uninstallation completed successfully!"

echo
log "Uninstallation summary:"
log "- RV Media Player application removed"
log "- Systemd services removed and disabled"
log "- System optimizations reverted"
if [ -d "$BACKUP_DIR" ]; then
    log "- Configuration backup available at: $BACKUP_DIR"
fi

echo
log "You may want to:"
log "1. Reboot the system to ensure all changes take effect"
log "2. Check for any remaining configuration files in /etc/"
log "3. Review /etc/fstab for any tmpfs entries that were added"

echo
warning "Note: Some system packages may have been left installed to avoid breaking other applications."
warning "If you're sure they're not needed, you can remove them manually with 'apt remove <package>'"
