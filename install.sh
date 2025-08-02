#!/bin/bash
# RV Media Player Installation Script for Ubuntu
# This script sets up the RV Media Player application on an Orange Pi running Ubuntu

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

# Get the directory where the script is located (source code)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Application will be installed to /opt/rv-media-player
APP_DIR="/opt/rv-media-player"

# Configuration
MEDIA_DIR="/media"  # Use system media directory
LOGS_DIR="$APP_DIR/logs"
CONFIG_DIR="$APP_DIR/config"
VENV_DIR="$APP_DIR/venv"
SYSTEMD_SERVICE_FILE="/etc/systemd/system/rv-media-player.service"
USER=$(logname || echo "$SUDO_USER")
GROUP=$(id -gn "$USER")

log "Starting RV Media Player installation..."
log "Installation directory: $APP_DIR"
log "User: $USER, Group: $GROUP"

# Step 1: Update system and install dependencies
log "Updating system and installing dependencies..."
apt update && apt upgrade -y || error "Failed to update system"

# Core system packages
log "Installing core system packages..."
apt install -y \
    python3 python3-pip python3-venv \
    git curl wget unzip \
    build-essential gcc make cmake \
    software-properties-common \
    apt-transport-https \
    ca-certificates \
    gnupg \
    lsb-release \
    || error "Failed to install core packages"

# Media packages
log "Installing media packages..."
apt install -y \
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
    || error "Failed to install media packages"

# Network and web server packages
log "Installing network packages..."
apt install -y \
    nginx \
    openssh-server \
    rsync \
    samba \
    cifs-utils \
    net-tools \
    iproute2 \
    dnsutils \
    nmap \
    || error "Failed to install network packages"

# System utilities
log "Installing system utilities..."
apt install -y \
    htop \
    nano \
    vim \
    screen \
    tmux \
    lshw \
    usbutils \
    pciutils \
    sqlite3 \
    tree \
    || error "Failed to install system utilities"

# Hardware acceleration packages for Orange Pi
log "Installing hardware acceleration packages..."
apt install -y \
    mesa-utils \
    va-driver-all \
    vdpau-driver-all \
    libva2 \
    libvdpau1 \
    || warn "Some hardware acceleration packages may not be available"

# Python development packages
log "Installing Python development packages..."
apt install -y \
    python3-dev \
    python3-setuptools \
    python3-wheel \
    libffi-dev \
    libssl-dev \
    || error "Failed to install Python development packages"

# Step 2: Create application directory structure
log "Creating application directory structure..."

# Create application directory first
mkdir -p "$APP_DIR"
mkdir -p "$LOGS_DIR" "$CONFIG_DIR" "$APP_DIR/data" "$APP_DIR/backups"

# Create media directories
mkdir -p "$MEDIA_DIR/movies" "$MEDIA_DIR/tv-shows" "$MEDIA_DIR/downloads" "$MEDIA_DIR/local"

# Create media user if it doesn't exist
if ! id "media" &>/dev/null; then
    log "Creating media user..."
    # Check if media group exists, if not create it
    if ! getent group media >/dev/null; then
        groupadd media
        log "Created media group"
    fi
    # Create user with media as primary group
    useradd -r -g media -s /bin/bash -d "$APP_DIR" media
    usermod -a -G audio,video,dialout,plugdev media
    log "Created media user with media group"
else
    log "Media user already exists"
    # Ensure user is in the correct groups
    usermod -a -G media,audio,video,dialout,plugdev media
fi

# Step 3: Copy application files
log "Copying application files..."
# Copy all application files except installation files and git directory
cp -r "$SCRIPT_DIR/app" "$APP_DIR/"
cp -r "$SCRIPT_DIR/static" "$APP_DIR/"
cp -r "$SCRIPT_DIR/templates" "$APP_DIR/"
cp -r "$SCRIPT_DIR/systemd" "$APP_DIR/"
cp -r "$SCRIPT_DIR/config" "$APP_DIR/"
cp "$SCRIPT_DIR/requirements.txt" "$APP_DIR/"
cp "$SCRIPT_DIR/setup_config.sh" "$APP_DIR/"

