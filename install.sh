#!/bin/bash
# RV Media Player - Raspberry Pi Installer
# Installs, configures, and starts the app in a single run.
# Run with: sudo ./install.sh

set -e

# ─── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log()     { echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $1"; }
success() { echo -e "${GREEN}[✓]${NC} $1"; }
warning() { echo -e "${YELLOW}[!]${NC} $1"; }
error()   { echo -e "${RED}[✗] $1${NC}"; exit 1; }
section() { echo -e "\n${BOLD}${CYAN}── $1 ──${NC}"; }

# ─── Root check ───────────────────────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    error "Run as root: sudo ./install.sh"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ─── Cleanup on failure ───────────────────────────────────────────────────────
cleanup() {
    echo -e "${RED}[✗] Installation failed - rolling back...${NC}"
    systemctl disable rv-media-player.service 2>/dev/null || true
    systemctl stop rv-media-player.service 2>/dev/null || true
}
trap cleanup ERR

# ─── Paths ────────────────────────────────────────────────────────────────────
APP_DIR="/opt/rv-media-player"
MEDIA_DIR="/media/rv"
VENV_DIR="$APP_DIR/venv"
CONFIG_DIR="$APP_DIR/config"
LOGS_DIR="$APP_DIR/logs"
SERVICE_FILE="/etc/systemd/system/rv-media-player.service"

# Resolve the real user early - needed for the service file and desktop setup
REAL_USER="${SUDO_USER:-pi}"
REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)

# Detect Pi config.txt location (Bookworm uses /boot/firmware, older uses /boot)
if [ -f /boot/firmware/config.txt ]; then
    PI_CONFIG="/boot/firmware/config.txt"
elif [ -f /boot/config.txt ]; then
    PI_CONFIG="/boot/config.txt"
else
    PI_CONFIG=""
fi

# ─── Banner ───────────────────────────────────────────────────────────────────
echo -e "${BOLD}"
echo "  ╔══════════════════════════════════════╗"
echo "  ║       RV Media Player Installer      ║"
echo "  ║        Raspberry Pi / Raspbian        ║"
echo "  ╚══════════════════════════════════════╝"
echo -e "${NC}"
echo -e "  Install directory : ${CYAN}$APP_DIR${NC}"
echo -e "  Media directory   : ${CYAN}$MEDIA_DIR${NC}"
echo ""

# ─── Gather all config upfront ────────────────────────────────────────────────
section "Configuration"
echo "Answer the prompts below, then the install runs unattended."
echo ""

# Jellyfin
read -rp "  Jellyfin server URL   (e.g. http://192.168.1.100:8096, or blank to skip): " JELLYFIN_URL
read -rp "  Jellyfin username     (or blank): " JELLYFIN_USER
read -rp "  Jellyfin API key      (or blank): " JELLYFIN_API_KEY

echo ""
echo "  To find your API key: Jellyfin → Dashboard → API Keys → New key"
echo ""

# Media storage location - can be any path, including a USB mount (e.g. /mnt/stor, /mnt/media).
# Movies, TV shows and downloads will be stored as subdirectories of this path.
echo ""
echo "  Where should media be stored? (can be a USB mount, e.g. /mnt/stor)"
read -rp "  Media directory [${MEDIA_DIR}]: " INPUT_MEDIA
MEDIA_DIR="${INPUT_MEDIA:-$MEDIA_DIR}"
echo "  → Media will be stored in: $MEDIA_DIR"

read -rp "  Additional scan paths (comma-separated, or blank for none): " EXTRA_PATHS

# Pi optimizations
echo ""
read -rp "  Apply Raspberry Pi performance optimisations? [Y/n]: " INPUT_OPT
ENABLE_OPT="${INPUT_OPT:-Y}"

echo ""
log "Starting installation - no more input needed."
sleep 1

# ─── Step 1: System packages ──────────────────────────────────────────────────
section "System packages"

log "Updating package lists..."
apt-get update -qq

log "Installing system dependencies..."
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    python3-setuptools \
    python3-wheel \
    git \
    curl \
    wget \
    sqlite3 \
    openssl \
    libffi-dev \
    libssl-dev \
    || error "Failed to install system packages"

log "Installing media packages..."
apt-get install -y \
    vlc \
    ffmpeg \
    mediainfo \
    libavcodec-extra \
    || error "Failed to install media packages"

log "Installing optional GStreamer plugins..."
apt-get install -y \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-libav \
    2>/dev/null || warning "Some GStreamer plugins unavailable - skipping"

log "Installing utilities..."
apt-get install -y \
    htop \
    nano \
    screen \
    usbutils \
    || true   # non-fatal

success "System packages installed"

