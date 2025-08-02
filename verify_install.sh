#!/bin/bash

# RV Media Player Installation Verification Script
# Run this script to verify the installation was successful

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}🔍 RV Media Player Installation Verification${NC}"
echo "=============================================="
echo

# Check if running as root
if [[ $EUID -eq 0 ]]; then
    echo -e "${YELLOW}⚠️  Running as root. Some checks may not reflect normal user experience.${NC}"
    echo
fi

# Check 1: Application directory
echo -e "${BLUE}📁 Checking application directory...${NC}"
if [ -d "/opt/rv-media-player" ]; then
    echo -e "${GREEN}✓ Application directory exists: /opt/rv-media-player${NC}"
    ls -la /opt/rv-media-player | head -10
else
    echo -e "${RED}✗ Application directory missing: /opt/rv-media-player${NC}"
fi
echo

# Check 2: Media user
echo -e "${BLUE}👤 Checking media user...${NC}"
if id "media" &>/dev/null; then
    echo -e "${GREEN}✓ Media user exists${NC}"
    echo "   User info: $(id media)"
    echo "   Groups: $(groups media)"
else
    echo -e "${RED}✗ Media user does not exist${NC}"
fi
echo

# Check 3: Media directories
echo -e "${BLUE}📂 Checking media directories...${NC}"
for dir in "/media/movies" "/media/tv-shows" "/media/downloads" "/media/local"; do
    if [ -d "$dir" ]; then
        echo -e "${GREEN}✓ Directory exists: $dir${NC}"
    else
        echo -e "${RED}✗ Directory missing: $dir${NC}"
    fi
done
echo

# Check 4: Python virtual environment
echo -e "${BLUE}🐍 Checking Python virtual environment...${NC}"
if [ -d "/opt/rv-media-player/venv" ]; then
    echo -e "${GREEN}✓ Virtual environment exists${NC}"
    if [ -f "/opt/rv-media-player/venv/bin/python" ]; then
        echo -e "${GREEN}✓ Python executable found${NC}"
        echo "   Python version: $(/opt/rv-media-player/venv/bin/python --version)"
    else
        echo -e "${RED}✗ Python executable missing in venv${NC}"
    fi
else
    echo -e "${RED}✗ Virtual environment missing${NC}"
fi
echo

# Check 5: Required Python packages
echo -e "${BLUE}📦 Checking Python packages...${NC}"
if [ -f "/opt/rv-media-player/venv/bin/pip" ]; then
    echo "Checking key packages..."
    packages=("flask" "requests" "python-vlc" "mutagen" "psutil")
    for package in "${packages[@]}"; do
        if /opt/rv-media-player/venv/bin/pip show "$package" &>/dev/null; then
            echo -e "${GREEN}✓ $package installed${NC}"
        else
            echo -e "${RED}✗ $package missing${NC}"
        fi
    done
else
    echo -e "${RED}✗ pip not found in virtual environment${NC}"
fi
echo

# Check 6: System packages
echo -e "${BLUE}🔧 Checking system packages...${NC}"
packages=("vlc" "ffmpeg" "python3" "nginx")
for package in "${packages[@]}"; do
    if command -v "$package" &>/dev/null; then
        echo -e "${GREEN}✓ $package installed${NC}"
    else
        echo -e "${RED}✗ $package missing${NC}"
    fi
done
echo

# Check 7: Systemd service
echo -e "${BLUE}⚙️  Checking systemd service...${NC}"
if [ -f "/etc/systemd/system/rv-media-player.service" ]; then
    echo -e "${GREEN}✓ Service file exists${NC}"
    if systemctl is-enabled rv-media-player &>/dev/null; then
        echo -e "${GREEN}✓ Service is enabled${NC}"
    else
        echo -e "${YELLOW}⚠️  Service is not enabled${NC}"
    fi
    
    if systemctl is-active rv-media-player &>/dev/null; then
        echo -e "${GREEN}✓ Service is running${NC}"
    else
        echo -e "${YELLOW}⚠️  Service is not running${NC}"
    fi
else
    echo -e "${RED}✗ Service file missing${NC}"
fi
echo

# Check 8: Configuration
echo -e "${BLUE}⚙️  Checking configuration...${NC}"
if [ -f "/opt/rv-media-player/config/app_config.json.template" ]; then
    echo -e "${GREEN}✓ Configuration template exists${NC}"
else
    echo -e "${RED}✗ Configuration template missing${NC}"
fi

if [ -f "/opt/rv-media-player/config/app_config.json" ]; then
    echo -e "${GREEN}✓ Configuration file exists${NC}"
else
    echo -e "${YELLOW}⚠️  Configuration file not created yet (run setup_config.sh)${NC}"
fi
echo

# Check 9: Permissions
echo -e "${BLUE}🔒 Checking permissions...${NC}"
if [ -d "/opt/rv-media-player" ]; then
    owner=$(stat -c '%U:%G' /opt/rv-media-player)
    if [ "$owner" = "media:media" ]; then
        echo -e "${GREEN}✓ Application directory owned by media:media${NC}"
    else
        echo -e "${RED}✗ Application directory ownership incorrect: $owner${NC}"
    fi
fi

if [ -d "/media" ]; then
    owner=$(stat -c '%U:%G' /media)
    if [ "$owner" = "media:media" ]; then
        echo -e "${GREEN}✓ Media directory owned by media:media${NC}"
    else
        echo -e "${YELLOW}⚠️  Media directory ownership: $owner${NC}"
    fi
fi
echo

# Summary
echo -e "${BLUE}📋 Installation Summary${NC}"
echo "======================="

if [ -d "/opt/rv-media-player" ] && id "media" &>/dev/null && [ -f "/etc/systemd/system/rv-media-player.service" ]; then
    echo -e "${GREEN}✅ Installation appears successful!${NC}"
    echo
    echo -e "${BLUE}Next steps:${NC}"
    echo "1. Configure the application: cd /opt/rv-media-player && sudo -u media ./setup_config.sh"
    echo "2. Start the service: sudo systemctl start rv-media-player"
    echo "3. Check service status: sudo systemctl status rv-media-player"
    echo "4. Access web interface: http://$(hostname -I | awk '{print $1}'):5000"
else
    echo -e "${RED}❌ Installation has issues. Please review the errors above.${NC}"
    echo
    echo -e "${BLUE}Troubleshooting:${NC}"
    echo "1. Re-run the installation script: sudo ./install.sh"
    echo "2. Check the installation logs above for specific errors"
    echo "3. Ensure you have sudo privileges"
fi