# Don't copy installation files, git directory, or other development files
# install.sh, .git/, .gitignore, README files stay in source directory

# Set proper ownership and permissions
chmod 755 "$APP_DIR" "$MEDIA_DIR" "$LOGS_DIR" "$CONFIG_DIR"
chown -R media:media "$APP_DIR" "$MEDIA_DIR"

# Step 4: Set up Python virtual environment
log "Setting up Python virtual environment..."
log "Note: Using --no-cache-dir to avoid permission issues with pip cache"

if [ -d "$VENV_DIR" ]; then
    warning "Virtual environment already exists. Recreating..."
    rm -rf "$VENV_DIR"
fi

# Create virtual environment as media user with proper environment
sudo -u media -H bash -c "cd '$APP_DIR' && python3 -m venv '$VENV_DIR'" || error "Failed to create virtual environment"

# Upgrade pip with proper cache handling
sudo -u media -H bash -c "
    cd '$APP_DIR'
    source '$VENV_DIR/bin/activate'
    pip install --no-cache-dir --upgrade pip
" || error "Failed to upgrade pip"

# Install Python dependencies
log "Installing Python dependencies..."
sudo -u media -H bash -c "
    cd '$APP_DIR'
    source '$VENV_DIR/bin/activate'
    pip install --no-cache-dir flask
    pip install --no-cache-dir requests
    pip install --no-cache-dir python-dotenv
    pip install --no-cache-dir gunicorn
    pip install --no-cache-dir psutil
    pip install --no-cache-dir watchdog
    pip install --no-cache-dir schedule
    pip install --no-cache-dir python-vlc
    pip install --no-cache-dir mutagen
    pip install --no-cache-dir pillow
    pip install --no-cache-dir 'qrcode[pil]'
    pip install --no-cache-dir cryptography
    pip install --no-cache-dir pyyaml
    pip install --no-cache-dir jsonschema
    pip install --no-cache-dir click
    pip install --no-cache-dir colorama
    pip install --no-cache-dir tqdm
    pip install --no-cache-dir humanize
    pip install --no-cache-dir pymediainfo
" || error "Failed to install Python dependencies"

# Install requirements.txt if it exists
if [ -f "$APP_DIR/requirements.txt" ]; then
    log "Installing additional requirements from requirements.txt..."
    sudo -u media -H bash -c "
        cd '$APP_DIR'
        source '$VENV_DIR/bin/activate'
        pip install --no-cache-dir -r '$APP_DIR/requirements.txt'
    "
fi

# Step 5: Set up configuration
log "Setting up configuration..."
if [ ! -f "$CONFIG_DIR/app_config.json" ]; then
    log "Creating default configuration..."
    # Ensure config directory exists with secure permissions
    mkdir -p "$CONFIG_DIR"
    chmod 700 "$CONFIG_DIR"
    
    # Create a basic configuration file
    cat > "$CONFIG_DIR/app_config.json" << EOF
{
  "jellyfin_server_url": "",
  "jellyfin_username": "",
  "jellyfin_api_key": "",
  "local_media_paths": [
    "/media/movies",
    "/media/tv-shows",
    "/media/local"
  ],
  "download_directory": "/media/downloads",
  "vlc_path": "/usr/bin/vlc",
  "auto_launch": true,
  "fullscreen_browser": true
}
EOF
    chmod 600 "$CONFIG_DIR/app_config.json"
    chown media:media "$CONFIG_DIR/app_config.json"
fi

# Step 6: Create systemd service for auto-launch
log "Creating systemd service for auto-launch..."
cat > "$SYSTEMD_SERVICE_FILE" << EOF
[Unit]
Description=RV Media Player - Jellyfin Offline Media Server
Documentation=https://github.com/your-repo/rv-media-player
After=network-online.target
Wants=network-online.target
Requires=rv-media-player-optimize.service

