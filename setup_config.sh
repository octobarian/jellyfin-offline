#!/bin/bash

# RV Media Player Configuration Setup Script
# Run this after installation to configure the application

set -e

# Check if running with sudo
if [[ $EUID -ne 0 ]]; then
    echo -e "\033[0;31m[ERROR]\033[0m This script must be run with sudo"
    echo "Usage: sudo ./setup_config.sh"
    exit 1
fi

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

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
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
# Note: User ID is automatically retrieved during authentication

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

# Ensure directories exist with proper permissions before creating config
log "Ensuring directories exist with proper permissions..."
sudo mkdir -p /opt/rv-media-player/data /opt/rv-media-player/logs
sudo mkdir -p /media/movies /media/tv-shows /media/downloads /media/local
sudo chown -R media:media /opt/rv-media-player /media
sudo chmod -R 755 /opt/rv-media-player
sudo chmod 755 /media /media/movies /media/tv-shows /media/downloads /media/local

# Create simplified configuration file that matches the Configuration class
sudo tee "$CONFIG_FILE" > /dev/null << EOF
{
  "jellyfin_server_url": "$JELLYFIN_URL",
  "jellyfin_username": "$JELLYFIN_USER",
  "jellyfin_api_key": "$JELLYFIN_API_KEY",
  "local_media_paths": [
    "/media/movies",
    "/media/tv-shows",
    "/media/downloads"$(if [[ -n "$ADDITIONAL_PATHS" ]]; then echo ","; echo "$ADDITIONAL_PATHS" | sed 's/,/",\n    "/g' | sed 's/^/    "/'; fi)
  ],
  "download_directory": "/media/downloads",
  "vlc_path": "/usr/bin/vlc",
  "auto_launch": true,
  "fullscreen_browser": false,
  "validation_cache_ttl": 300,
  "max_validation_workers": 10
}
EOF

# Set proper ownership and permissions
sudo chmod 600 "$CONFIG_FILE"
sudo chown media:media "$CONFIG_FILE"

# Verify permissions are correct
log "Verifying directory permissions..."
if [[ ! -w "/opt/rv-media-player/data" ]] || [[ ! -d "/opt/rv-media-player/data" ]]; then
    log "Fixing data directory permissions..."
    sudo mkdir -p /opt/rv-media-player/data
    sudo chown -R media:media /opt/rv-media-player/data
    sudo chmod 755 /opt/rv-media-player/data
fi

if [[ ! -w "/opt/rv-media-player/logs" ]] || [[ ! -d "/opt/rv-media-player/logs" ]]; then
    log "Fixing logs directory permissions..."
    sudo mkdir -p /opt/rv-media-player/logs
    sudo chown -R media:media /opt/rv-media-player/logs
    sudo chmod 755 /opt/rv-media-player/logs
fi

# Test database creation
log "Testing database creation..."
if command -v sqlite3 >/dev/null 2>&1; then
    if sudo -u media sqlite3 /opt/rv-media-player/data/test.db "CREATE TABLE test (id INTEGER); DROP TABLE test;" 2>/dev/null; then
        sudo rm -f /opt/rv-media-player/data/test.db
        success "Database creation test passed"
    else
        warning "Database creation test failed - permissions may need adjustment"
        log "Attempting to fix database directory permissions..."
        sudo chown -R media:media /opt/rv-media-player/data
        sudo chmod -R 755 /opt/rv-media-player/data
    fi
else
    warning "sqlite3 not found - skipping database test"
fi

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
