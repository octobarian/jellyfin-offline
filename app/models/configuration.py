"""
Configuration data model for the RV Media Player application.
"""
from dataclasses import dataclass, field
from typing import List, Optional
import os
from urllib.parse import urlparse


@dataclass
class Configuration:
    """
    Configuration settings for the RV Media Player application.
    
    Attributes:
        jellyfin_server_url: URL of the Jellyfin server
        jellyfin_username: Username for Jellyfin authentication
        jellyfin_api_key: API key for Jellyfin authentication
        local_media_paths: List of paths to scan for local media
        download_directory: Directory for downloaded media files
        vlc_path: Path to VLC executable (optional, auto-detected if None)
        auto_launch: Whether to auto-launch on system startup
        fullscreen_browser: Whether to launch browser in fullscreen mode
    """
    jellyfin_server_url: str
    jellyfin_username: str
    jellyfin_api_key: str
    local_media_paths: List[str]
    download_directory: str
    vlc_path: Optional[str] = None
    auto_launch: bool = True
    fullscreen_browser: bool = True
    
    def __post_init__(self):
        """Validate the Configuration after initialization."""
        self.validate()
    
    def validate(self) -> None:
        """
        Validate the Configuration fields.
        
        Raises:
            ValueError: If validation fails
        """
        # Validate Jellyfin server URL
        if not self.jellyfin_server_url or not isinstance(self.jellyfin_server_url, str):
            raise ValueError("jellyfin_server_url must be a non-empty string")
        
        parsed_url = urlparse(self.jellyfin_server_url)
        if not parsed_url.scheme or not parsed_url.netloc:
            raise ValueError("jellyfin_server_url must be a valid URL with scheme and netloc")
        
        if parsed_url.scheme not in ['http', 'https']:
            raise ValueError("jellyfin_server_url must use http or https scheme")
        
        # Validate Jellyfin credentials
        if not self.jellyfin_username or not isinstance(self.jellyfin_username, str):
            raise ValueError("jellyfin_username must be a non-empty string")
        
        if not self.jellyfin_api_key or not isinstance(self.jellyfin_api_key, str):
            raise ValueError("jellyfin_api_key must be a non-empty string")
        
        # Validate local media paths
        if not isinstance(self.local_media_paths, list):
            raise ValueError("local_media_paths must be a list")
        
        if not self.local_media_paths:
            raise ValueError("local_media_paths must contain at least one path")
        
        for path in self.local_media_paths:
            if not isinstance(path, str) or not path:
                raise ValueError("All local_media_paths must be non-empty strings")
        
        # Validate download directory
        if not self.download_directory or not isinstance(self.download_directory, str):
            raise ValueError("download_directory must be a non-empty string")
        
        # Validate VLC path if provided
        if self.vlc_path is not None and not isinstance(self.vlc_path, str):
            raise ValueError("vlc_path must be a string or None")
        
        # Validate boolean fields
        if not isinstance(self.auto_launch, bool):
            raise ValueError("auto_launch must be a boolean")
        
        if not isinstance(self.fullscreen_browser, bool):
            raise ValueError("fullscreen_browser must be a boolean")
    
    def validate_paths_exist(self) -> List[str]:
        """
        Validate that configured paths exist on the filesystem.
        
        Returns:
            List of validation errors (empty if all paths exist)
        """
        errors = []
        
        # Check local media paths
        for path in self.local_media_paths:
            if not os.path.exists(path):
                errors.append(f"Local media path does not exist: {path}")
            elif not os.path.isdir(path):
                errors.append(f"Local media path is not a directory: {path}")
        
        # Check download directory
        if not os.path.exists(self.download_directory):
            errors.append(f"Download directory does not exist: {self.download_directory}")
        elif not os.path.isdir(self.download_directory):
            errors.append(f"Download directory is not a directory: {self.download_directory}")
        
        # Check VLC path if provided
        if self.vlc_path and not os.path.exists(self.vlc_path):
            errors.append(f"VLC path does not exist: {self.vlc_path}")
        
        return errors
    
    def create_directories(self) -> None:
        """
        Create configured directories if they don't exist.
        
        Raises:
            OSError: If directory creation fails
        """
        # Create local media directories
        for path in self.local_media_paths:
            os.makedirs(path, exist_ok=True)
        
        # Create download directory
        os.makedirs(self.download_directory, exist_ok=True)