[Service]
Type=simple
User=media
Group=media
SupplementaryGroups=audio video dialout plugdev
WorkingDirectory=$APP_DIR
Environment=PYTHONPATH=$APP_DIR
Environment=FLASK_APP=app.py
Environment=FLASK_ENV=production
ExecStartPre=/bin/mkdir -p $APP_DIR/logs
ExecStartPre=/bin/chown media:media $APP_DIR/logs
ExecStart=$VENV_DIR/bin/python -m app.app
ExecReload=/bin/kill -HUP \$MAINPID
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=rv-media-player

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$APP_DIR /media /tmp

# Resource limits
LimitNOFILE=65536
LimitNPROC=4096

# Process priority
Nice=-5

[Install]
WantedBy=multi-user.target
EOF

chmod 644 "$SYSTEMD_SERVICE_FILE"
systemctl daemon-reload
systemctl enable rv-media-player.service

# Step 7: Create run script
log "Creating run script..."
cat > "$APP_DIR/run.sh" << EOF
#!/bin/bash
# Activate virtual environment and run the RV Media Player
cd "$APP_DIR"
source "$VENV_DIR/bin/activate"
export PYTHONPATH="$APP_DIR:\$PYTHONPATH"
export FLASK_APP=app/app.py
export FLASK_ENV=production
python -m app.app
EOF

chmod +x "$APP_DIR/run.sh"
chown media:media "$APP_DIR/run.sh"

# Step 8: Orange Pi specific optimizations
log "Applying Orange Pi optimizations..."

# Create optimization script
cat > "$APP_DIR/optimize_orangepi.sh" << EOF
#!/bin/bash
# Orange Pi optimization script for RV Media Player

# ANSI color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

log_opt() {
    echo -e "\${GREEN}[OPT]\${NC} \$1"
}

warn_opt() {
    echo -e "\${YELLOW}[OPT]\${NC} \$1"
}

log_opt "Applying Orange Pi optimizations for RV Media Player..."

# CPU governor settings for better performance
log_opt "Setting CPU governor to performance mode..."
for cpu in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
    if [ -f "\$cpu" ]; then
        echo "performance" > "\$cpu" 2>/dev/null || warn_opt "Could not set performance governor for \$cpu"
    fi
done

# GPU memory split for better video performance (if applicable)
if [ -f /boot/config.txt ]; then
    log_opt "Configuring GPU memory split..."
    grep -q "gpu_mem=" /boot/config.txt || echo "gpu_mem=128" >> /boot/config.txt
fi

# Memory and I/O optimizations
log_opt "Applying memory and I/O optimizations..."
echo 10 > /proc/sys/vm/swappiness 2>/dev/null || warn_opt "Could not set swappiness"
echo 20 > /proc/sys/vm/dirty_ratio 2>/dev/null || warn_opt "Could not set dirty_ratio"
echo 10 > /proc/sys/vm/dirty_background_ratio 2>/dev/null || warn_opt "Could not set dirty_background_ratio"

# Network optimizations
log_opt "Applying network optimizations..."
echo 'net.core.rmem_max = 16777216' >> /etc/sysctl.d/99-rv-media-player.conf
echo 'net.core.wmem_max = 16777216' >> /etc/sysctl.d/99-rv-media-player.conf
echo 'net.ipv4.tcp_rmem = 4096 87380 16777216' >> /etc/sysctl.d/99-rv-media-player.conf
echo 'net.ipv4.tcp_wmem = 4096 65536 16777216' >> /etc/sysctl.d/99-rv-media-player.conf

# Disable unnecessary services for better performance
log_opt "Disabling unnecessary services..."
services_to_disable=("bluetooth" "cups-browsed" "avahi-daemon" "ModemManager" "snapd")
for service in "\${services_to_disable[@]}"; do
    systemctl stop "\$service.service" 2>/dev/null || true
    systemctl disable "\$service.service" 2>/dev/null || true
done

# Ubuntu-specific optimizations
log_opt "Applying Ubuntu-specific optimizations..."
# Disable automatic updates during media playback
systemctl disable unattended-upgrades 2>/dev/null || true
# Disable snap refresh during usage
snap set system refresh.timer=fri,23:00-01:00 2>/dev/null || true

