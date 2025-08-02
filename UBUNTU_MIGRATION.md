# Ubuntu Migration Summary

This document summarizes the changes made to migrate RV Media Player from Arch Linux to Ubuntu.

## 🔄 Changes Made

### 1. Package Manager Migration
- **From**: `pacman` (Arch Linux)
- **To**: `apt` (Ubuntu/Debian)

### 2. Package Name Updates
| Arch Linux | Ubuntu |
|------------|--------|
| `python` | `python3` |
| `python-pip` | `python3-pip` |
| `python-virtualenv` | `python3-venv` |
| `base-devel` | `build-essential` |
| `sqlite` | `sqlite3` |
| `gstreamer` | `gstreamer1.0-tools` |
| `gst-plugins-*` | `gstreamer1.0-plugins-*` |
| `mesa` | `mesa-utils` |
| `xf86-video-fbdev` | (not needed on Ubuntu) |
| `libva-mesa-driver` | `va-driver-all` |

### 3. System Service Updates
- Updated systemd service files for Ubuntu compatibility
- Changed web server user from `http` to `www-data`
- Added supplementary groups for media user: `audio`, `video`, `dialout`, `plugdev`

### 4. User Management
- Created dedicated `media` user for running the application
- Proper group assignments for hardware access
- Secure file permissions and ownership

### 5. Ubuntu-Specific Optimizations
- Disabled `unattended-upgrades` during media playback
- Configured snap refresh timing
- Added Ubuntu-specific service management

### 6. Python Environment
- Updated to use `python3` explicitly
- Enhanced virtual environment creation with proper user context
- Added Python development packages (`python3-dev`, `libffi-dev`, `libssl-dev`)

## 🗂️ Files Cleaned Up

### Removed AI/Development Files
- `.kiro/` directory (AI assistant files)
- `debug_media_items.py`
- All `test_*.html` files
- `test_status_endpoints.py`
- `static/test_progressive_loader.html`
- Entire `tests/` directory

### Updated Documentation
- `README.md` - Comprehensive application description
- `README_ORANGEPI.md` - Updated for Ubuntu
- `INSTALL_ORANGEPI.md` - Ubuntu-specific quick guide

## 📦 Installation Package Structure

```
rv-media-player/
├── install.sh                 # Main Ubuntu installation script
├── setup_config.sh           # Post-installation configuration
├── requirements.txt           # Python dependencies
├── README.md                  # Main application documentation
├── README_ORANGEPI.md         # Detailed Orange Pi setup guide
├── INSTALL_ORANGEPI.md        # Quick installation reference
├── app/                       # Application code
├── static/                    # Web assets
├── templates/                 # HTML templates
├── config/                    # Configuration templates
└── systemd/                   # Service files
```

## 🚀 Installation Process

1. **System Preparation**: Ubuntu 20.04+ on Orange Pi
2. **One-Command Install**: `sudo ./install.sh`
3. **Interactive Setup**: `./setup_config.sh`
4. **Service Management**: Standard systemd commands

## 🔧 Key Features

### Hardware Optimization
- CPU governor set to performance
- Memory and I/O optimizations
- Network buffer tuning
- Unnecessary service disabling

### Security Hardening
- Dedicated user with minimal privileges
- Systemd security features
- Secure file permissions
- Optional authentication

### Media Management
- Local and remote media integration
- Progressive loading (local first, remote background)
- Download queue management
- TV show hierarchy support

## ✅ Verification

To verify the migration was successful:

1. **Check package installation**:
   ```bash
   dpkg -l | grep -E "(python3|vlc|ffmpeg|nginx)"
   ```

2. **Verify service files**:
   ```bash
   systemctl list-unit-files | grep rv-media-player
   ```

3. **Test Python environment**:
   ```bash
   sudo -u media /opt/rv-media-player/venv/bin/python --version
   ```

4. **Check media user**:
   ```bash
   id media
   groups media
   ```

## 🎯 Benefits of Ubuntu Migration

1. **Better Hardware Support**: Ubuntu has better ARM64 support for Orange Pi
2. **Package Availability**: More media packages available in Ubuntu repositories
3. **Long-term Support**: Ubuntu LTS provides stable base for embedded systems
4. **Community Support**: Larger community and better documentation
5. **Enterprise Ready**: More suitable for production deployments

## 📋 Post-Migration Checklist

- [ ] Test installation on clean Ubuntu system
- [ ] Verify all media formats play correctly
- [ ] Test Jellyfin integration
- [ ] Confirm download functionality
- [ ] Validate service auto-start
- [ ] Check performance optimizations
- [ ] Test web interface on multiple devices

## 🆘 Troubleshooting

### Common Ubuntu-Specific Issues

1. **Permission Denied for Audio/Video**:
   ```bash
   sudo usermod -a -G audio,video media
   ```

2. **Python Module Not Found**:
   ```bash
   sudo -u media /opt/rv-media-player/venv/bin/pip install --upgrade pip
   ```

3. **Service Won't Start**:
   ```bash
   sudo journalctl -u rv-media-player -f
   ```

4. **VLC Audio Issues**:
   ```bash
   sudo apt install pulseaudio-utils
   ```

The migration to Ubuntu provides a more stable and feature-rich foundation for RV Media Player on Orange Pi devices.
