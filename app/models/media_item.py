"""
MediaItem data model for the RV Media Player application.
"""
import os
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from .enums import MediaType, MediaAvailability


@dataclass
class MediaItem:
    """
    Represents a media item that can be either local or remote.
    
    Attributes:
        id: Unique identifier for the media item
        title: Display title of the media
        type: Type of media (movie, tv_show, episode)
        year: Release year (optional)
        duration: Duration in seconds (optional)
        thumbnail_url: URL to thumbnail image (optional)
        cached_thumbnail_path: Path to locally cached thumbnail (optional)
        local_path: Path to local file if available (optional)
        jellyfin_id: Jellyfin server ID if available (optional)
        availability: Where the media is available (local, remote, both)
        metadata: Additional metadata dictionary
        file_validated: Whether local file existence was validated
        validation_timestamp: When validation was performed (Unix timestamp)
    """
    id: str
    title: str
    type: MediaType
    availability: MediaAvailability
    year: Optional[int] = None
    duration: Optional[int] = None
    thumbnail_url: Optional[str] = None
    cached_thumbnail_path: Optional[str] = None
    local_path: Optional[str] = None
    jellyfin_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    file_validated: bool = False
    validation_timestamp: float = 0.0
    
    def __post_init__(self):
        """Validate the MediaItem after initialization."""
        self.validate()
    
    def validate(self) -> None:
        """
        Validate the MediaItem fields.
        
        Raises:
            ValueError: If validation fails
        """
        if not self.id or not isinstance(self.id, str):
            raise ValueError("MediaItem id must be a non-empty string")
        
        if not self.title or not isinstance(self.title, str):
            raise ValueError("MediaItem title must be a non-empty string")
        
        if not isinstance(self.type, MediaType):
            raise ValueError("MediaItem type must be a MediaType enum")
        
        if not isinstance(self.availability, MediaAvailability):
            raise ValueError("MediaItem availability must be a MediaAvailability enum")
        
        if self.year is not None and (not isinstance(self.year, int) or self.year < 1800 or self.year > 2100):
            raise ValueError("MediaItem year must be an integer between 1800 and 2100")
        
        if self.duration is not None and (not isinstance(self.duration, int) or self.duration < 0):
            raise ValueError("MediaItem duration must be a non-negative integer")
        
        if self.thumbnail_url is not None and not isinstance(self.thumbnail_url, str):
            raise ValueError("MediaItem thumbnail_url must be a string")
        
        if self.local_path is not None and not isinstance(self.local_path, str):
            raise ValueError("MediaItem local_path must be a string")
        
        if self.jellyfin_id is not None and not isinstance(self.jellyfin_id, str):
            raise ValueError("MediaItem jellyfin_id must be a string")
        
        if not isinstance(self.metadata, dict):
            raise ValueError("MediaItem metadata must be a dictionary")
        
        if not isinstance(self.file_validated, bool):
            raise ValueError("MediaItem file_validated must be a boolean")
        
        if not isinstance(self.validation_timestamp, (int, float)) or self.validation_timestamp < 0:
            raise ValueError("MediaItem validation_timestamp must be a non-negative number")
        
        # Validate availability consistency
        if self.availability == MediaAvailability.LOCAL_ONLY and not self.local_path:
            raise ValueError("LOCAL_ONLY media must have a local_path")
        
        if self.availability == MediaAvailability.REMOTE_ONLY and not self.jellyfin_id:
            raise ValueError("REMOTE_ONLY media must have a jellyfin_id")
        
        if self.availability == MediaAvailability.BOTH and (not self.local_path or not self.jellyfin_id):
            raise ValueError("BOTH availability media must have both local_path and jellyfin_id")
    
    def _validate_local_file(self) -> bool:
        """
        Validate that the local file exists on disk.
        
        Returns:
            bool: True if file exists and is accessible, False otherwise
        """
        if not self.local_path:
            self.file_validated = False
            self.validation_timestamp = time.time()
            return False
        
        try:
            file_exists = os.path.isfile(self.local_path) and os.access(self.local_path, os.R_OK)
            self.file_validated = file_exists
            self.validation_timestamp = time.time()
            return file_exists
        except (OSError, IOError):
            # Handle permission errors, network drive issues, etc.
            self.file_validated = False
            self.validation_timestamp = time.time()
            return False
    
    def is_local_available(self) -> bool:
        """
        Check if media is available locally with validation.
        
        Returns:
            bool: True if media has local availability and file exists (if validated)
        """
        # Check if media has local availability
        has_local_availability = self.availability in [MediaAvailability.LOCAL_ONLY, MediaAvailability.BOTH]
        
        if not has_local_availability:
            return False
        
        # If file hasn't been validated or validation is stale (older than 5 minutes), validate now
        current_time = time.time()
        validation_age = current_time - self.validation_timestamp
        validation_stale = validation_age > 300  # 5 minutes
        
        if not self.file_validated or validation_stale:
            return self._validate_local_file()
        
        return self.file_validated
    
    def is_remote_available(self) -> bool:
        """Check if media is available remotely."""
        return self.availability in [MediaAvailability.REMOTE_ONLY, MediaAvailability.BOTH]
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert MediaItem to dictionary for serialization.
        
        Returns:
            Dict[str, Any]: Dictionary representation including validation status
        """
        return {
            'id': self.id,
            'title': self.title,
            'type': self.type.value,
            'availability': self.availability.value,
            'year': self.year,
            'duration': self.duration,
            'thumbnail_url': self.thumbnail_url,
            'cached_thumbnail_path': self.cached_thumbnail_path,
            'local_path': self.local_path,
            'jellyfin_id': self.jellyfin_id,
            'metadata': self.metadata,
            'file_validated': self.file_validated,
            'validation_timestamp': self.validation_timestamp,
            'is_local_available': self.is_local_available(),
            'is_remote_available': self.is_remote_available()
        }