# Set higher priority for media processes
log_opt "Configuring process priorities..."
cat > /etc/security/limits.d/rv-media-player.conf << EOL
media soft nice -10
media hard nice -10
media soft rtprio 10
media hard rtprio 10
EOL

# Apply I/O scheduler optimizations
log_opt "Optimizing I/O schedulers..."
for disk in \$(lsblk -d -o NAME | grep -v NAME); do
    if [ -f "/sys/block/\$disk/queue/scheduler" ]; then
        # Use mq-deadline for SSDs, cfq for HDDs
        if [ -f "/sys/block/\$disk/queue/rotational" ] && [ "\$(cat /sys/block/\$disk/queue/rotational)" = "0" ]; then
            echo "mq-deadline" > "/sys/block/\$disk/queue/scheduler" 2>/dev/null || true
        else
            echo "cfq" > "/sys/block/\$disk/queue/scheduler" 2>/dev/null || true
        fi
        echo 1024 > "/sys/block/\$disk/queue/read_ahead_kb" 2>/dev/null || true
    fi
done

# Configure audio for better performance
log_opt "Configuring audio settings..."
if [ -f /etc/pulse/daemon.conf ]; then
    sed -i 's/; high-priority = yes/high-priority = yes/' /etc/pulse/daemon.conf
    sed -i 's/; nice-level = -11/nice-level = -11/' /etc/pulse/daemon.conf
fi

# Create tmpfs for temporary files if enough RAM
TOTAL_RAM=\$(free -m | awk 'NR==2{print \$2}')
if [ "\$TOTAL_RAM" -gt 1024 ]; then
    log_opt "Creating tmpfs for temporary files..."
    echo "tmpfs /tmp tmpfs defaults,noatime,mode=1777,size=256M 0 0" >> /etc/fstab
fi

log_opt "Orange Pi optimizations applied successfully"
EOF

chmod +x "$APP_DIR/optimize_orangepi.sh"
chown media:media "$APP_DIR/optimize_orangepi.sh"

# Create systemd service to run optimizations at boot
cat > "/etc/systemd/system/rv-media-player-optimize.service" << EOF
[Unit]
Description=RV Media Player Orange Pi Optimizations
After=network.target
Before=rv-media-player.service

[Service]
Type=oneshot
ExecStart=$APP_DIR/optimize_orangepi.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

chmod 644 "/etc/systemd/system/rv-media-player-optimize.service"
systemctl daemon-reload
systemctl enable rv-media-player-optimize.service

# Step 9: Create installation test script
log "Creating installation test script..."
cat > "$APP_DIR/test_installation.sh" << EOF
#!/bin/bash
# Test script for RV Media Player installation

# ANSI color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}Running RV Media Player installation tests...${NC}"

# Test 1: Check Python and virtual environment
echo -e "${YELLOW}Test 1: Checking Python and virtual environment...${NC}"
if [ -d "$VENV_DIR" ] && [ -f "$VENV_DIR/bin/python" ]; then
    echo -e "${GREEN}✓ Virtual environment exists${NC}"
    source "$VENV_DIR/bin/activate"
    PYTHON_VERSION=\$(python --version)
    echo -e "${GREEN}✓ Python version: \$PYTHON_VERSION${NC}"
    
    # Check if required packages are installed
    echo -e "${YELLOW}Checking required Python packages...${NC}"
    pip freeze | grep -q "Flask" && echo -e "${GREEN}✓ Flask installed${NC}" || echo -e "${RED}✗ Flask not installed${NC}"
    pip freeze | grep -q "watchdog" && echo -e "${GREEN}✓ watchdog installed${NC}" || echo -e "${RED}✗ watchdog not installed${NC}"
    pip freeze | grep -q "requests" && echo -e "${GREEN}✓ requests installed${NC}" || echo -e "${RED}✗ requests not installed${NC}"
    pip freeze | grep -q "mutagen" && echo -e "${GREEN}✓ mutagen installed${NC}" || echo -e "${RED}✗ mutagen not installed${NC}"
    pip freeze | grep -q "pymediainfo" && echo -e "${GREEN}✓ pymediainfo installed${NC}" || echo -e "${RED}✗ pymediainfo not installed${NC}"
    pip freeze | grep -q "cryptography" && echo -e "${GREEN}✓ cryptography installed${NC}" || echo -e "${RED}✗ cryptography not installed${NC}"
    pip freeze | grep -q "python-dotenv" && echo -e "${GREEN}✓ python-dotenv installed${NC}" || echo -e "${RED}✗ python-dotenv not installed${NC}"
    
    deactivate
