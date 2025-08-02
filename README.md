# RV Media Player

A comprehensive media management and playback application designed for Orange Pi single-board computers running Ubuntu. RV Media Player provides a modern web-based interface for managing both local media files and remote Jellyfin server content, with seamless offline capabilities and hardware-optimized performance.

## 🎯 Overview

RV Media Player bridges the gap between local media storage and cloud-based media servers, offering:

- **Unified Media Library**: Browse and play both local files and Jellyfin server content in one interface
- **Offline-First Design**: Local media is always available, with remote content cached for offline viewing
- **Progressive Loading**: Local content loads instantly while remote content loads in the background
- **Download Management**: Download remote media for permanent offline access
- **Hardware Optimization**: Specifically tuned for Orange Pi ARM processors and limited resources

## ✨ Key Features

### 🎬 Media Management
- **Local Media Scanning**: Automatic detection and organization of local video files
- **Jellyfin Integration**: Seamless connection to Jellyfin media servers
- **TV Show Hierarchy**: Organized Show → Season → Episode structure
- **Movie Library**: Clean movie browsing with metadata and thumbnails
- **Smart Filtering**: Filter by availability (Local, Remote, Both), media type, and search

### 📱 Modern Web Interface
- **Responsive Design**: Works on desktop, tablet, and mobile devices
- **Real-time Updates**: Live progress indicators and status updates
- **Progressive Enhancement**: Core functionality works even with slow connections
- **Touch-Friendly**: Optimized for touch interfaces on tablets and phones

### ⬇️ Download System
- **Background Downloads**: Download remote media without blocking the interface
- **Queue Management**: Multiple concurrent downloads with progress tracking
- **Smart Organization**: Downloaded content automatically organized by type
- **Resume Support**: Interrupted downloads can be resumed
- **Storage Management**: Configurable download locations and cleanup options

### 🎮 Playback Engine
- **VLC Integration**: Hardware-accelerated playback using VLC media player
- **Multiple Formats**: Support for all common video and audio formats
- **Subtitle Support**: Automatic subtitle detection and selection
- **Audio Track Selection**: Multiple audio track support
- **Hardware Acceleration**: GPU acceleration on supported Orange Pi models

### 🔧 Orange Pi Optimization
- **Performance Tuning**: CPU governor, memory, and I/O optimizations
- **Resource Management**: Efficient memory usage for limited RAM environments
- **Power Efficiency**: Balanced performance and power consumption
- **Hardware Detection**: Automatic optimization based on Orange Pi model

## 🚀 Quick Start

### Prerequisites
- Orange Pi 3 LTS, 4 LTS, 5, or 5 Plus
- Ubuntu 20.04 LTS or newer
- 2GB+ RAM (4GB+ recommended)
- 16GB+ storage (32GB+ recommended)
- Network connectivity

### Installation

1. **Clone the repository:**
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

4. **Start the service:**
   ```bash
   sudo systemctl start rv-media-player
   sudo systemctl enable rv-media-player
   ```

5. **Access the web interface:**
   - Open your browser to `http://[orange-pi-ip]:5000`

## 📁 Directory Structure

```
/opt/rv-media-player/          # Application directory
├── app/                       # Python application code
│   ├── api/                   # REST API endpoints
│   ├── controllers/           # Request handlers
│   ├── models/                # Data models
│   └── services/              # Business logic
├── static/                    # Web assets (CSS, JS, images)
├── templates/                 # HTML templates
├── config/                    # Configuration files
├── logs/                      # Application logs
├── data/                      # Database and cache
└── venv/                      # Python virtual environment

/media/                        # Media storage
├── movies/                    # Local movie files
├── tv-shows/                  # Local TV show files
├── downloads/                 # Downloaded content
└── local/                     # Other local media
```

## ⚙️ Configuration

### Basic Configuration

The installation creates a configuration file from the template. Edit `/opt/rv-media-player/config/app_config.json`:

> **Security Note**: This file contains sensitive credentials and is automatically ignored by git. Never commit actual configuration files to version control.

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

### Media Organization

Organize your media files as follows:

```
/media/movies/
├── The Matrix (1999)/
│   └── The Matrix (1999).mp4
├── Inception (2010)/
│   └── Inception (2010).mkv

/media/tv-shows/
├── Breaking Bad/
│   ├── Season 1/
│   │   ├── S01E01.mp4
│   │   └── S01E02.mp4
│   └── Season 2/
│       ├── S02E01.mp4
│       └── S02E02.mp4
```

## 🎮 Usage

### Web Interface

1. **Browse Media**: Use the filter dropdown to switch between:
   - **Movies**: All movie content
   - **TV Shows**: Organized show/season/episode view
   - **Local Only**: Content stored locally
   - **Remote Only**: Content on Jellyfin server
   - **Available Both**: Content available locally and remotely

2. **Search**: Use the search box to find specific titles

3. **Play Content**: Click on any media item to:
   - Play locally stored files directly
   - Stream from Jellyfin server
   - Download remote content for offline viewing

4. **Download Management**: 
   - Click download buttons to queue remote content
   - Monitor progress in the download queue
   - Downloaded content appears in local library

### Service Management

```bash
# Check service status
sudo systemctl status rv-media-player

# View logs
sudo journalctl -u rv-media-player -f

# Restart service
sudo systemctl restart rv-media-player

# Stop service
sudo systemctl stop rv-media-player
```

## 🔧 Advanced Features

### API Endpoints

RV Media Player provides a REST API for integration:

- `GET /api/media` - List all media items
- `GET /api/movies` - List movies
- `GET /api/tv-shows` - List TV shows
- `POST /api/download` - Queue download
- `GET /api/download/progress` - Download progress
- `POST /api/play` - Play media item

### Performance Monitoring

```bash
# Monitor system resources
htop

# Check disk usage
df -h

# Monitor network
iftop

# Application logs
tail -f /opt/rv-media-player/logs/app.log
```

## 🛠️ Troubleshooting

### Common Issues

1. **Service won't start**
   ```bash
   sudo journalctl -u rv-media-player -n 50
   ```

2. **VLC playback issues**
   ```bash
   vlc --version
   sudo usermod -a -G audio,video media
   ```

3. **Jellyfin connection problems**
   ```bash
   curl -I http://your-jellyfin-server:8096
   ```

4. **Permission issues**
   ```bash
   sudo chown -R media:media /opt/rv-media-player /media
   ```

### Performance Optimization

- Use fast storage (eMMC > microSD)
- Ensure adequate cooling for sustained performance
- Monitor CPU temperature: `cat /sys/class/thermal/thermal_zone0/temp`
- Check memory usage: `free -h`

## 📊 System Requirements

### Minimum Requirements
- Orange Pi 3 LTS or newer
- 2GB RAM
- 16GB storage
- 100Mbps network (for streaming)

### Recommended Requirements
- Orange Pi 5 or 5 Plus
- 4GB+ RAM
- 64GB+ eMMC storage
- Gigabit Ethernet
- Active cooling

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. **Review security**: Check `GITIGNORE_GUIDE.md` to ensure no sensitive data is committed
6. Submit a pull request

### Important Security Note
Never commit configuration files with real credentials, API keys, or personal data. See `GITIGNORE_GUIDE.md` for details on what should and shouldn't be committed.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

- **Documentation**: See `README_ORANGEPI.md` for detailed setup instructions
- **Issues**: Report bugs and feature requests on GitHub
- **Logs**: Check `/opt/rv-media-player/logs/app.log` for troubleshooting
