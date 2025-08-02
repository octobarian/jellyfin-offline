#!/bin/bash

# RV Media Player Configuration Setup Script
# Run this after installation to configure the application

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
APP_DIR="/opt/rv-media-player"
CONFIG_FILE="$APP_DIR/config/app_config.json"

log() {
    echo -e "${GREEN}[$(date +'%H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%H:%M:%S')] WARNING: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%H:%M:%S')] ERROR: $1${NC}"
    exit 1
}

info() {
    echo -e "${BLUE}[$(date +'%H:%M:%S')] INFO: $1${NC}"
}

# Check if running as root
if [[ $EUID -eq 0 ]]; then
    error "This script should NOT be run as root. Run as a regular user with sudo access."
fi

# Check if application is installed
if [[ ! -d "$APP_DIR" ]]; then
    error "RV Media Player is not installed. Please run install.sh first."
fi

log "RV Media Player Configuration Setup"
echo "This script will help you configure your RV Media Player installation."
echo

# Get Orange Pi IP address
ORANGE_PI_IP=$(hostname -I | awk '{print $1}')
info "Orange Pi IP Address: $ORANGE_PI_IP"
echo

# Jellyfin Configuration
echo "=== Jellyfin Server Configuration ==="
read -p "Enter Jellyfin server URL (e.g., http://192.168.1.100:8096): " JELLYFIN_URL
read -p "Enter Jellyfin username: " JELLYFIN_USER

echo "To get your Jellyfin API key:"
echo "1. Open Jellyfin web interface: $JELLYFIN_URL"
echo "2. Go to Dashboard > API Keys"
echo "3. Create a new API key for RV Media Player"
echo
read -p "Enter Jellyfin API key: " JELLYFIN_API_KEY

echo "To get your Jellyfin User ID:"
echo "1. In Jellyfin, go to Dashboard > Users"
echo "2. Click on your username"
echo "3. Copy the User ID from the URL (long string after /users/)"
echo
read -p "Enter Jellyfin User ID: " JELLYFIN_USER_ID

# Media Paths Configuration
echo
echo "=== Media Paths Configuration ==="
echo "Current media directories:"
ls -la /media/ 2>/dev/null || echo "No media directories found"
echo

read -p "Enter additional local media paths (comma-separated, or press Enter for defaults): " ADDITIONAL_PATHS

# Web Interface Configuration
echo
echo "=== Web Interface Configuration ==="
read -p "Enter web interface port (default: 5000): " WEB_PORT
WEB_PORT=${WEB_PORT:-5000}

# Generate secret key
SECRET_KEY=$(openssl rand -hex 32)

# Create configuration file
log "Creating configuration file..."

sudo tee "$CONFIG_FILE" > /dev/null << EOF
{
  "jellyfin_server_url": "$JELLYFIN_URL",
  "jellyfin_username": "$JELLYFIN_USER",
  "jellyfin_api_key": "$JELLYFIN_API_KEY",
  "jellyfin_user_id": "$JELLYFIN_USER_ID",
  "local_media_paths": [
    "/media/movies",
    "/media/tv-shows",
    "/media/local"$(if [[ -n "$ADDITIONAL_PATHS" ]]; then echo ","; echo "$ADDITIONAL_PATHS" | sed 's/,/",\n    "/g' | sed 's/^/    "/'; fi)
  ],
  "download_directory": "/media/downloads",
  "vlc_path": "/usr/bin/vlc",
  "auto_launch": true,
  "fullscreen_browser": false,
  "web_interface": {
    "host": "0.0.0.0",
    "port": $WEB_PORT,
    "debug": false,
    "secret_key": "$SECRET_KEY"
  },
  "media_scanning": {
    "auto_scan": true,
    "scan_interval_minutes": 30,
    "validate_files": true,
    "extract_metadata": true,
    "generate_thumbnails": true
  },
  "download_settings": {
    "max_concurrent_downloads": 3,
    "download_quality": "1080p",
    "auto_organize": true,
    "cleanup_after_download": false
  },
  "playback_settings": {
    "default_player": "vlc",
    "hardware_acceleration": true,
    "subtitle_languages": ["en", "eng"],
    "audio_languages": ["en", "eng"]
  },
  "orange_pi_settings": {
    "enable_optimizations": true,
    "cpu_governor": "performance",
    "gpu_memory_split": 128,
    "disable_bluetooth": true,
    "disable_wifi_power_save": true
  },
  "logging": {
    "level": "INFO",
    "file": "/opt/rv-media-player/logs/app.log",
    "max_size_mb": 10,
    "backup_count": 5
  },
  "security": {
    "enable_authentication": false,
    "username": "",
    "password_hash": "",
    "session_timeout_minutes": 60,
    "allowed_ips": []
  },
  "advanced": {
    "cache_size_mb": 256,
    "thumbnail_cache_size_mb": 128,
    "database_path": "/opt/rv-media-player/data/media.db",
    "backup_config": true,
    "backup_interval_hours": 24
  }
}
EOF

# Set proper ownership
sudo chown media:media "$CONFIG_FILE"

log "Configuration file created: $CONFIG_FILE"

# Test Jellyfin connection
echo
log "Testing Jellyfin connection..."
if curl -s -f "$JELLYFIN_URL/System/Info" > /dev/null; then
    log "✓ Jellyfin server is reachable"
else
    warn "✗ Could not reach Jellyfin server. Please check the URL and network connectivity."
fi

# Create media directories if they don't exist
log "Creating media directories..."
sudo mkdir -p /media/{movies,tv-shows,downloads,local}
sudo chown -R media:media /media

# Start/restart the service
echo
read -p "Start/restart the RV Media Player service now? (y/n): " START_SERVICE
if [[ "$START_SERVICE" =~ ^[Yy]$ ]]; then
    log "Starting RV Media Player service..."
    sudo systemctl restart rv-media-player
    sudo systemctl enable rv-media-player
    
    # Wait a moment for service to start
    sleep 3
    
    if sudo systemctl is-active --quiet rv-media-player; then
        log "✓ RV Media Player service is running"
    else
        warn "✗ Service failed to start. Check logs with: sudo journalctl -u rv-media-player"
    fi
fi

# Final instructions
echo
log "Configuration complete!"
echo
info "Next steps:"
info "1. Access the web interface: http://$ORANGE_PI_IP:$WEB_PORT"
info "2. Add your media files to the configured directories"
info "3. The application will automatically scan for new media"
echo
info "Useful commands:"
info "- Check service status: sudo systemctl status rv-media-player"
info "- View logs: sudo journalctl -u rv-media-player -f"
info "- Restart service: sudo systemctl restart rv-media-player"
echo
info "For troubleshooting, see README_ORANGEPI.md"
