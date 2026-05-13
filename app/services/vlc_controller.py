"""
VLC Controller Service

Handles VLC media player integration for local file playback and streaming.
Provides methods for launching VLC processes, managing playback, and detecting VLC installation.
"""

import glob
import logging
import os
import subprocess
import platform
import shutil
import time
from typing import Optional, List
from pathlib import Path


logger = logging.getLogger(__name__)


class VLCController:
    """Controller for VLC media player integration."""

    def __init__(self, vlc_path: Optional[str] = None):
        self.vlc_path: Optional[str] = vlc_path  # may be overridden by detection
        self.current_process: Optional[subprocess.Popen] = None
        if vlc_path:
            # Caller supplied an explicit path - use it directly if it exists.
            if not os.path.exists(vlc_path):
                logger.warning(f"Supplied VLC path does not exist: {vlc_path}")
                self.vlc_path = None
        else:
            self._detect_vlc_installation()
    
    def _detect_vlc_installation(self) -> None:
        """Detect VLC installation and set the path."""
        system = platform.system().lower()
        
        if system == "windows":
            # Common VLC installation paths on Windows
            possible_paths = [
                r"C:\Program Files\VideoLAN\VLC\vlc.exe",
                r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
                os.path.expanduser(r"~\AppData\Local\Programs\VLC\vlc.exe")
            ]
            
            for path in possible_paths:
                if os.path.exists(path):
                    self.vlc_path = path
                    return
                    
            # Try to find VLC in PATH
            vlc_in_path = shutil.which("vlc")
            if vlc_in_path:
                self.vlc_path = vlc_in_path
                
        elif system == "linux":
            # Try common Linux paths and PATH
            possible_paths = [
                "/usr/bin/vlc",
                "/usr/local/bin/vlc",
                "/snap/bin/vlc"
            ]
            
            for path in possible_paths:
                if os.path.exists(path):
                    self.vlc_path = path
                    return
                    
            # Try to find VLC in PATH
            vlc_in_path = shutil.which("vlc")
            if vlc_in_path:
                self.vlc_path = vlc_in_path
                
        elif system == "darwin":  # macOS
            possible_paths = [
                "/Applications/VLC.app/Contents/MacOS/VLC"
            ]
            
            for path in possible_paths:
                if os.path.exists(path):
                    self.vlc_path = path
                    return
                    
            vlc_in_path = shutil.which("vlc")
            if vlc_in_path:
                self.vlc_path = vlc_in_path
    
    def is_vlc_installed(self) -> bool:
        """Check if VLC is installed and accessible."""
        if self.vlc_path is None:
            return False
        # For paths found via shutil.which, they should exist
        return os.path.exists(self.vlc_path) or shutil.which(os.path.basename(self.vlc_path)) is not None
    
    def install_vlc(self) -> bool:
        """
        Attempt to install VLC automatically.
        Returns True if installation was successful or VLC is already installed.
        """
        if self.is_vlc_installed():
            return True
            
        system = platform.system().lower()
        
        try:
            if system == "linux":
                # Try different package managers
                package_managers = [
                    ["pacman", "-S", "--noconfirm", "vlc"],  # Arch Linux
                    ["apt-get", "install", "-y", "vlc"],     # Debian/Ubuntu
                    ["yum", "install", "-y", "vlc"],         # RHEL/CentOS
                    ["dnf", "install", "-y", "vlc"],         # Fedora
                ]
                
                for cmd in package_managers:
                    if shutil.which(cmd[0]):
                        result = subprocess.run(cmd, capture_output=True, text=True)
                        if result.returncode == 0:
                            self._detect_vlc_installation()
                            return self.is_vlc_installed()
                            
            elif system == "darwin":  # macOS
                # Try Homebrew
                if shutil.which("brew"):
                    result = subprocess.run(["brew", "install", "--cask", "vlc"], 
                                          capture_output=True, text=True)
                    if result.returncode == 0:
                        self._detect_vlc_installation()
                        return self.is_vlc_installed()
                        
            elif system == "windows":
                # On Windows, we can't easily auto-install, so just return False
                # User will need to install VLC manually
                return False
                
        except Exception:
            pass
            
        return False
    
    @staticmethod
    def _vlc_env() -> dict:
        """
        Environment for the VLC subprocess.

        Ensures DISPLAY, WAYLAND_DISPLAY, XDG_RUNTIME_DIR, and XAUTHORITY are
        set so VLC can reach the display server when launched from a systemd
        service that does not inherit the desktop session environment.
        Do NOT override QT_QPA_PLATFORM - forcing 'xcb' breaks VLC on Pi
        configs where the Qt xcb platform plugin is not installed.
        """
        env = os.environ.copy()

        # X11 display fallback (used directly or via XWayland)
        env.setdefault("DISPLAY", ":0")

        # Wayland display fallback for Pi OS Bookworm (Wayfire/Wayland default)
        env.setdefault("WAYLAND_DISPLAY", "wayland-1")

        # XDG_RUNTIME_DIR is required for Wayland socket access
        if "XDG_RUNTIME_DIR" not in env:
            try:
                uid = os.getuid()
                runtime_dir = f"/run/user/{uid}"
                if os.path.exists(runtime_dir):
                    env["XDG_RUNTIME_DIR"] = runtime_dir
            except Exception:
                pass

        # XAUTHORITY for X11/XWayland auth.  Systemd services don't inherit
        # it, and the default Pi user is 'pi' — not 'media' or 'root'.
        if "XAUTHORITY" not in env:
            candidates = [
                os.path.expanduser("~/.Xauthority"),
                "/home/pi/.Xauthority",
                "/home/media/.Xauthority",
                "/root/.Xauthority",
            ]
            # Catch any other user home directories on this machine
            candidates.extend(glob.glob("/home/*/.Xauthority"))

            for candidate in candidates:
                if os.path.exists(candidate):
                    env["XAUTHORITY"] = candidate
                    logger.debug(f"Using XAUTHORITY: {candidate}")
                    break

        return env

    @staticmethod
    def _linux_vout_flags() -> List[str]:
        """
        Video-output flags for Raspberry Pi / Linux.

        Pi OS Bookworm (and later) runs Wayland by default (Wayfire).  Forcing
        --vout=xcb_x11 on a Wayland-only session causes VLC to exit immediately
        with no window.  On X11 sessions (Pi OS Bullseye and earlier, or when
        Wayland is disabled) the GL renderer silently produces a black window on
        most Pi GPU configs, so xcb_x11 (software blitting) is still needed.

        Detection uses the session environment inherited by the Flask process:
        - WAYLAND_DISPLAY set  → Wayland session → let VLC auto-detect output
        - XDG_SESSION_TYPE=wayland → same
        - Otherwise            → assume X11 → force xcb_x11

        Do NOT add --intf=qt  : if vlc-plugin-qt is missing VLC exits immediately.
        Do NOT add --no-embedded-video : produces a borderless overlay with no
                                         controls toolbar.
        """
        is_wayland = bool(os.environ.get("WAYLAND_DISPLAY")) or \
                     os.environ.get("XDG_SESSION_TYPE") == "wayland"
        if is_wayland:
            return []  # Let VLC auto-detect (uses wl or gl output on Wayland)
        return ["--vout=xcb_x11"]

    def play_local_file(self, file_path: str, fullscreen: bool = False,
                        title: Optional[str] = None) -> bool:
        """
        Play a local media file using VLC.

        Args:
            file_path: Path to the local media file
            fullscreen: Whether to start VLC in fullscreen mode
            title: Window/playlist title shown in VLC (overrides embedded metadata)

        Returns:
            True if VLC was launched successfully, False otherwise
        """
        if not self.is_vlc_installed():
            return False

        if not os.path.exists(file_path):
            return False

        # Stop any currently running VLC process
        self.stop_playback()

        cmd = [self.vlc_path]

        # On Linux (Raspberry Pi) force xcb_x11 output - the default GL/xcb
        # renderer silently produces a black window on most Pi configurations.
        if platform.system().lower() == "linux":
            cmd.extend(self._linux_vout_flags())

        if fullscreen:
            cmd.append("--fullscreen")

        # Override the window title with the proper media title so VLC doesn't
        # show the embedded MKV track name (e.g. "MKV-REMUX") instead.
        if title:
            cmd.extend(["--meta-title", title])

        cmd.append("--play-and-exit")
        cmd.append(file_path)

        logger.info(f"Launching VLC: {' '.join(cmd)}")
        try:
            startupinfo = None
            if platform.system() == "Windows":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_SHOW

            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=self._vlc_env(),
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if platform.system() == "Windows" else 0,
                startupinfo=startupinfo,
            )
            time.sleep(0.4)
            if self.current_process.poll() is not None:
                logger.error(f"VLC exited immediately (code {self.current_process.returncode})")
                return False
            return True
        except Exception as e:
            logger.error(f"Failed to launch VLC: {e}")
            return False

    def play_stream(self, stream_url: str, fullscreen: bool = False,
                    title: Optional[str] = None) -> bool:
        """
        Play a streaming URL using VLC.

        Args:
            stream_url: URL of the stream to play
            fullscreen: Whether to start VLC in fullscreen mode
            title: Window/playlist title shown in VLC

        Returns:
            True if VLC was launched successfully, False otherwise
        """
        if not self.is_vlc_installed():
            return False

        # Stop any currently running VLC process
        self.stop_playback()

        cmd = [self.vlc_path]

        # Same xcb_x11 fix for Pi - applies equally to network streams.
        if platform.system().lower() == "linux":
            cmd.extend(self._linux_vout_flags())

        if fullscreen:
            cmd.append("--fullscreen")

        if title:
            cmd.extend(["--meta-title", title])

        cmd.extend([
            "--play-and-exit",
            "--network-caching", "3000",  # 3-second network buffer
        ])

        cmd.append(stream_url)

        logger.info(f"Launching VLC stream: {' '.join(cmd)}")
        try:
            startupinfo = None
            if platform.system() == "Windows":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_SHOW

            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=self._vlc_env(),
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if platform.system() == "Windows" else 0,
                startupinfo=startupinfo,
            )
            time.sleep(0.4)
            if self.current_process.poll() is not None:
                logger.error(f"VLC stream exited immediately (code {self.current_process.returncode})")
                return False
            return True
        except Exception as e:
            logger.error(f"Failed to launch VLC stream: {e}")
            return False

    def stop_playback(self) -> bool:
        """
        Stop the current VLC playback.
        
        Returns:
            True if playback was stopped successfully, False otherwise
        """
        if self.current_process is None:
            return True
            
        try:
            # Terminate the VLC process
            self.current_process.terminate()
            
            # Wait for process to terminate (with timeout)
            try:
                self.current_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # Force kill if it doesn't terminate gracefully
                self.current_process.kill()
                self.current_process.wait()
                
            self.current_process = None
            return True
            
        except Exception:
            return False
    
    def is_playing(self) -> bool:
        """
        Check if VLC is currently playing.
        
        Returns:
            True if VLC process is running, False otherwise
        """
        if self.current_process is None:
            return False
            
        # Check if process is still running
        return self.current_process.poll() is None
    
    def get_vlc_version(self) -> Optional[str]:
        """
        Get the version of the installed VLC.
        
        Returns:
            VLC version string if available, None otherwise
        """
        if not self.is_vlc_installed():
            return None
            
        try:
            result = subprocess.run(
                [self.vlc_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                # Parse version from output
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'VLC media player' in line:
                        return line.strip()
                        
        except Exception:
            pass
            
        return None
    
    def get_supported_formats(self) -> List[str]:
        """
        Get list of supported media formats.
        
        Returns:
            List of supported file extensions
        """
        # Common formats supported by VLC
        return [
            '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm',
            '.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma',
            '.m4v', '.3gp', '.asf', '.rm', '.rmvb', '.vob',
            '.ts', '.m2ts', '.mts', '.divx', '.xvid'
        ]
    
    def cleanup(self) -> None:
        """Clean up resources and stop any running processes."""
        self.stop_playback()