else
    echo -e "${RED}✗ Virtual environment not found${NC}"
fi

# Test 2: Check VLC installation
echo -e "${YELLOW}Test 2: Checking VLC installation...${NC}"
if command -v vlc &> /dev/null; then
    VLC_VERSION=\$(vlc --version | head -n 1)
    echo -e "${GREEN}✓ VLC installed: \$VLC_VERSION${NC}"
else
    echo -e "${RED}✗ VLC not installed${NC}"
fi

# Test 3: Check directory structure
echo -e "${YELLOW}Test 3: Checking directory structure...${NC}"
[ -d "$MEDIA_DIR/movies" ] && echo -e "${GREEN}✓ Movies directory exists${NC}" || echo -e "${RED}✗ Movies directory not found${NC}"
[ -d "$MEDIA_DIR/tv-shows" ] && echo -e "${GREEN}✓ TV Shows directory exists${NC}" || echo -e "${RED}✗ TV Shows directory not found${NC}"
[ -d "$MEDIA_DIR/downloads" ] && echo -e "${GREEN}✓ Downloads directory exists${NC}" || echo -e "${RED}✗ Downloads directory not found${NC}"
[ -d "$LOGS_DIR" ] && echo -e "${GREEN}✓ Logs directory exists${NC}" || echo -e "${RED}✗ Logs directory not found${NC}"

# Test 4: Check configuration
echo -e "${YELLOW}Test 4: Checking configuration...${NC}"
[ -f "$CONFIG_DIR/app_config.json" ] && echo -e "${GREEN}✓ Configuration file exists${NC}" || echo -e "${RED}✗ Configuration file not found${NC}"

# Test 5: Check systemd services
echo -e "${YELLOW}Test 5: Checking systemd services...${NC}"
systemctl is-enabled rv-media-player.service &> /dev/null && echo -e "${GREEN}✓ RV Media Player service is enabled${NC}" || echo -e "${RED}✗ RV Media Player service is not enabled${NC}"
systemctl is-enabled rv-media-player-optimize.service &> /dev/null && echo -e "${GREEN}✓ Optimization service is enabled${NC}" || echo -e "${RED}✗ Optimization service is not enabled${NC}"

# Test 6: Check application startup
echo -e "${YELLOW}Test 6: Testing application startup...${NC}"
source "$VENV_DIR/bin/activate"
python -c "from app.app import create_app; app = create_app(); print('Application created successfully')" && echo -e "${GREEN}✓ Application imports and creates successfully${NC}" || echo -e "${RED}✗ Application failed to create${NC}"
deactivate

echo -e "${BLUE}Installation tests completed.${NC}"
EOF

chmod +x "$APP_DIR/test_installation.sh"
chown media:media "$APP_DIR/test_installation.sh"

# Make setup script executable
chmod +x "$APP_DIR/setup_config.sh"
chown media:media "$APP_DIR/setup_config.sh"

# Final steps
success "RV Media Player installation completed successfully!"
log "You can now:"
log "1. Configure the application: cd $APP_DIR && ./setup_config.sh"
log "2. Run the application manually with: cd $APP_DIR && ./run.sh"
log "3. Start the service with: sudo systemctl start rv-media-player"
log "4. Test the installation with: cd $APP_DIR && ./test_installation.sh"
log "5. Access the web interface at: http://$(hostname -I | awk '{print $1}'):5000"

# Run the test script to verify installation
log "Running installation tests..."
cd "$APP_DIR" && "./test_installation.sh"

echo
log "Installation complete! Next steps:"
log "1. Run the configuration script: cd $APP_DIR && ./setup_config.sh"
log "2. See $SCRIPT_DIR/README_ORANGEPI.md for detailed documentation"
