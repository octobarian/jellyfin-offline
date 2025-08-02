# RV Media Player Troubleshooting Guide

This guide helps resolve common installation and runtime issues with RV Media Player on Ubuntu.

## 🔧 Installation Issues

### Pip Cache Permission Warnings

**Problem**: During installation, you see warnings like:
```
WARNING: The directory '/home/orangepi/.cache/pip' or its parent directory is not owned or is not writable by the current user.
```

**Solution**: This warning is harmless and has been fixed in the latest installation script. The script now uses:
- `sudo -u media -H` to set proper HOME environment
- `--no-cache-dir` flag to avoid cache issues
- Proper directory permissions

**If you still see this warning**:
```bash
# Clear pip cache and reinstall
sudo rm -rf /home/*/.*cache/pip
sudo ./install.sh
```

### Permission Denied Errors

**Problem**: Installation fails with permission denied errors.

**Solutions**:
1. **Run with sudo**: `sudo ./install.sh`
2. **Check directory ownership**:
   ```bash
   ls -la /opt/rv-media-player
   sudo chown -R media:media /opt/rv-media-player /media
   ```
3. **Verify media user exists**:
   ```bash
   id media
   # If not found, recreate:
   sudo userdel media 2>/dev/null || true
   sudo ./install.sh
   ```

### Virtual Environment Issues

**Problem**: Python virtual environment creation fails.

**Solutions**:
1. **Check Python installation**:
   ```bash
   python3 --version
   python3 -m venv --help
   ```
2. **Install python3-venv if missing**:
   ```bash
   sudo apt update
   sudo apt install python3-venv python3-dev
   ```
3. **Recreate virtual environment**:
   ```bash
   sudo rm -rf /opt/rv-media-player/venv
   sudo ./install.sh
   ```

### Package Installation Failures

**Problem**: Python packages fail to install.

**Solutions**:
1. **Update package lists**:
   ```bash
   sudo apt update
   sudo apt install build-essential python3-dev libffi-dev libssl-dev
   ```
2. **Check internet connectivity**:
   ```bash
   ping -c 3 pypi.org
   ```
3. **Manual package installation**:
   ```bash
   cd /opt/rv-media-player
   sudo -u media -H bash -c "source venv/bin/activate && pip install --no-cache-dir flask"
   ```

## 🚀 Runtime Issues

### Service Won't Start

**Problem**: `systemctl start rv-media-player` fails.

**Diagnosis**:
```bash
sudo systemctl status rv-media-player
sudo journalctl -u rv-media-player -f
```

**Common Solutions**:
1. **Configuration missing**:
   ```bash
   cd /opt/rv-media-player
   sudo -u media ./setup_config.sh
   ```
2. **Port already in use**:
   ```bash
   sudo netstat -tlnp | grep :5000
   # Kill process using port 5000 or change port in config
   ```
3. **Python dependencies missing**:
   ```bash
   cd /opt/rv-media-player
   sudo -u media -H bash -c "source venv/bin/activate && pip install -r requirements.txt"
   ```

### VLC Playback Issues

**Problem**: Media files won't play or VLC errors.

**Solutions**:
1. **Check VLC installation**:
   ```bash
   vlc --version
   sudo apt install vlc vlc-plugin-base
   ```
2. **Test VLC as media user**:
   ```bash
   sudo -u media vlc --intf dummy --version
   ```
3. **Check audio/video groups**:
   ```bash
   groups media
   sudo usermod -a -G audio,video media
   ```

### Jellyfin Connection Issues

**Problem**: Cannot connect to Jellyfin server.

**Diagnosis**:
```bash
curl -I http://your-jellyfin-server:8096
```

**Solutions**:
1. **Check network connectivity**:
   ```bash
   ping your-jellyfin-server
   telnet your-jellyfin-server 8096
   ```
2. **Verify Jellyfin credentials**:
   - Check server URL format: `http://ip:8096` (not `https`)
   - Verify API key in Jellyfin Dashboard > API Keys
   - Check username spelling and case sensitivity
3. **Update configuration**:
   ```bash
   cd /opt/rv-media-player
   sudo -u media ./setup_config.sh
   ```

### Web Interface Not Accessible

**Problem**: Cannot access web interface at http://ip:5000.

**Solutions**:
1. **Check service status**:
   ```bash
   sudo systemctl status rv-media-player
   ```
2. **Check port binding**:
   ```bash
   sudo netstat -tlnp | grep :5000
   ```
3. **Check firewall**:
   ```bash
   sudo ufw status
   sudo ufw allow 5000
   ```
4. **Check configuration**:
   ```bash
   grep -A 5 "web_interface" /opt/rv-media-player/config/app_config.json
   ```

## 🔍 Diagnostic Commands

### System Information
```bash
# OS and hardware info
uname -a
lsb_release -a
free -h
df -h

# Network info
hostname -I
ip route show default
```

### Application Status
```bash
# Service status
sudo systemctl status rv-media-player
sudo journalctl -u rv-media-player --since "1 hour ago"

# Process info
ps aux | grep python
ps aux | grep vlc

# File permissions
ls -la /opt/rv-media-player
ls -la /media
```

### Python Environment
```bash
# Virtual environment
cd /opt/rv-media-player
sudo -u media -H bash -c "source venv/bin/activate && python --version"
sudo -u media -H bash -c "source venv/bin/activate && pip list"

# Test imports
sudo -u media -H bash -c "cd /opt/rv-media-player && source venv/bin/activate && python -c 'import flask; print(\"Flask OK\")'"
```

## 📞 Getting Help

### Before Reporting Issues

1. **Run verification script**:
   ```bash
   ./verify_install.sh
   ```

2. **Collect logs**:
   ```bash
   sudo journalctl -u rv-media-player > rv-media-player.log
   tail -100 /opt/rv-media-player/logs/app.log
   ```

3. **Check configuration**:
   ```bash
   sudo -u media cat /opt/rv-media-player/config/app_config.json
   ```

### Information to Include

When reporting issues, please include:
- Ubuntu version: `lsb_release -a`
- Orange Pi model
- Error messages (exact text)
- Service logs: `sudo journalctl -u rv-media-player`
- Installation verification results
- Steps to reproduce the issue

### Common Log Locations

- **Service logs**: `sudo journalctl -u rv-media-player`
- **Application logs**: `/opt/rv-media-player/logs/app.log`
- **System logs**: `/var/log/syslog`
- **Installation logs**: Terminal output during `./install.sh`

## 🔄 Clean Reinstallation

If all else fails, perform a clean reinstallation:

```bash
# Stop and disable service
sudo systemctl stop rv-media-player
sudo systemctl disable rv-media-player

# Remove application
sudo rm -rf /opt/rv-media-player
sudo rm -f /etc/systemd/system/rv-media-player.service

# Remove user (optional)
sudo userdel media

# Reinstall
sudo ./install.sh
```

**Note**: This will remove all configuration and downloaded media. Back up important data first.
