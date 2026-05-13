"""
Update Service

Checks GitHub for the latest release and applies in-place updates.
Preserves user config, media files, and the virtual environment.
"""

import logging
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
from typing import Dict, Tuple

import requests

logger = logging.getLogger(__name__)

# Project root: two levels up from app/services/
APP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

GITHUB_API_URL = "https://api.github.com/repos/octobarian/jellyfin-offline/releases/latest"
VERSION_FILE = os.path.join(APP_ROOT, "VERSION")
VENV_PIP = os.path.join(APP_ROOT, "venv", "bin", "pip")
SYSTEMD_SERVICE = "rv-media-player"

# Directories/files to overwrite during update — config, media, data, venv, logs, .git are NOT listed here
_UPDATE_DIRS = {"app", "static", "templates", "systemd"}
_UPDATE_FILES = {"requirements.txt", "run.sh", "VERSION"}


# ---------------------------------------------------------------------------
# Version helpers
# ---------------------------------------------------------------------------

def get_current_version() -> str:
    """Read the current version from the VERSION file."""
    try:
        if os.path.exists(VERSION_FILE):
            with open(VERSION_FILE) as fh:
                return fh.read().strip()
    except Exception as exc:
        logger.warning(f"Could not read VERSION file: {exc}")
    return "1.0.0"


def _parse_version(version: str) -> Tuple[int, ...]:
    """Parse a semver string into a comparable tuple, ignoring leading 'v'."""
    version = version.lstrip("v")
    parts = re.sub(r"[^0-9.]", "", version).split(".")
    try:
        return tuple(int(p) for p in parts if p)
    except ValueError:
        return (0,)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_for_updates() -> Dict:
    """
    Query the GitHub releases API and compare with the local version.

    Returns a dict with keys:
        current_version, latest_version, update_available,
        changelog, release_name, release_url, tarball_url, published_at
        (or 'error' on failure).
    """
    current = get_current_version()
    try:
        resp = requests.get(
            GITHUB_API_URL,
            headers={
                "User-Agent": "jellyfin-offline-updater/1.0",
                "Accept": "application/vnd.github.v3+json",
            },
            timeout=15,
        )
        resp.raise_for_status()
        release = resp.json()

        tag = release.get("tag_name", "").lstrip("v")
        latest = tag or current
        update_available = _parse_version(latest) > _parse_version(current)

        return {
            "current_version": current,
            "latest_version": latest,
            "update_available": update_available,
            "changelog": (release.get("body") or "").strip() or "No changelog available.",
            "release_name": release.get("name") or f"v{latest}",
            "release_url": release.get("html_url", ""),
            "tarball_url": release.get("tarball_url", ""),
            "published_at": release.get("published_at", ""),
        }
    except Exception as exc:
        logger.error(f"Failed to check for updates: {exc}")
        return {
            "current_version": current,
            "error": str(exc),
            "update_available": False,
        }


def apply_update(tarball_url: str) -> Dict:
    """
    Download the release tarball, extract it, copy updated files into the
    installation directory, and refresh Python dependencies.

    User config (config/), media (media/), database (data/), logs (logs/),
    and the virtual environment (venv/) are never touched.

    Returns a dict with keys: success, new_version, message  (or 'error').
    """
    tmp_dir = None
    try:
        # 1. Download tarball
        logger.info(f"Downloading update from {tarball_url}")
        tmp_dir = tempfile.mkdtemp(prefix="rv-update-")
        tarball_path = os.path.join(tmp_dir, "release.tar.gz")

        with requests.get(
            tarball_url,
            headers={"User-Agent": "jellyfin-offline-updater/1.0"},
            stream=True,
            timeout=180,
        ) as r:
            r.raise_for_status()
            with open(tarball_path, "wb") as fh:
                for chunk in r.iter_content(chunk_size=65536):
                    fh.write(chunk)
        logger.info("Download complete")

        # 2. Extract
        extract_dir = os.path.join(tmp_dir, "extracted")
        os.makedirs(extract_dir)
        with tarfile.open(tarball_path, "r:gz") as tar:
            tar.extractall(extract_dir)

        # GitHub wraps everything in a single top-level dir
        entries = os.listdir(extract_dir)
        if len(entries) == 1 and os.path.isdir(os.path.join(extract_dir, entries[0])):
            source_dir = os.path.join(extract_dir, entries[0])
        else:
            source_dir = extract_dir
        logger.info(f"Release extracted to {source_dir}")

        # 3. Copy directories
        for name in _UPDATE_DIRS:
            src = os.path.join(source_dir, name)
            dst = os.path.join(APP_ROOT, name)
            if os.path.isdir(src):
                if os.path.exists(dst):
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
                logger.info(f"Updated directory: {name}")

        # 4. Copy files
        for name in _UPDATE_FILES:
            src = os.path.join(source_dir, name)
            dst = os.path.join(APP_ROOT, name)
            if os.path.isfile(src):
                shutil.copy2(src, dst)
                logger.info(f"Updated file: {name}")

        # 5. Refresh Python dependencies
        pip = VENV_PIP if os.path.exists(VENV_PIP) else sys.executable.replace("python", "pip")
        req_file = os.path.join(APP_ROOT, "requirements.txt")
        if os.path.exists(req_file):
            logger.info("Installing updated dependencies…")
            result = subprocess.run(
                [pip, "install", "-q", "-r", req_file],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode != 0:
                logger.warning(f"pip install warnings: {result.stderr[:500]}")
            else:
                logger.info("Dependencies updated successfully")

        new_version = get_current_version()
        logger.info(f"Update complete — now at {new_version}")

        return {
            "success": True,
            "new_version": new_version,
            "message": "Update applied. The service will restart in a few seconds.",
        }

    except Exception as exc:
        logger.error(f"Update failed: {exc}", exc_info=True)
        return {"success": False, "error": str(exc)}
    finally:
        if tmp_dir and os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)


def schedule_restart(delay: float = 3.0) -> None:
    """
    Restart the systemd service in a background thread after *delay* seconds
    so the HTTP response can be delivered to the browser first.
    """
    def _do() -> None:
        import time
        time.sleep(delay)
        _restart_service()

    threading.Thread(target=_do, daemon=True).start()


def _restart_service() -> bool:
    """Try systemctl restart, with and without sudo. Returns True on success."""
    for cmd in (
        ["systemctl", "restart", SYSTEMD_SERVICE],
        ["sudo", "-n", "systemctl", "restart", SYSTEMD_SERVICE],
    ):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            if result.returncode == 0:
                logger.info(f"Service restarted via: {' '.join(cmd)}")
                return True
            logger.warning(f"{' '.join(cmd)} exited {result.returncode}: {result.stderr.strip()}")
        except FileNotFoundError:
            continue
        except Exception as exc:
            logger.warning(f"Restart attempt failed: {exc}")
    logger.warning("Could not restart service automatically — manual restart required")
    return False