# ─── Step 2: App user ─────────────────────────────────────────────────────────
section "App user"

if ! id "media" &>/dev/null; then
    log "Creating 'media' system user..."
    if ! getent group media >/dev/null; then
        groupadd --system media
    fi
    useradd --system --gid media --shell /bin/bash --home "$APP_DIR" media
fi
usermod -aG audio,video,dialout,plugdev media 2>/dev/null || true
success "User 'media' ready"

# ─── Step 3: Directories ──────────────────────────────────────────────────────
section "Directories"

mkdir -p "$APP_DIR" "$CONFIG_DIR" "$LOGS_DIR" "$APP_DIR/data" "$APP_DIR/backups"

# If MEDIA_DIR is on a mount point (e.g. /mnt/stor) the parent is likely owned
# by root; create the subdirs anyway - they'll be accessible once the drive is
# mounted.  Use -p so we don't fail if the mount isn't present yet at install time.
mkdir -p "$MEDIA_DIR/movies" "$MEDIA_DIR/tv-shows" "$MEDIA_DIR/downloads"

success "Directories created under $APP_DIR and $MEDIA_DIR"

# ─── Step 4: Copy application files ──────────────────────────────────────────
section "Application files"

log "Copying app files to $APP_DIR..."
cp -r "$SCRIPT_DIR/app"       "$APP_DIR/"
cp -r "$SCRIPT_DIR/static"    "$APP_DIR/"
cp -r "$SCRIPT_DIR/templates" "$APP_DIR/"
cp -r "$SCRIPT_DIR/config"    "$APP_DIR/"
[ -d "$SCRIPT_DIR/systemd" ]  && cp -r "$SCRIPT_DIR/systemd" "$APP_DIR/"
[ -f "$SCRIPT_DIR/requirements.txt" ] && cp "$SCRIPT_DIR/requirements.txt" "$APP_DIR/"

# Set ownership
chown -R media:media "$APP_DIR"
chmod -R 755 "$APP_DIR"
chmod 700 "$CONFIG_DIR"
# Grant media user ownership of the media directory.
# This works for regular dirs and for already-mounted USB drives.
# If the drive isn't mounted yet the dirs still get created and will be
# accessible once the USB is plugged in (ownership set on the dirs themselves).
chown -R media:media "$MEDIA_DIR" 2>/dev/null || \
    warning "Could not chown $MEDIA_DIR - if it is a mount point, re-run: sudo chown -R media:media $MEDIA_DIR"

success "Files copied"

# ─── Step 5: Python virtualenv + deps ────────────────────────────────────────
section "Python environment"

log "Creating virtual environment..."
[ -d "$VENV_DIR" ] && rm -rf "$VENV_DIR"
sudo -u media -H python3 -m venv "$VENV_DIR" || error "Failed to create venv"

log "Upgrading pip..."
sudo -u media -H bash -c "
    source '$VENV_DIR/bin/activate'
    pip install --quiet --no-cache-dir --upgrade pip
" || error "Failed to upgrade pip"

log "Installing Python dependencies (this takes a few minutes)..."
sudo -u media -H bash -c "
    source '$VENV_DIR/bin/activate'
    pip install --quiet --no-cache-dir -r '$APP_DIR/requirements.txt'
" || error "Failed to install Python dependencies"

success "Python environment ready"

# ─── Step 6: Write configuration ─────────────────────────────────────────────
section "Configuration"

log "Writing config file..."

# Build local_media_paths JSON array
MEDIA_PATHS="\"$MEDIA_DIR/movies\",\n    \"$MEDIA_DIR/tv-shows\",\n    \"$MEDIA_DIR/downloads\""
if [ -n "$EXTRA_PATHS" ]; then
    while IFS=',' read -ra PATHS; do
        for p in "${PATHS[@]}"; do
            p="$(echo "$p" | xargs)"  # trim whitespace
            [ -n "$p" ] && MEDIA_PATHS="$MEDIA_PATHS,\n    \"$p\""
        done
    done <<< "$EXTRA_PATHS"
fi

cat > "$CONFIG_DIR/app_config.json" << CONF
{
  "jellyfin_server_url": "${JELLYFIN_URL}",
  "jellyfin_username": "${JELLYFIN_USER}",
  "jellyfin_api_key": "${JELLYFIN_API_KEY}",
  "local_media_paths": [
    $(echo -e "$MEDIA_PATHS")
  ],
  "download_directory": "${MEDIA_DIR}/downloads",
  "vlc_path": "/usr/bin/vlc",
  "auto_launch": true,
  "validation_cache_ttl": 300,
  "max_validation_workers": 10
}
CONF

chmod 600 "$CONFIG_DIR/app_config.json"
chown media:media "$CONFIG_DIR/app_config.json"
chown -R media:media "$CONFIG_DIR"

