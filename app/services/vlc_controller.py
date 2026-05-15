"""
VLC Controller Service

Handles VLC media player integration for local file playback and streaming.
Provides methods for launching VLC processes, managing playback, and detecting VLC installation.
"""

import glob
import logging
import os
import shlex
import subprocess
import platform
import shutil
import time
from typing import Optional, List, Tuple
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

    # ── Display / session helpers ──────────────────────────────────────────────

    @staticmethod
    def _find_graphical_session() -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Use loginctl to find the logged-in user who owns a graphical desktop
        session (X11 or Wayland).

        Returns (username, uid_str, session_type) or (None, None, None).
        """
        try:
            sessions = subprocess.run(
                ["loginctl", "list-sessions", "--no-legend"],
                capture_output=True, text=True, timeout=5
            )
            for line in sessions.stdout.splitlines():
                parts = line.split()
                if len(parts) < 3:
                    continue
                session_id, uid_str, user = parts[0], parts[1], parts[2]
                try:
                    props = subprocess.run(
                        ["loginctl", "show-session", session_id,
                         "--property=Type", "--property=State"],
                        capture_output=True, text=True, timeout=5
                    )
                    prop_map = dict(
                        p.split("=", 1) for p in props.stdout.splitlines() if "=" in p
                    )
                    session_type = prop_map.get("Type", "")
                    state = prop_map.get("State", "")
                    if session_type in ("x11", "wayland") and state in ("active", "online"):
                        logger.debug(
                            f"VLC: graphical session found — user={user} "
                            f"uid={uid_str} type={session_type}"
                        )
                        return user, uid_str, session_type
                except Exception:
                    continue
        except Exception:
            pass
        return None, None, None

    @staticmethod
    def _vlc_env(runtime_dir: Optional[str] = None,
                 wayland_display: Optional[str] = None) -> dict:
        """
        Build the environment for the VLC subprocess.

        When the server runs as a systemd service user (e.g. 'media') it has no
        DISPLAY, WAYLAND_DISPLAY, or XDG_RUNTIME_DIR.  We detect the active
        graphical session's runtime directory from the filesystem so VLC can
        reach the compositor.
        """
        env = os.environ.copy()

        # ── XDG_RUNTIME_DIR ──────────────────────────────────────────────────
        # Prefer caller-supplied value (from loginctl detection), then inherited
        # env, then filesystem search.
        if runtime_dir and os.path.isdir(runtime_dir):
            env["XDG_RUNTIME_DIR"] = runtime_dir
        elif not env.get("XDG_RUNTIME_DIR") or not os.path.isdir(env.get("XDG_RUNTIME_DIR", "")):
            # Search /run/user/* for the directory that has a Wayland socket
            # (meaning a compositor is running for that user).
            candidates = sorted(
                glob.glob("/run/user/*/"),
                key=lambda p: os.path.getmtime(p.rstrip("/")),
                reverse=True,
            )
            found = None
            for candidate in candidates:
                candidate = candidate.rstrip("/")
                wayland_sockets = [
                    f for f in glob.glob(os.path.join(candidate, "wayland-*"))
                    if not f.endswith(".lock")
                ]
                if wayland_sockets:
                    found = candidate
                    break
            if not found:
                # Fall back to any existing /run/user/ dir (X11 session)
                for candidate in candidates:
                    candidate = candidate.rstrip("/")
                    if os.path.isdir(candidate):
                        found = candidate
                        break
            if not found:
                # Last resort: current process UID
                try:
                    uid = os.getuid()
                    fallback = f"/run/user/{uid}"
                    if os.path.isdir(fallback):
                        found = fallback
                except Exception:
                    pass
            if found:
                env["XDG_RUNTIME_DIR"] = found

        # ── WAYLAND_DISPLAY ──────────────────────────────────────────────────
        # Detect the actual socket name from XDG_RUNTIME_DIR rather than
        # hard-coding 'wayland-1' (Pi OS Bookworm uses 'wayland-0').
        if wayland_display:
            env["WAYLAND_DISPLAY"] = wayland_display
        elif not env.get("WAYLAND_DISPLAY"):
            rt = env.get("XDG_RUNTIME_DIR", "")
            if rt:
                sockets = sorted([
                    f for f in glob.glob(os.path.join(rt, "wayland-*"))
                    if not f.endswith(".lock")
                ])
                if sockets:
                    env["WAYLAND_DISPLAY"] = os.path.basename(sockets[0])

        # ── DISPLAY (X11 / XWayland) ─────────────────────────────────────────
        env.setdefault("DISPLAY", ":0")

        # ── XAUTHORITY ───────────────────────────────────────────────────────
        if not env.get("XAUTHORITY"):
            candidates = [os.path.expanduser("~/.Xauthority")]
            candidates.extend(glob.glob("/home/*/.Xauthority"))
            candidates.append("/root/.Xauthority")
            for c in candidates:
                if os.path.exists(c):
                    env["XAUTHORITY"] = c
                    break

        logger.debug(
            f"VLC env: DISPLAY={env.get('DISPLAY')} "
            f"WAYLAND_DISPLAY={env.get('WAYLAND_DISPLAY')} "
            f"XDG_RUNTIME_DIR={env.get('XDG_RUNTIME_DIR')} "
            f"XAUTHORITY={env.get('XAUTHORITY', '<not set>')}"
        )
        return env

    @staticmethod
    def _linux_vout_flags(runtime_dir: Optional[str] = None) -> List[str]:
        """
        Video-output flags for Raspberry Pi / Linux.

        Checks both the inherited process environment AND the actual filesystem
        for Wayland sockets — critical when Flask runs as a systemd service
        whose environment has been stripped of session variables.

        - Wayland detected → return [] (let VLC auto-select wl or gl output)
        - X11 only         → return ['--vout=xcb_x11']  (avoids black window on Pi)
        """
        # Check Flask process env first (works for terminal launches)
        is_wayland = (
            bool(os.environ.get("WAYLAND_DISPLAY")) or
            os.environ.get("XDG_SESSION_TYPE") == "wayland"
        )

        # Also probe the filesystem — catches systemd service with stripped env
        if not is_wayland:
            search_dirs = []
            if runtime_dir:
                search_dirs.append(runtime_dir)
            search_dirs.extend(glob.glob("/run/user/*/"))

            for rdir in search_dirs:
                sockets = [
                    f for f in glob.glob(os.path.join(rdir.rstrip("/"), "wayland-*"))
                    if not f.endswith(".lock")
                ]
                if sockets:
                    is_wayland = True
                    break

        if is_wayland:
            logger.debug("VLC: Wayland session detected — auto-detecting video output")
            return []

        logger.debug("VLC: X11 session — using xcb_x11 output")
        return ["--vout=xcb_x11"]

    def _build_cmd(self, base_cmd: List[str], current_user: str,
                   display_user: Optional[str]) -> List[str]:
        """
        If we're running as a service user that differs from the desktop user,
        wrap the VLC command in 'su' so it runs under the display owner's account.

        This handles the common Pi setup where the web service runs as a
        dedicated user (e.g. 'media') but the Wayland/X11 session belongs to
        the logged-in desktop user (e.g. 'riley').

        Requires that the service user can run 'su <display_user> -c ...'
        without a password, typically via a sudoers NOPASSWD rule or by running
        the service as root.
        """
        if not display_user or display_user == current_user:
            return base_cmd

        # Build an inline env string so the sub-shell gets display variables
        env = self._vlc_env()
        display_env_pairs = []
        for key in ("DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "XAUTHORITY"):
            val = env.get(key, "")
            if val:
                display_env_pairs.append(f"{key}={shlex.quote(val)}")

        vlc_cmd_str = " ".join(shlex.quote(c) for c in base_cmd)
        full_cmd_str = " ".join(display_env_pairs + [vlc_cmd_str])

        logger.info(
            f"VLC: running as '{display_user}' (service user is '{current_user}')"
        )
        return ["su", display_user, "-c", full_cmd_str]

    def _launch_vlc(self, cmd: List[str]) -> bool:
        """
        Core VLC launch logic shared by play_local_file and play_stream.

        Handles display user detection, environment setup, and stderr capture
        for diagnostics on immediate exit.
        """
        # ── Detect who owns the graphical session ────────────────────────────
        display_user, display_uid_str, session_type = None, None, None
        runtime_dir_override = None

        if platform.system().lower() == "linux":
            display_user, display_uid_str, session_type = self._find_graphical_session()
            if display_uid_str:
                candidate = f"/run/user/{display_uid_str}"
                if os.path.isdir(candidate):
                    runtime_dir_override = candidate

        # ── Video output flags (Linux only) ──────────────────────────────────
        if platform.system().lower() == "linux":
            vout = self._linux_vout_flags(runtime_dir=runtime_dir_override)
            # Insert vout flags right after the vlc binary (index 0)
            cmd = [cmd[0]] + vout + cmd[1:]

        # ── Wrap in su if service user ≠ display user ────────────────────────
        import pwd
        try:
            current_user = pwd.getpwuid(os.getuid()).pw_name
        except Exception:
            current_user = str(os.getuid())

        final_cmd = self._build_cmd(cmd, current_user, display_user)

        env = self._vlc_env(
            runtime_dir=runtime_dir_override,
            wayland_display=None,  # auto-detect from runtime dir
        )

        logger.info(f"Launching VLC: {' '.join(final_cmd)}")

        try:
            startupinfo = None
            if platform.system() == "Windows":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_SHOW

            self.current_process = subprocess.Popen(
                final_cmd,
                stdout=subprocess.DEVNULL,
                # Capture stderr so we can log it if VLC exits immediately.
                # VLC writes only a few KB at startup; the 64 KB pipe buffer
                # is ample for normal playback.
                stderr=subprocess.PIPE,
                env=env,
                creationflags=(
                    subprocess.CREATE_NEW_PROCESS_GROUP
                    if platform.system() == "Windows" else 0
                ),
                startupinfo=startupinfo,
            )

            # Give VLC time to connect to the display.  Use 1.5 s on Linux
            # because Wayland connection failures can take up to ~1 s to surface.
            wait_time = 1.5 if platform.system().lower() == "linux" else 0.4
            time.sleep(wait_time)

            if self.current_process.poll() is not None:
                # VLC exited — read stderr for a useful error message
                stderr_out = b""
                try:
                    stderr_out = self.current_process.stderr.read()
                except Exception:
                    pass
                logger.error(
                    f"VLC exited immediately (code={self.current_process.returncode}). "
                    f"Stderr: {stderr_out.decode('utf-8', errors='replace').strip()[:800]}"
                )
                return False

            return True

        except Exception as e:
            logger.error(f"Failed to launch VLC: {e}")
            return False

    def play_local_file(self, file_path: str, fullscreen: bool = False,
                        title: Optional[str] = None) -> bool:
        """
        Play a local media file using VLC.

        Args:
            file_path: Path to the local media file
            fullscreen: Whether to start VLC in fullscreen mode
            title: Window/playlist title shown in VLC

        Returns:
            True if VLC was launched successfully, False otherwise
        """
        if not self.is_vlc_installed():
            logger.error("VLC not installed")
            return False

        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return False

        self.stop_playback()

        cmd = [self.vlc_path]
        if fullscreen:
            cmd.append("--fullscreen")
        if title:
            cmd.extend(["--meta-title", title])
        cmd.append("--play-and-exit")
        cmd.append(file_path)

        return self._launch_vlc(cmd)

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
            logger.error("VLC not installed")
            return False

        self.stop_playback()

        cmd = [self.vlc_path]
        if fullscreen:
            cmd.append("--fullscreen")
        if title:
            cmd.extend(["--meta-title", title])
        cmd.extend([
            "--play-and-exit",
            "--network-caching", "3000",
        ])
        cmd.append(stream_url)

        return self._launch_vlc(cmd)

    def stop_playback(self) -> bool:
        """
        Stop the current VLC playback.

        Returns:
            True if playback was stopped successfully, False otherwise
        """
        if self.current_process is None:
            return True

        try:
            self.current_process.terminate()

            try:
                self.current_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.current_process.kill()
                self.current_process.wait()

            self.current_process = None
            return True

        except Exception:
            return False

    def is_playing(self) -> bool:
        """Check if VLC is currently playing."""
        if self.current_process is None:
            return False
        return self.current_process.poll() is None

    def get_vlc_version(self) -> Optional[str]:
        """Get the version of the installed VLC."""
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
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'VLC media player' in line:
                        return line.strip()

        except Exception:
            pass

        return None

    def get_supported_formats(self) -> List[str]:
        """Get list of supported media formats."""
        return [
            '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm',
            '.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma',
            '.m4v', '.3gp', '.asf', '.rm', '.rmvb', '.vob',
            '.ts', '.m2ts', '.mts', '.divx', '.xvid'
        ]

    def cleanup(self) -> None:
        """Clean up resources and stop any running processes."""
        self.stop_playback()
