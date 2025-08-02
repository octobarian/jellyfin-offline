# RV Media Player - Orange Pi Installation Guide

A comprehensive media player application designed for Orange Pi single-board computers running Ubuntu. This application provides a web-based interface for managing and playing local and remote media content via Jellyfin integration.

## Features

- 🎬 **Local & Remote Media Playback** - Play media files stored locally or stream from Jellyfin server
- 📺 **TV Show Hierarchy** - Organized Show/Season/Episode structure for TV content
- ⬇️ **Download Management** - Download media from Jellyfin for offline viewing
- 🎮 **VLC Integration** - Hardware-accelerated playback using VLC media player
- 🌐 **Web Interface** - Modern, responsive web UI accessible from any device
- 🔧 **Orange Pi Optimized** - Performance optimizations specifically for Orange Pi hardware
- 🚀 **Auto-Start Service** - Systemd service for automatic startup and management

## Hardware Requirements

### Minimum Requirements
- Orange Pi 3 LTS, Orange Pi 4 LTS, or Orange Pi 5 series
- 2GB RAM (4GB+ recommended)
- 16GB microSD card (32GB+ recommended)
- Network connectivity (Ethernet or WiFi)

### Recommended Requirements
- Orange Pi 5 or Orange Pi 5 Plus
- 4GB+ RAM
- 64GB+ eMMC or high-speed microSD card
- Gigabit Ethernet connection
- USB 3.0 storage for media files

## Prerequisites

1. **Orange Pi with Ubuntu installed**
   - Download Ubuntu image for your Orange Pi model (20.04 LTS or newer)
   - Flash to microSD card or eMMC
   - Complete initial setup and network configuration

2. **Root access** - Installation requires sudo/root privileges

3. **Internet connection** - Required for downloading packages and dependencies

## Quick Installation

1. **Download the application:**
   ```bash
   git clone https://github.com/your-repo/rv-media-player.git
   cd rv-media-player
   ```

2. **Run the installation script:**
   ```bash
   sudo ./install.sh
   ```

3. **Start the service:**
   ```bash
   sudo systemctl start rv-media-player
   sudo systemctl enable rv-media-player
   ```

4. **Access the web interface:**
   - Open your browser and navigate to `http://[orange-pi-ip]:5000`
   - Replace `[orange-pi-ip]` with your Orange Pi's IP address

## Manual Installation Steps

If you prefer to install manually or need to troubleshoot:

### 1. System Update and Package Installation

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install required packages
sudo apt install -y python3 python3-pip python3-venv git vlc ffmpeg mediainfo nginx
```

### 2. Create Application User and Directories

```bash
# Create media user
sudo useradd -r -s /bin/bash -d /opt/rv-media-player -m media
sudo usermod -a -G audio,video,storage media

# Create directory structure
sudo mkdir -p /opt/rv-media-player/{logs,config,data,downloads}
sudo mkdir -p /media/{movies,tv-shows,downloads,local}
sudo chown -R media:media /opt/rv-media-player /media
```

### 3. Python Environment Setup

```bash
# Create virtual environment
sudo -u media python3 -m venv /opt/rv-media-player/venv

# Install Python dependencies
sudo -u media /opt/rv-media-player/venv/bin/pip install -r requirements.txt
```

### 4. Configuration

```bash
# Copy configuration template
sudo cp config/app_config.json.template /opt/rv-media-player/config/app_config.json
sudo chown media:media /opt/rv-media-player/config/app_config.json