# Encrypt sensitive fields via the app's own config manager (if supported)
sudo -u media -H bash -c "
    source '$VENV_DIR/bin/activate'
    python3 - << 'PY' 2>/dev/null || true
from config.configuration import Configuration
cfg = Configuration.load_from_file('$CONFIG_DIR/app_config.json')
cfg.save_to_file('$CONFIG_DIR/app_config.json')
print('Config encrypted and saved')
PY
"

success "Configuration written"

# ─── Step 7: Create run script ────────────────────────────────────────────────
cat > "$APP_DIR/run.sh" << 'RUN'
#!/bin/bash
APP_DIR="/opt/rv-media-player"
cd "$APP_DIR"
source "$APP_DIR/venv/bin/activate"
export PYTHONPATH="$APP_DIR"
export FLASK_APP=app/app.py
export FLASK_ENV=production
exec python -m app.app
RUN
chmod +x "$APP_DIR/run.sh"
chown media:media "$APP_DIR/run.sh"

# ─── Step 8: Systemd service ──────────────────────────────────────────────────
section "Systemd service"

# If MEDIA_DIR is under /mnt or /media it could be a removable drive.
# Add RequiresMountsFor so systemd waits for the drive before starting.
MOUNT_DEP=""
case "$MEDIA_DIR" in
    /mnt/*|/media/*)
        MOUNT_DEP="RequiresMountsFor=$MEDIA_DIR" ;;
esac

cat > "$SERVICE_FILE" << SERVICE
[Unit]
Description=RV Media Player
After=network-online.target
Wants=network-online.target
$MOUNT_DEP

[Service]
Type=simple
User=media
Group=media
SupplementaryGroups=audio video dialout plugdev
WorkingDirectory=$APP_DIR
Environment=PYTHONPATH=$APP_DIR
Environment=FLASK_ENV=production
# VLC needs a display to open its GUI window on the Pi desktop
Environment=DISPLAY=:0
Environment=XAUTHORITY=$REAL_HOME/.Xauthority
ExecStartPre=/bin/mkdir -p $APP_DIR/logs $APP_DIR/data
ExecStartPre=/bin/chown media:media $APP_DIR/logs $APP_DIR/data
ExecStart=$VENV_DIR/bin/python -m app.app
ExecReload=/bin/kill -HUP \$MAINPID
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=rv-media-player

NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=$APP_DIR $MEDIA_DIR /tmp

LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
SERVICE

chmod 644 "$SERVICE_FILE"
systemctl daemon-reload
systemctl enable rv-media-player.service
success "Service registered and enabled"

# ─── Step 9: Raspberry Pi optimisations (optional) ───────────────────────────
if [[ "$ENABLE_OPT" =~ ^[Yy]$ ]]; then
    section "Raspberry Pi optimisations"

    # CPU governor → performance
    log "Setting CPU governor to performance..."
    for gov in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
        [ -f "$gov" ] && echo "performance" > "$gov" 2>/dev/null || true
    done

    # GPU memory split (headless Pi doesn't need much; 128 is a safe default)
    if [ -n "$PI_CONFIG" ]; then
        log "Configuring GPU memory split in $PI_CONFIG..."
        grep -q "^gpu_mem=" "$PI_CONFIG" \
            && sed -i 's/^gpu_mem=.*/gpu_mem=128/' "$PI_CONFIG" \
            || echo "gpu_mem=128" >> "$PI_CONFIG"
    fi

    # VM / network tuning
    log "Applying kernel tuning..."
    cat > /etc/sysctl.d/99-rv-media-player.conf << 'SYSCTL'
vm.swappiness=10
vm.dirty_ratio=20
vm.dirty_background_ratio=10
net.core.rmem_max=16777216
net.core.wmem_max=16777216
net.ipv4.tcp_rmem=4096 87380 16777216
net.ipv4.tcp_wmem=4096 65536 16777216
SYSCTL
    sysctl -p /etc/sysctl.d/99-rv-media-player.conf >/dev/null 2>&1 || true

    # Process priority limits
    cat > /etc/security/limits.d/rv-media-player.conf << 'LIMITS'
media soft nice -10
media hard nice -10
media soft rtprio 10
media hard rtprio 10
LIMITS

    # Disable services not needed on a headless media server
    for svc in bluetooth ModemManager avahi-daemon cups-browsed; do
        systemctl disable "$svc.service" 2>/dev/null && \
            systemctl stop "$svc.service" 2>/dev/null || true
    done

    # tmpfs for /tmp if >= 1 GB RAM
    TOTAL_RAM=$(free -m | awk 'NR==2{print $2}')
    if [ "$TOTAL_RAM" -gt 1024 ] && ! grep -q "^tmpfs /tmp" /etc/fstab; then
        echo "tmpfs /tmp tmpfs defaults,noatime,mode=1777,size=256M 0 0" >> /etc/fstab
    fi

    success "Raspberry Pi optimisations applied"
