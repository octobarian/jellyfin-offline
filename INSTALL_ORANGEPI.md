# RV Media Player - Orange Pi Ubuntu Quick Install Guide

## Quick Installation

1. **Download and extract the application:**
   ```bash
   git clone https://github.com/your-repo/rv-media-player.git
   cd rv-media-player
   ```

2. **Run the installation script:**
   ```bash
   sudo ./install.sh
   ```

3. **Configure the application:**
   ```bash
   ./setup_config.sh
   ```

4. **Access the web interface:**
   - Open browser: `http://[orange-pi-ip]:5000`

## What Gets Installed

### System Packages
- **Core**: Python 3, pip, venv, git, curl, wget, build-essential
- **Media**: VLC, FFmpeg, MediaInfo, GStreamer plugins, libavcodec-extra
- **Network**: Nginx, OpenSSH, Samba, network utilities
- **System**: htop, nano, vim, screen, tmux, hardware utilities
- **Hardware**: Mesa utils, VA-API drivers, VDPAU drivers

### Python Dependencies
- **Web Framework**: Flask, Werkzeug, Gunicorn
- **Media Processing**: python-vlc, mutagen, pymediainfo, Pillow
- **System**: psutil, watchdog, schedule
- **Utilities**: requests, cryptography, PyYAML, colorama, tqdm

### Services
- **rv-media-player.service** - Main application service
- **rv-media-player-optimize.service** - Orange Pi optimizations
- **nginx.service** - Web server (optional)

### Directory Structure
```
/opt/rv-media-player/          # Application directory
├── app/                       # Application code
├── venv/                      # Python virtual environment
├── config/                    # Configuration files
├── logs/                      # Application logs
├── data/                      # Database and cache
└── downloads/                 # Downloaded media

/media/                        # Media storage
├── movies/                    # Movie files
├── tv-shows/                  # TV show files
├── downloads/                 # Downloaded content
└── local/                     # Other local media
```

## Orange Pi Optimizations

The installation automatically applies these optimizations:

- **CPU Governor**: Set to performance mode
- **Memory Management**: Optimized swappiness and cache settings
- **I/O Scheduler**: Optimized for storage type (SSD/HDD)
- **Network**: TCP buffer optimizations for streaming
- **Services**: Disabled unnecessary services (Bluetooth, etc.)
- **Process Priority**: Higher priority for media processes
- **GPU Memory**: Configured for video playback (if applicable)

## Post-Installation

### Service Management
```bash
# Start service
sudo systemctl start rv-media-player

# Stop service
sudo systemctl stop rv-media-player

# Check status
sudo systemctl status rv-media-player

# View logs
sudo journalctl -u rv-media-player -f
```

### Configuration
- Main config: `/opt/rv-media-player/config/app_config.json`
- Environment: `/opt/rv-media-player/.env` (optional)
- Logs: `/opt/rv-media-player/logs/app.log`

### Testing
```bash
# Run installation tests
./test_installation.sh

# Test VLC
vlc --version

# Test Jellyfin connection
curl -I http://your-jellyfin-server:8096
```

## Troubleshooting

### Common Issues
1. **Service won't start**: Check logs with `sudo journalctl -u rv-media-player`
2. **VLC issues**: Test with `vlc --version` and check audio/video groups
3. **Network issues**: Verify Jellyfin server connectivity
4. **Permission issues**: Run `sudo chown -R media:media /opt/rv-media-player /media`

### Performance Issues
- Check CPU governor: `cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor`
- Monitor resources: `htop`, `iotop`, `iftop`
- Check disk space: `df -h`

## Support

For detailed documentation, see `README_ORANGEPI.md`

For issues:
1. Check application logs: `/opt/rv-media-player/logs/app.log`
2. Check system logs: `sudo journalctl -u rv-media-player`
3. Run tests: `./test_installation.sh`
4. Create GitHub issue with logs and system info
