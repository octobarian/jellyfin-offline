"""
Enums for the RV Media Player application.
"""
from enum import Enum


class MediaType(Enum):
    """Enumeration for different types of media content."""
    MOVIE = "movie"
    TV_SHOW = "tv_show"
    EPISODE = "episode"


class MediaAvailability(Enum):
    """Enumeration for media availability status."""
    LOCAL_ONLY = "local_only"
    REMOTE_ONLY = "remote_only"
    BOTH = "both"


class DownloadStatus(Enum):
    """Enumeration for download task status."""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"