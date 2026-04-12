"""
DownloadTask data model for the RV Media Player application.
"""
from dataclasses import dataclass
from typing import Optional
import uuid
from .enums import DownloadStatus


@dataclass
class DownloadTask:
    """
    Represents a media download task.
    
    Attributes:
        task_id: Unique identifier for the download task
        media_id: ID of the media item being downloaded
        status: Current status of the download
        progress: Download progress from 0.0 to 1.0
        file_path: Path where the file will be/is saved (optional)
        error_message: Error message if download failed (optional)
    """
    media_id: str
    status: DownloadStatus = DownloadStatus.PENDING
    progress: float = 0.0
    file_path: Optional[str] = None
    error_message: Optional[str] = None
    task_id: str = None
    
    def __post_init__(self):
        """Initialize task_id if not provided and validate the DownloadTask."""
        if self.task_id is None:
            self.task_id = str(uuid.uuid4())
        self.validate()
    
    def validate(self) -> None:
        """
        Validate the DownloadTask fields.
        
        Raises:
            ValueError: If validation fails
        """
        if not self.task_id or not isinstance(self.task_id, str):
            raise ValueError("DownloadTask task_id must be a non-empty string")
        
        if not self.media_id or not isinstance(self.media_id, str):
            raise ValueError("DownloadTask media_id must be a non-empty string")
        
        if not isinstance(self.status, DownloadStatus):
            raise ValueError("DownloadTask status must be a DownloadStatus enum")
        
        if not isinstance(self.progress, (int, float)):
            raise ValueError("DownloadTask progress must be a number")
        
        if self.progress < 0.0 or self.progress > 1.0:
            raise ValueError("DownloadTask progress must be between 0.0 and 1.0")
        
        if self.file_path is not None and not isinstance(self.file_path, str):
            raise ValueError("DownloadTask file_path must be a string or None")
        
        if self.error_message is not None and not isinstance(self.error_message, str):
            raise ValueError("DownloadTask error_message must be a string or None")
        
        # Validate status-specific constraints
        if self.status == DownloadStatus.COMPLETED and not self.file_path:
            raise ValueError("COMPLETED downloads must have a file_path")
        
        if self.status == DownloadStatus.FAILED and not self.error_message:
            raise ValueError("FAILED downloads must have an error_message")
        
        if self.status == DownloadStatus.COMPLETED and self.progress != 1.0:
            raise ValueError("COMPLETED downloads must have progress = 1.0")
    
    def update_progress(self, progress: float) -> None:
        """
        Update the download progress.
        
        Args:
            progress: New progress value (0.0 to 1.0)
        
        Raises:
            ValueError: If progress is invalid
        """
        if not isinstance(progress, (int, float)):
            raise ValueError("Progress must be a number")
        
        if progress < 0.0 or progress > 1.0:
            raise ValueError("Progress must be between 0.0 and 1.0")
        
        self.progress = float(progress)
        
        # Auto-update status based on progress
        if self.progress == 1.0 and self.status == DownloadStatus.DOWNLOADING:
            self.status = DownloadStatus.COMPLETED
        elif self.progress > 0.0 and self.status == DownloadStatus.PENDING:
            self.status = DownloadStatus.DOWNLOADING
    
    def mark_completed(self, file_path: str) -> None:
        """
        Mark the download as completed.
        
        Args:
            file_path: Path to the completed download file
        
        Raises:
            ValueError: If file_path is invalid
        """
        if not file_path or not isinstance(file_path, str):
            raise ValueError("file_path must be a non-empty string")
        
        self.status = DownloadStatus.COMPLETED
        self.progress = 1.0
        self.file_path = file_path
        self.error_message = None
    
    def mark_failed(self, error_message: str) -> None:
        """
        Mark the download as failed.
        
        Args:
            error_message: Description of the failure
        
        Raises:
            ValueError: If error_message is invalid
        """
        if not error_message or not isinstance(error_message, str):
            raise ValueError("error_message must be a non-empty string")
        
        self.status = DownloadStatus.FAILED
        self.error_message = error_message
    
    def is_active(self) -> bool:
        """Check if the download task is currently active."""
        return self.status in [DownloadStatus.PENDING, DownloadStatus.DOWNLOADING]
    
    def is_finished(self) -> bool:
        """Check if the download task is finished (completed or failed)."""
        return self.status in [DownloadStatus.COMPLETED, DownloadStatus.FAILED]