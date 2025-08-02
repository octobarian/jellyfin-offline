# RV Media Player Installation Troubleshooting Guide

This guide addresses common issues encountered during installation and deployment of the RV Media Player on Orange Pi systems.

## Common Installation Issues

### 1. ModuleNotFoundError: No module named 'config.configuration'

**Problem**: After installation to `/opt/rv-media-player`, running `./run.sh` shows:
```
ModuleNotFoundError: No module named 'config.configuration'
```

**Root Cause**: Python cannot find the application modules because the Python path is not correctly configured for the installed location.

**Solutions**:

#### Solution A: Use the Fixed Installation Script
The updated `install.sh` script now creates a proper `run.sh` with correct Python path configuration:

```bash
# Uninstall the current installation
sudo ./uninstall.sh

# Pull latest changes
git pull

# Reinstall with the fixed script
sudo ./install.sh
```

#### Solution B: Manual Fix for Existing Installation
If you don't want to reinstall, manually fix the `/opt/rv-media-player/run.sh` file:

```bash
sudo nano /opt/rv-media-player/run.sh
```

Replace the content with:
```bash
#!/bin/bash
# Activate virtual environment and run the RV Media Player
cd "/opt/rv-media-player"
source "/opt/rv-media-player/venv/bin/activate"
export PYTHONPATH="/opt/rv-media-player:$PYTHONPATH"
export FLASK_APP=app/app.py
export FLASK_ENV=production
python -m app.app
```

#### Solution C: Fix the systemd Service
Also update the systemd service file:

```bash
sudo nano /etc/systemd/system/rv-media-player.service
```

Ensure the `ExecStart` line uses:
```
ExecStart=/opt/rv-media-player/venv/bin/python -m app.app
```

Then reload and restart:
```bash
sudo systemctl daemon-reload
sudo systemctl restart rv-media-player
```

### 2. Permission Issues

**Problem**: Permission denied errors when running the application.

**Solution**:
```bash
# Fix ownership
sudo chown -R media:media /opt/rv-media-player /media

# Fix permissions
sudo chmod -R 755 /opt/rv-media-player
sudo chmod 700 /opt/rv-media-player/config
sudo chmod 600 /opt/rv-media-player/config/app_config.json
```

### 3. Virtual Environment Issues

**Problem**: Virtual environment not found or corrupted.

**Solution**:
```bash
# Remove and recreate virtual environment
sudo rm -rf /opt/rv-media-player/venv
sudo -u media -H bash -c "cd /opt/rv-media-player && python3 -m venv venv"
sudo -u media -H bash -c "cd /opt/rv-media-player && source venv/bin/activate && pip install --no-cache-dir -r requirements.txt"
```

### 4. Missing Dependencies

**Problem**: Import errors for specific Python packages.

**Solution**:
```bash
# Activate virtual environment and install missing packages
cd /opt/rv-media-player
source venv/bin/activate
pip install --no-cache-dir flask requests python-dotenv watchdog mutagen cryptography
```

### 5. Port Already in Use

**Problem**: Flask cannot bind to port 5000.

**Solutions**:
```bash
# Check what's using port 5000
sudo netstat -tulpn | grep :5000

# Kill the process using port 5000
sudo kill -9 <PID>

# Or use a different port by modifying app.py
```

### 6. VLC Not Found

**Problem**: VLC controller fails to initialize.

**Solution**:
```bash
# Install VLC
sudo apt update
sudo apt install vlc

# Verify installation
which vlc
vlc --version
```

## Development Environment Issues

### 1. Running from Source Directory

**Problem**: Module import errors when running from the development directory.

**Solution**: Use the provided run scripts:

**Linux/macOS**:
```bash
./run.sh
```

**Windows**:
```batch
run.bat
```

### 2. Python Path Issues in Development

**Problem**: Import errors in development environment.

**Solution**: Set the Python path manually:
```bash
export PYTHONPATH="$(pwd):$PYTHONPATH"
python -m app.app
```

## Service Management Issues

### 1. Service Won't Start

**Problem**: systemd service fails to start.

**Diagnosis**:
```bash
# Check service status
sudo systemctl status rv-media-player

# Check logs
sudo journalctl -u rv-media-player -f

# Check if service file is valid
sudo systemctl daemon-reload
```

### 2. Service Starts but Application Fails

**Problem**: Service starts but application crashes immediately.

**Diagnosis**:
```bash
# Check application logs
sudo tail -f /opt/rv-media-player/logs/app.log

# Run manually to see errors
sudo -u media -H bash -c "cd /opt/rv-media-player && source venv/bin/activate && python -m app.app"
```

## Configuration Issues

### 1. Configuration File Not Found

**Problem**: Application cannot find configuration file.