fi

# ─── Step 10: Desktop launcher ───────────────────────────────────────────────
section "Desktop launcher"

# Launch script - ensures service is running then opens browser to http://
cat > "$APP_DIR/launch.sh" << 'LAUNCH'
#!/bin/bash
# RV Media Player launcher
# Starts the service if not running, then opens the web interface.

if ! systemctl is-active --quiet rv-media-player.service; then
    sudo systemctl start rv-media-player.service
    # Wait for Flask to be ready (up to 15 s)
    for i in $(seq 1 15); do
        sleep 1
        curl -s http://localhost:5000 >/dev/null 2>&1 && break
    done
fi

# Open browser - force http:// so Firefox/Chromium don't upgrade to https
URL="http://localhost:5000"
chromium-browser --new-window "$URL" 2>/dev/null || \
    chromium         --new-window "$URL" 2>/dev/null || \
    firefox          "$URL"             2>/dev/null || \
    xdg-open         "$URL"
LAUNCH

chmod +x "$APP_DIR/launch.sh"

# Grant the 'media' service user access to the Pi's X display so VLC can open windows.
# Uses an autostart entry so the grant is re-applied each time the desktop session starts.
AUTOSTART_DIR="$REAL_HOME/.config/autostart"
mkdir -p "$AUTOSTART_DIR"
cat > "$AUTOSTART_DIR/rv-media-xhost.desktop" << XHOST
[Desktop Entry]
Type=Application
Name=RV Media Player Display Access
Comment=Allow media service user to open VLC on the local display
Exec=xhost +local:media
Hidden=false
NoDisplay=true
X-GNOME-Autostart-enabled=true
XHOST
chown -R "$REAL_USER:$REAL_USER" "$AUTOSTART_DIR"
# Also apply immediately for this session (best-effort - may fail if no display)
DISPLAY=:0 xhost +local:media 2>/dev/null || true

DESKTOP_DIR="$REAL_HOME/Desktop"
mkdir -p "$DESKTOP_DIR"

# Detect icon - use logo if it exists, fall back to a standard system icon
ICON="$APP_DIR/static/images/logo.png"
[ -f "$ICON" ] || ICON="video-x-generic"

cat > "$DESKTOP_DIR/rv-media-player.desktop" << DESKTOP
[Desktop Entry]
Version=1.0
Type=Application
Name=RV Media Player
Comment=Offline media library
Exec=$APP_DIR/launch.sh
Icon=$ICON
Terminal=false
Categories=AudioVideo;Video;Player;
DESKTOP

chmod +x "$DESKTOP_DIR/rv-media-player.desktop"
chown "$REAL_USER:$REAL_USER" "$DESKTOP_DIR/rv-media-player.desktop"

# Sudoers rule - lets the real user start/stop the service from the launcher
# without a password prompt interrupting the desktop click
SUDOERS_FILE="/etc/sudoers.d/rv-media-player"
cat > "$SUDOERS_FILE" << SUDOERS
# Allow $REAL_USER to control the rv-media-player service without a password
$REAL_USER ALL=(ALL) NOPASSWD: /bin/systemctl start rv-media-player.service, /bin/systemctl stop rv-media-player.service, /bin/systemctl restart rv-media-player.service
SUDOERS
chmod 440 "$SUDOERS_FILE"

success "Desktop shortcut created at $DESKTOP_DIR/rv-media-player.desktop"

# ─── Step 11: Start service ───────────────────────────────────────────────────
section "Starting service"

log "Starting rv-media-player..."
systemctl start rv-media-player.service

sleep 3

if systemctl is-active --quiet rv-media-player.service; then
    success "Service is running"
else
    warning "Service did not start - check: sudo journalctl -u rv-media-player -n 50"
fi

# ─── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}  ✓ Installation complete!${NC}"
echo ""
echo -e "  Web interface  →  ${CYAN}http://localhost:5000${NC}"
echo -e "  App directory  →  ${CYAN}$APP_DIR${NC}"
echo -e "  Media files    →  ${CYAN}$MEDIA_DIR${NC}"
echo ""
echo -e "  Double-click ${CYAN}RV Media Player${NC} on the desktop to launch."
echo ""
echo -e "  ${BOLD}Useful commands:${NC}"
echo -e "    sudo systemctl status rv-media-player"
echo -e "    sudo journalctl -u rv-media-player -f"
echo -e "    sudo systemctl restart rv-media-player"
echo ""
