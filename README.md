<p align="center">
  <img src="static/images/ascii-art-white.svg" alt="RV Media Player" width="420">
</p>

```
 ██████╗ ██╗   ██╗    ███╗   ███╗███████╗██████╗ ██╗ █████╗
 ██╔══██╗██║   ██║    ████╗ ████║██╔════╝██╔══██╗██║██╔══██╗
 ██████╔╝██║   ██║    ██╔████╔██║█████╗  ██║  ██║██║███████║
 ██╔══██╗╚██╗ ██╔╝    ██║╚██╔╝██║██╔══╝  ██║  ██║██║██╔══██║
 ██║  ██║ ╚████╔╝     ██║ ╚═╝ ██║███████╗██████╔╝██║██║  ██║
 ╚═╝  ╚═╝  ╚═══╝      ╚═╝     ╚═╝╚══════╝╚═════╝ ╚═╝╚═╝  ╚═╝
                        P L A Y E R
```

<p align="center">
  <a href="https://www.buymeacoffee.com/rileysmilk" target="_blank">
    <img src="static/images/bmc-button.png" alt="Buy me a coffee" width="180">
  </a>
</p>

---

## About

A self-hosted media player for Raspberry Pi. Syncs your movie and TV library from a Jellyfin server and lets you browse, download, and play them locally - with or without an internet connection. Playback uses VLC. The web interface runs on the Pi and is accessible from any browser on your local network.

---

## Install

Requires a Raspberry Pi running Raspberry Pi OS (Bullseye or Bookworm) with `sudo` access.

**1. Clone the repo**
```bash
git clone <your-repo-url>
cd jellyfin-offline
```

**2. Run the installer**
```bash
sudo ./install.sh
```

The script asks for your Jellyfin server URL, username, API key, and where to store media (any path - including a USB mount like `/mnt/stor`), then runs fully unattended.

---

## Boot & desktop

The app is registered as a systemd service and starts automatically on every boot. A desktop shortcut is created at `~/Desktop/RV Media Player` - double-click it to open the interface in the browser.

The web interface is available at `http://localhost:5000` or `http://<pi-ip>:5000` from any device on your network.
