"""
VLC Controller Service

Handles VLC media player integration for local file playback and streaming.
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
        self.vlc_path: Optional[str] = vlc_path
        self.current_process: Optional[subprocess.Popen] = None
        if vlc_path:
            if not os.path.exists(vlc_path):
                logger.warning(f"Supplied VLC path does not exist: {vlc_path}")
                self.vlc_path = None
        else:
            self._detect_vlc_installation()

    def _detect_vlc_installation(self) -> None:
        """Detect VLC installation and set the path."""
        system = platform.system().lower()

        if system == "windows":
            possible_paths = [
                r"C:\Program Files\VideoLAN\VLC\vlc.exe",
                r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
                os.path.expanduser(r"~\AppData\Local\Programs\VLC\vlc.exe")
            ]
            for path in possible_paths:
                if os.path.exists(path):
                    self.vlc_path = path
                    return
            vlc_in_path = shutil.which("vlc")
            if vlc_in_path:
                self.vlc_path = vlc_in_path

        elif system == "linux":
            possible_paths = ["/usr/bin/vlc", "/usr/local/bin/vlc", "/snap/bin/vlc"]
            for path in possible_paths:
                if os.path.exists(path):
                    self.vlc_path = path
                    return
            vlc_in_path = shutil.which("vlc")
            if vlc_in_path:
                self.vlc_path = vlc_in_path

        elif system == "darwin":
            possible_paths = ["/Applications/VLC.app/Contents/MacOS/VLC"]
            for path in possible_paths:
                if os.path.exists(path):
                    self.vlc_path = path
                    return
            vlc_in_path = shutil.which("vlc")
            if vlc_in_path:
                self.vlc_path = vlc_in_path

    def is_vlc_installed(self) -> bool:
        if self.vlc_path is None:
            return False
        return os.path.exists(self.vlc_path) or shutil.which(os.path.basename(self.vlc_path)) is not None

    def install_vlc(self) -> bool:
        if self.is_vlc_installed():
            return True
        system = platform.system().lower()
        try:
            if system == "linux":
                for cmd in [
                    ["apt-get", "install", "-y", "vlc"],
                    ["pacman", "-S", "--noconfirm", "vlc"],
                    ["dnf", "install", "-y", "vlc"],
                ]:
                    if shutil.which(cmd[0]):
                        result = subprocess.run(cmd, capture_output=True, text=True)
                        if result.returncode == 0:
                            self._detect_vlc_installation()
                            return self.is_vlc_installed()
            elif system == "darwin":
                if shutil.which("brew"):
                    result = subprocess.run(["brew", "install", "--cask", "vlc"],
                                          capture_output=True, text=True)
                    if result.returncode == 0:
                        self._detect_vlc_installation()
                        return self.is_vlc_installed()
        except Exception:
            pass
        return False

    # ── Display environment helpers ────────────────────────────────────────────

    @staticmethod
    def _vlc_env() -> dict:
        """
        Build the subprocess environment for VLC.

        systemd strips DISPLAY, WAYLAND_DISPLAY, and XDG_RUNTIME_DIR from
        service environments.  We detect them from the filesystem so VLC can
        reach the compositor even when launched from a system service running
        as the desktop user.

        NOTE: this does NOT attempt to switch users.  The service must already
        run as the logged-in desktop user (configured by install.sh).  See the
        systemd service file for how that is set up.
        """
        env = os.environ.copy()

        # ── XDG_RUNTIME_DIR ──────────────────────────────────────────────────
        # systemd drops this; detect it from /run/user/<uid> for the current user,
        # then fall back to scanning all /run/user/* dirs for one with a Wayland socket.
        rt = env.get("XDG_RUNTIME_DIR", "")
        if not rt or not os.path.isdir(rt):
            # Current user's runtime dir (works when service User= matches desktop user)
            try:
                uid_dir = f"/run/user/{os.getuid()}"
                if os.path.isdir(uid_dir):
                    rt = uid_dir
            except Exception:
                pass

        if not rt or not os.path.isdir(rt):
            # Scan all /run/user/* — prefer the one with a live Wayland socket
            candidates = sorted(
                glob.glob("/run/user/*/"),
                key=lambda p: os.path.getmtime(p.rstrip("/")),
                reverse=True,
            )
            for candidate in candidates:
                candidate = candidate.rstrip("/")
                has_wayland = any(
                    not f.endswith(".lock")
                    for f in glob.glob(os.path.join(candidate, "wayland-*"))
                )
                if has_wayland:
                    rt = candidate
                    break
            if not rt and candidates:
                rt = candidates[0].rstrip("/")

        if rt:
            env["XDG_RUNTIME_DIR"] = rt

        # ── WAYLAND_DISPLAY ──────────────────────────────────────────────────
        # Detect actual socket name from XDG_RUNTIME_DIR.
        # Pi OS Bookworm uses wayland-0, not wayland-1.
        if not env.get("WAYLAND_DISPLAY") and rt:
            sockets = sorted(
                f for f in glob.glob(os.path.join(rt, "wayland-*"))
                if not f.endswith(".lock")
            )
            if sockets:
                env["WAYLAND_DISPLAY"] = os.path.basename(sockets[0])

        # ── DISPLAY (X11 / XWayland) ─────────────────────────────────────────
        env.setdefault("DISPLAY", ":0")

        # ── XAUTHORITY ───────────────────────────────────────────────────────
        if not env.get("XAUTHORITY"):
            for c in [os.path.expanduser("~/.Xauthority")] + glob.glob("/home/*/.Xauthority"):
                if os.path.exists(c):
                    env["XAUTHORITY"] = c
                    break

        logger.debug(
            "VLC env: DISPLAY=%s WAYLAND_DISPLAY=%s XDG_RUNTIME_DIR=%s XAUTHORITY=%s",
            env.get("DISPLAY"), env.get("WAYLAND_DISPLAY"),
            env.get("XDG_RUNTIME_DIR"), env.get("XAUTHORITY", "<not set>"),
        )
        return env

    @staticmethod
    def _linux_vout_flags() -> List[str]:
        """
        Choose video output plugin for Raspberry Pi / Linux.

        Checks both the inherited process environment AND the filesystem for a
        live Wayland socket — critical when Flask runs as a systemd service
        whose environment has been stripped of session variables.

        Wayland socket found → [] (VLC auto-selects wl/gl output)
        X11 only             → ['--vout=xcb_x11']  (avoids black window on Pi)
        """
        # Fast path: session type set in inherited environment
        if (os.environ.get("WAYLAND_DISPLAY") or
                os.environ.get("XDG_SESSION_TYPE") == "wayland"):
            logger.debug("VLC: Wayland (env) — auto video output")
            return []

        # Slow path: check the filesystem for a live Wayland socket
        search = [f"/run/user/{os.getuid()}"] if os.getuid() != 0 else []
        search += glob.glob("/run/user/*/")
        for rdir in search:
            sockets = [
                f for f in glob.glob(os.path.join(rdir.rstrip("/"), "wayland-*"))
                if not f.endswith(".lock")
            ]
            if sockets:
                logger.debug("VLC: Wayland (socket found at %s) — auto video output", rdir)
                return []

        logger.debug("VLC: X11 — using xcb_x11 output")
        return ["--vout=xcb_x11"]

    def _launch_vlc(self, cmd: List[str]) -> bool:
        """Core launch logic shared by play_local_file and play_stream."""
        env = self._vlc_env()

        # Prepend Linux video-output flags
        if platform.system().lower() == "linux":
            vout = self._linux_vout_flags()
            cmd = [cmd[0]] + vout + cmd[1:]

        logger.info("Launching VLC: %s", " ".join(cmd))

        try:
            startupinfo = None
            if platform.system() == "Windows":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_SHOW

            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                # Pipe stderr so we can log it if VLC exits immediately.
                # VLC rarely writes more than a few KB to stderr during playback,
                # so the 64 KB pipe buffer is safe for long-running processes.
                stderr=subprocess.PIPE,
                env=env,
                creationflags=(
                    subprocess.CREATE_NEW_PROCESS_GROUP
                    if platform.system() == "Windows" else 0
                ),
                startupinfo=startupinfo,
            )

            # On Linux, allow 1.5 s for VLC to connect to the display server
            # (Wayland/X11 connection failures can take ~1 s to surface).
            wait_time = 1.5 if platform.system().lower() == "linux" else 0.4
            time.sleep(wait_time)

            if self.current_process.poll() is not None:
                stderr_out = b""
                try:
                    stderr_out = self.current_process.stderr.read()
                except Exception:
                    pass
                logger.error(
                    "VLC exited immediately (code=%d). Stderr: %s",
                    self.current_process.returncode,
                    stderr_out.decode("utf-8", errors="replace").strip()[:800],
                )
                return False

            return True

        except Exception as e:
            logger.error("Failed to launch VLC: %s", e)
            return False

    # ── Public playback API ────────────────────────────────────────────────────

    def play_local_file(self, file_path: str, fullscreen: bool = False,
                        title: Optional[str] = None) -> bool:
        """Play a local media file using VLC."""
        if not self.is_vlc_installed():
            logger.error("VLC not installed")
            return False
        if not os.path.exists(file_path):
            logger.error("File not found: %s", file_path)
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
        """Play a streaming URL using VLC."""
        if not self.is_vlc_installed():
            logger.error("VLC not installed")
            return False

        self.stop_playback()

        cmd = [self.vlc_path]
        if fullscreen:
            cmd.append("--fullscreen")
        if title:
            cmd.extend(["--meta-title", title])
        cmd.extend(["--play-and-exit", "--network-caching", "3000"])
        cmd.append(stream_url)

        return self._launch_vlc(cmd)

    def stop_playback(self) -> bool:
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
        if self.current_process is None:
            return False
        return self.current_process.poll() is None

    def get_vlc_version(self) -> Optional[str]:
        if not self.is_vlc_installed():
            return None
        try:
            result = subprocess.run(
                [self.vlc_path, "--version"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'VLC media player' in line:
                        return line.strip()
        except Exception:
            pass
        return None

    def get_supported_formats(self) -> List[str]:
        return [
            '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm',
            '.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma',
            '.m4v', '.3gp', '.asf', '.rm', '.rmvb', '.vob',
            '.ts', '.m2ts', '.mts', '.divx', '.xvid'
        ]

    def cleanup(self) -> None:
        self.stop_playback()
