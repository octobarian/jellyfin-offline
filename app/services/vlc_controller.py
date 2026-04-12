"""
VLC Controller Service

Handles VLC media player integration for local file playback and streaming.
Provides methods for launching VLC processes, managing playback, and detecting VLC installation.
"""

import logging
import os
import subprocess
import platform
import shutil
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

        Ensures DISPLAY and XAUTHORITY are set so VLC can reach the X server
        when launched from a systemd service that may not inherit them.
        Do NOT override QT_QPA_PLATFORM - forcing 'xcb' breaks VLC on Pi
        configs where the Qt xcb platform plugin is not installed.
        """
        env = os.environ.copy()
        env.setdefault("DISPLAY", ":0")

        # Ensure XAUTHORITY is available - systemd services often don't inherit it.
        if "XAUTHORITY" not in env:
            for candidate in [
                os.path.expanduser("~/.Xauthority"),
                "/home/media/.Xauthority",
                "/root/.Xauthority",
            ]:
                if os.path.exists(candidate):
                    env["XAUTHORITY"] = candidate
                    break

        return env

    @staticmethod
    def _linux_vout_flags() -> List[str]:
        """
        Video-output flags for Raspberry Pi / Linux.

        --vout=xcb_x11 : software X11 blitting.  The default GL renderer opens
                         a window but renders nothing on most Pi GPU configs.
        Do NOT add --intf=qt  : if the vlc-plugin-qt package is missing VLC
                                exits immediately - use VLC's auto-detected
                                default interface instead.
        Do NOT add --no-embedded-video : detaches video into a borderless
                                overlay window with no controls toolbar.
        """
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
            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=self._vlc_env(),
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if platform.system() == "Windows" else 0,
            )
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
            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=self._vlc_env(),
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if platform.system() == "Windows" else 0,
            )
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