**Solution**:
```bash
# Create default configuration
sudo mkdir -p /opt/rv-media-player/config
sudo chown media:media /opt/rv-media-player/config
sudo chmod 700 /opt/rv-media-player/config

# Run configuration setup
cd /opt/rv-media-player
sudo -u media ./setup_config.sh
```

### 2. Encryption Key Issues

**Problem**: Configuration decryption fails.

**Solution**:
```bash
# Remove corrupted encryption key (will create new one)
sudo rm -f /opt/rv-media-player/config/.encryption_key

# Reconfigure application
cd /opt/rv-media-player
sudo -u media ./setup_config.sh
```

## Media Directory Issues

### 1. Media Directories Not Accessible

**Problem**: Application cannot access media directories.

**Solution**:
```bash
# Create media directories
sudo mkdir -p /media/{movies,tv-shows,downloads,local}

# Set proper ownership and permissions
sudo chown -R media:media /media
sudo chmod -R 755 /media
```

### 2. External Storage Not Mounted

**Problem**: External USB drives not accessible.

**Solution**:
```bash
# Check mounted drives
lsblk
df -h

# Mount USB drive (example)
sudo mkdir -p /media/usb
sudo mount /dev/sda1 /media/usb
sudo chown media:media /media/usb

# Add to fstab for permanent mounting
echo "/dev/sda1 /media/usb ext4 defaults,user,rw 0 0" | sudo tee -a /etc/fstab
```

## Network Issues

### 1. Cannot Access Web Interface

**Problem**: Cannot access the web interface from other devices.

**Solutions**:
```bash
# Check if service is running
sudo systemctl status rv-media-player

# Check if port is open
sudo netstat -tulpn | grep :5000

# Check firewall
sudo ufw status
sudo ufw allow 5000

# Get IP address
hostname -I
```

### 2. Jellyfin Connection Issues

**Problem**: Cannot connect to Jellyfin server.

**Diagnosis**:
```bash
# Test connectivity
ping jellyfin-server-ip
curl -I http://jellyfin-server-ip:8096

# Check configuration
cat /opt/rv-media-player/config/app_config.json
```

## Performance Issues

### 1. Slow Media Scanning

**Problem**: Media library scanning is very slow.

**Solutions**:
- Reduce the number of validation workers in configuration
- Increase cache TTL
- Use faster storage (SSD instead of HDD)
- Optimize Orange Pi performance settings

### 2. High CPU Usage

**Problem**: Application uses too much CPU.

**Solutions**:
```bash
# Check CPU governor
cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

# Set to performance mode
sudo /opt/rv-media-player/optimize_orangepi.sh

# Monitor processes
htop
```

## Uninstallation and Reinstallation

### Complete Uninstallation

```bash
# Stop services
sudo systemctl stop rv-media-player
sudo systemctl disable rv-media-player

# Run uninstall script
sudo ./uninstall.sh

# Manual cleanup if needed
sudo rm -rf /opt/rv-media-player
sudo rm -f /etc/systemd/system/rv-media-player*
sudo systemctl daemon-reload
```

### Clean Reinstallation

```bash
# Uninstall
sudo ./uninstall.sh

# Update source code
git pull

# Reinstall
sudo ./install.sh
```

## Getting Help

### Log Files to Check

1. **Application logs**: `/opt/rv-media-player/logs/app.log`
2. **System logs**: `sudo journalctl -u rv-media-player`
3. **Installation logs**: Check terminal output during installation

### Diagnostic Commands

```bash
# System information
uname -a
lsb_release -a
free -h
df -h

# Python environment
python3 --version
pip3 --version

# Service status
sudo systemctl status rv-media-player
sudo systemctl list-unit-files | grep rv-media

# Network status
ip addr show
netstat -tulpn | grep :5000
```

### Creating Bug Reports

When reporting issues, include:

1. **System Information**: Output of diagnostic commands above
2. **Error Messages**: Complete error messages and stack traces
3. **Log Files**: Relevant portions of log files
4. **Steps to Reproduce**: Exact steps that led to the issue
5. **Configuration**: Sanitized configuration file (remove sensitive data)

## Quick Fix Checklist

When encountering issues, try these steps in order:

1. **Check service status**: `sudo systemctl status rv-media-player`
2. **Check logs**: `sudo tail -f /opt/rv-media-player/logs/app.log`
3. **Restart service**: `sudo systemctl restart rv-media-player`
4. **Check permissions**: `ls -la /opt/rv-media-player`
5. **Test manual run**: `sudo -u media -H bash -c "cd /opt/rv-media-player && source venv/bin/activate && python -m app.app"`
6. **Check Python path**: Ensure PYTHONPATH includes `/opt/rv-media-player`
7. **Verify dependencies**: `source /opt/rv-media-player/venv/bin/activate && pip list`
8. **Check configuration**: Verify `/opt/rv-media-player/config/app_config.json` exists and is readable

If none of these steps resolve the issue, consider a clean reinstallation using the updated installation script.