# Edit configuration
sudo nano /opt/rv-media-player/config/app_config.json
```

### 5. Systemd Service Installation

```bash
# Copy service files
sudo cp systemd/*.service /etc/systemd/system/

# Reload systemd and enable services
sudo systemctl daemon-reload
sudo systemctl enable rv-media-player.service
sudo systemctl enable rv-media-player-optimize.service
```

## Configuration

### Basic Configuration

Edit `/opt/rv-media-player/config/app_config.json`:

```json
{
  "jellyfin_server_url": "http://your-jellyfin-server:8096",
  "jellyfin_username": "your-username",
  "jellyfin_api_key": "your-api-key",
  "local_media_paths": [
    "/media/movies",
    "/media/tv-shows"
  ],
  "download_directory": "/media/downloads",
  "web_interface": {
    "host": "0.0.0.0",
    "port": 5000
  }
}
```

### Orange Pi Optimizations

The installation automatically applies Orange Pi-specific optimizations:

- **CPU Governor**: Set to performance mode
- **Memory Management**: Optimized swappiness and cache settings
- **I/O Scheduler**: Optimized for storage type (SSD/HDD)
- **Network**: TCP buffer optimizations
- **Services**: Disabled unnecessary services (Bluetooth, etc.)

### Media Directory Structure

Organize your media files as follows:

```
/media/
├── movies/
│   ├── Movie Name (Year)/
│   │   └── Movie Name (Year).mp4
├── tv-shows/
│   ├── Show Name/
│   │   ├── Season 1/
│   │   │   ├── S01E01.mp4
│   │   │   └── S01E02.mp4
│   │   └── Season 2/
├── downloads/
└── local/
```

## Usage

### Web Interface

1. **Access**: Navigate to `http://[orange-pi-ip]:5000`
2. **Browse**: Use the filter dropdown to switch between Movies, TV Shows, Local, Remote
3. **Play**: Click on media items to play locally or stream from Jellyfin
4. **Download**: Use download buttons to save remote content locally

### Service Management

```bash
# Start/stop service
sudo systemctl start rv-media-player
sudo systemctl stop rv-media-player

# Check status
sudo systemctl status rv-media-player

# View logs
sudo journalctl -u rv-media-player -f

# Restart service
sudo systemctl restart rv-media-player
```

### Performance Monitoring

```bash
# Check system resources
htop

# Monitor disk I/O
iotop

# Check network usage
iftop

# View application logs
tail -f /opt/rv-media-player/logs/app.log
```

## Troubleshooting

### Common Issues

1. **Service won't start**
   ```bash
   # Check logs
   sudo journalctl -u rv-media-player -n 50
   
   # Verify configuration
   sudo -u media /opt/rv-media-player/venv/bin/python -c "import json; json.load(open('/opt/rv-media-player/config/app_config.json'))"
   ```

2. **VLC playback issues**
   ```bash
   # Test VLC directly
   vlc --version
   vlc --intf dummy /path/to/test/video.mp4
   ```

3. **Network connectivity**
   ```bash
   # Test Jellyfin connection
   curl -I http://your-jellyfin-server:8096
   ```

4. **Permission issues**
   ```bash
   # Fix ownership
   sudo chown -R media:media /opt/rv-media-player /media
   ```

### Performance Issues

1. **Slow media scanning**
   - Disable file validation in config
   - Use faster storage (eMMC vs microSD)
   - Reduce scan frequency

2. **Playback stuttering**
   - Check CPU governor is set to performance
   - Verify hardware acceleration is enabled
   - Monitor system resources during playback

3. **Network streaming issues**
   - Check network bandwidth
   - Verify Jellyfin server performance
   - Consider local downloads for frequently watched content

## Maintenance

### Regular Maintenance

```bash
# Update system packages
sudo pacman -Syu

# Clean package cache
sudo pacman -Sc

# Check disk space
df -h

# Rotate logs
sudo journalctl --vacuum-time=30d
```

### Backup Configuration

```bash
# Backup configuration
sudo cp /opt/rv-media-player/config/app_config.json /opt/rv-media-player/backups/

# Backup database (if applicable)
sudo cp /opt/rv-media-player/data/media.db /opt/rv-media-player/backups/
```

## Support

For issues, questions, or contributions:

1. Check the troubleshooting section above
2. Review application logs: `/opt/rv-media-player/logs/app.log`
3. Check system logs: `sudo journalctl -u rv-media-player`
4. Create an issue on GitHub with detailed information

## Advanced Configuration

### Nginx Reverse Proxy (Optional)

For production deployments, you can set up Nginx as a reverse proxy:

```bash
# Copy Nginx configuration
sudo cp config/nginx.conf.template /etc/nginx/nginx.conf

# Test configuration
sudo nginx -t

# Enable and start Nginx
sudo systemctl enable nginx
sudo systemctl start nginx
```

### SSL/HTTPS Setup (Optional)

```bash
# Install Certbot
sudo pacman -S certbot certbot-nginx

# Obtain SSL certificate
sudo certbot --nginx -d your-domain.com

# Auto-renewal
sudo systemctl enable certbot.timer
```

### Remote Access Setup

1. **Port Forwarding**: Configure your router to forward port 5000 (or 80/443 if using Nginx)
2. **Dynamic DNS**: Set up dynamic DNS if you don't have a static IP
3. **VPN Access**: Consider setting up a VPN for secure remote access

## License

This project is licensed under the MIT License - see the LICENSE file for details.
