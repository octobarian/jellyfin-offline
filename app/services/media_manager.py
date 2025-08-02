"""
Media Manager Service

Orchestrates interactions between local and remote media services.
Provides unified media list generation, deduplication, availability detection,
and download queue management.
"""
import logging
import threading
from typing import List, Optional, Dict, Any, Set, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from .local_media_service import LocalMediaService
from .jellyfin_service import JellyfinService
from .vlc_controller import VLCController
from ..models.media_item import MediaItem
from ..models.download_task import DownloadTask
from ..models.enums import MediaType, MediaAvailability, DownloadStatus


@dataclass
class MediaComparison:
    """Result of comparing local and remote media items."""
    local_only: List[MediaItem]
    remote_only: List[MediaItem]
    both_available: List[MediaItem]
    total_local: int
    total_remote: int
    total_unified: int


class MediaManager:
    """
    Orchestrates media operations between local storage and Jellyfin server.
    
    Provides unified media list generation with deduplication, availability detection,
    download queue management, and media comparison functionality.
    """
    
    def __init__(self, 
                 local_service: LocalMediaService,
                 jellyfin_service: JellyfinService,
                 vlc_controller: VLCController):
        """
        Initialize the MediaManager.
        
        Args:
            local_service: LocalMediaService instance
            jellyfin_service: JellyfinService instance
            vlc_controller: VLCController instance
        """
        self.local_service = local_service
        self.jellyfin_service = jellyfin_service
        self.vlc_controller = vlc_controller
        self.logger = logging.getLogger(__name__)
        
        # Cache for unified media list
        self._unified_media_cache: List[MediaItem] = []
        self._cache_timestamp: float = 0
        self._cache_ttl: float = 300  # 5 minutes
        self._cache_lock = threading.RLock()
        
        # Separate caches for local and remote media
        self._local_media_cache: List[MediaItem] = []
        self._local_cache_timestamp: float = 0
        self._remote_media_cache: List[MediaItem] = []
        self._remote_cache_timestamp: float = 0
        
        # Image cache
        self._image_cache: Dict[str, str] = {}  # URL -> local path
        self._image_cache_lock = threading.RLock()
        
        # Download queue management
        self._download_queue: Dict[str, DownloadTask] = {}
        self._download_lock = threading.RLock()
        self._max_concurrent_downloads = 3
        self._download_executor = ThreadPoolExecutor(max_workers=self._max_concurrent_downloads)
        
        # Media comparison cache
        self._comparison_cache: Optional[MediaComparison] = None
        self._comparison_timestamp: float = 0
        
        # Flag to control Jellyfin sync behavior
        self._jellyfin_sync_requested: bool = False
    
    def get_local_media_with_validation(self, force_validation: bool = False) -> Tuple[List[MediaItem], Dict[str, Any]]:
        """
        Get local media items with file existence validation.
        
        Args:
            force_validation: Force re-validation of all files
            
        Returns:
            Tuple of (List of MediaItem objects with validated local availability, validation metadata dict)
        """
        self.logger.info(f"Getting local media with validation (force_validation={force_validation})")
        
        current_time = time.time()
        
        # Check if we can use cached data (unless forcing validation)
        if (not force_validation and 
            self._local_media_cache and 
            current_time - self._local_cache_timestamp < self._cache_ttl):
            self.logger.debug("Returning cached local media list")
            validation_metadata = {
                'validation_timestamp': self._local_cache_timestamp,
                'missing_files_count': 0  # Cached data assumed valid
            }
            return self._local_media_cache.copy(), validation_metadata
        
        try:
            # Get local media items
            local_media_items = self.local_service.get_local_media()
            
            # Always validate file existence for this method
            validated_items = self.local_service.validate_file_existence(local_media_items)
            
            # Convert to MediaItem objects
            media_items = self.local_service.to_media_items(validated_items)
            
            # Update cache
            self._local_media_cache = media_items
            self._local_cache_timestamp = current_time
            
            total_items = len(local_media_items)
            validated_items_count = len(validated_items)
            missing_files_count = total_items - validated_items_count
            
            self.logger.info(f"Local media validation complete: {validated_items_count}/{total_items} files exist")
            
            # Create validation metadata
            validation_metadata = {
                'validation_timestamp': current_time,
                'missing_files_count': missing_files_count,
                'total_files_count': total_items,
                'validated_files_count': validated_items_count
            }
            
            return media_items.copy(), validation_metadata
            
        except Exception as e:
            self.logger.error(f"Error getting local media with validation: {e}")
            # Return cached data if available, even if expired
            if self._local_media_cache:
                self.logger.warning("Returning expired cached local media due to error")
                validation_metadata = {
                    'validation_timestamp': self._local_cache_timestamp,
                    'missing_files_count': 0,  # Unknown for cached data
                    'error': str(e)
                }
                return self._local_media_cache.copy(), validation_metadata
            
            # Return empty list with error metadata
            validation_metadata = {
                'validation_timestamp': current_time,
                'missing_files_count': 0,
                'total_files_count': 0,
                'validated_files_count': 0,
                'error': str(e)
            }
            return [], validation_metadata

    def get_remote_media_only(self, force_refresh: bool = False) -> List[MediaItem]:
        """
        Get only remote media items from Jellyfin.
        
        Args:
            force_refresh: Force refresh of cached data
            
        Returns:
            List of MediaItem objects with remote availability
        """
        self.logger.info(f"Getting remote media only (force_refresh={force_refresh})")
        
        current_time = time.time()
        
        # Return cached data if still valid and not forcing refresh
        if (not force_refresh and 
            self._remote_media_cache and 
            current_time - self._remote_cache_timestamp < self._cache_ttl):
            self.logger.debug("Returning cached remote media list")
            return self._remote_media_cache.copy()
        
        try:
            self.logger.info("Loading remote media from Jellyfin")
            media_items, metadata = self.jellyfin_service.get_media_library()
            
            # Log retrieval metadata
            if metadata.get('errors'):
                self.logger.warning(f"Jellyfin retrieval had errors: {metadata['errors']}")
            if metadata.get('warnings'):
                self.logger.info(f"Jellyfin retrieval warnings: {metadata['warnings']}")
            if metadata.get('partial_success'):
                self.logger.warning("Jellyfin retrieval completed with partial success")
            
            self.logger.info(f"Retrieved {len(media_items)} remote media items in {metadata.get('retrieval_time_ms', 0):.1f}ms")
            self.logger.debug(f"Jellyfin retrieval metadata: {metadata}")
            
            # Update cache
            self._remote_media_cache = media_items
            self._remote_cache_timestamp = current_time
            
            return media_items.copy()
            
        except Exception as e:
            self.logger.error(f"Error getting remote media only: {e}")
            # Return cached data if available, even if expired
            if self._remote_media_cache:
                self.logger.warning("Returning expired cached remote media due to error")
                return self._remote_media_cache.copy()
            return []

    def get_unified_media_list(self, force_refresh: bool = False) -> List[MediaItem]:
        """
        Get unified media list from both local and remote sources with deduplication.
        Uses the new progressive loading methods for better performance and validation.
        
        Args:
            force_refresh: Force refresh of cached data
            
        Returns:
            List of MediaItem objects with availability status
        """
        with self._cache_lock:
            current_time = time.time()
            
            # Return cached data if still valid and not forcing refresh
            if (not force_refresh and 
                self._unified_media_cache is not None and 
                current_time - self._cache_timestamp < self._cache_ttl):
                self.logger.debug("Returning cached unified media list")
                return self._unified_media_cache.copy()
            
            self.logger.info("Generating unified media list using progressive loading methods")
            
            # Use the new progressive loading methods
            local_media, _ = self.get_local_media_with_validation(force_refresh)
            
            # Only get remote media if explicitly requested or on initial load
            remote_media = []
            if force_refresh or self._jellyfin_sync_requested or not self._remote_media_cache:
                self.logger.info("Loading remote media using get_remote_media_only")
                remote_media = self.get_remote_media_only(force_refresh)
                self._jellyfin_sync_requested = False  # Reset the flag after sync
            else:
                self.logger.info("Using cached remote media (Jellyfin sync not requested)")
                remote_media = self._remote_media_cache.copy()
            
            # Merge and deduplicate
            unified_media = self._merge_and_deduplicate(local_media, remote_media)
            
            # Update cache
            self._unified_media_cache = unified_media
            self._cache_timestamp = current_time
            
            self.logger.info(f"Generated unified media list with {len(unified_media)} items " +
                           f"({len(local_media)} local, {len(remote_media)} remote)")
            return unified_media.copy()
    
    def get_media_details(self, media_id: str) -> Optional[MediaItem]:
        """
        Get detailed information for a specific media item.
        
        Args:
            media_id: Unique media item identifier
            
        Returns:
            MediaItem object or None if not found
        """
        unified_media = self.get_unified_media_list()
        
        for media_item in unified_media:
            if media_item.id == media_id:
                return media_item
        
        self.logger.warning(f"Media item not found: {media_id}")
        return None
    
    def play_local_media(self, media_id: str, fullscreen: bool = False) -> bool:
        """
        Play local media using VLC.
        
        Args:
            media_id: Media item identifier
            fullscreen: Whether to play in fullscreen mode
            
        Returns:
            True if playback started successfully, False otherwise
        """
        media_item = self.get_media_details(media_id)
        if not media_item:
            self.logger.error(f"Media item not found: {media_id}")
            return False
        
        if not media_item.is_local_available():
            self.logger.error(f"Media not available locally: {media_id}")
            return False
        
        if not media_item.local_path:
            self.logger.error(f"No local path for media: {media_id}")
            return False
        
        self.logger.info(f"Starting local playback: {media_item.title}")
        return self.vlc_controller.play_local_file(media_item.local_path, fullscreen)
    
    def stream_media(self, media_id: str, fullscreen: bool = False) -> bool:
        """
        Stream media from Jellyfin server using VLC.
        
        Args:
            media_id: Media item identifier
            fullscreen: Whether to play in fullscreen mode
            
        Returns:
            True if streaming started successfully, False otherwise
        """
        media_item = self.get_media_details(media_id)
        if not media_item:
            self.logger.error(f"Media item not found: {media_id}")
            return False
        
        if not media_item.is_remote_available():
            self.logger.error(f"Media not available remotely: {media_id}")
            return False
        
        if not media_item.jellyfin_id:
            self.logger.error(f"No Jellyfin ID for media: {media_id}")
            return False
        
        # Get streaming URL from Jellyfin service
        stream_url = self.jellyfin_service.get_streaming_url(media_item.jellyfin_id)
        if not stream_url:
            self.logger.error(f"Failed to get streaming URL for: {media_id}")
            return False
        
        self.logger.info(f"Starting stream playback: {media_item.title}")
        return self.vlc_controller.play_stream(stream_url, fullscreen)
    
    def download_media(self, media_id: str, destination_dir: str = None, final_destination: str = None) -> Optional[DownloadTask]:
        """
        Download media from Jellyfin server to local storage.
        
        Args:
            media_id: Media item identifier
            destination_dir: Directory to download to (optional, defaults to downloads directory)
            final_destination: Final destination directory to move file to after download (optional)
            
        Returns:
            DownloadTask object for tracking progress or None if failed
        """
        media_item = self.get_media_details(media_id)
        if not media_item:
            self.logger.error(f"Media item not found: {media_id}")
            return None
        
        if not media_item.is_remote_available():
            self.logger.error(f"Media not available for download: {media_id}")
            return None
        
        if not media_item.jellyfin_id:
            self.logger.error(f"No Jellyfin ID for media: {media_id}")
            return None
        
        # Check if already downloading
        with self._download_lock:
            for task in self._download_queue.values():
                if task.media_id == media_id and task.is_active():
                    self.logger.info(f"Media already downloading: {media_id}")
                    return task
        
        # Determine destination path
        if not destination_dir:
            destination_dir = "media/downloads"
        
        import os
        os.makedirs(destination_dir, exist_ok=True)
        
        # Generate filename
        filename = self._generate_download_filename(media_item)
        destination_path = os.path.join(destination_dir, filename)
        
        # Start download with completion callback
        task = self.jellyfin_service.download_media(
            media_item.jellyfin_id, 
            destination_path, 
            completion_callback=self._handle_download_completion
        )
        
        # Store final destination in task metadata for post-download processing
        if final_destination:
            task.final_destination = final_destination
            self.logger.info(f"Set final_destination on task {task.task_id}: {final_destination}")
        else:
            self.logger.info(f"No final_destination provided for task {task.task_id}")
        
        with self._download_lock:
            self._download_queue[task.task_id] = task
        
        # Download and cache the thumbnail image if available
        if media_item.thumbnail_url:
            self._download_thumbnail_async(media_item.thumbnail_url, media_id)
            
        # Store thumbnail URL in task for poster download during completion
        if media_item.thumbnail_url:
            task.thumbnail_url = media_item.thumbnail_url
        
        self.logger.info(f"Started download: {media_item.title} -> {destination_path}")
        return task
    
    def get_download_status(self, task_id: str) -> Optional[DownloadTask]:
        """
        Get status of a download task.
        
        Args:
            task_id: Download task identifier
            
        Returns:
            DownloadTask object or None if not found
        """
        with self._download_lock:
            task = self._download_queue.get(task_id)
            if task:
                # Get previous status
                previous_status = task.status
                
                # Update from Jellyfin service
                updated_task = self.jellyfin_service.get_download_status(task_id)
                if updated_task:
                    # Preserve custom attributes from the original task
                    if hasattr(task, 'final_destination'):
                        updated_task.final_destination = task.final_destination
                        # Only log once to avoid spam
                        if not hasattr(updated_task, '_final_destination_logged'):
                            updated_task._final_destination_logged = True
                            self.logger.debug(f"Preserved final_destination on updated task: {task.final_destination}")
                    
                    self._download_queue[task_id] = updated_task
                    
                    # Check if download just completed
                    if (previous_status != DownloadStatus.COMPLETED and 
                        updated_task.status == DownloadStatus.COMPLETED):
                        self._handle_download_completion(updated_task)
                        
                        # Schedule cleanup of completed task after a delay to allow UI to show completion
                        import threading
                        def cleanup_completed_task():
                            import time
                            time.sleep(3)  # Wait 3 seconds
                            with self._download_lock:
                                if task_id in self._download_queue:
                                    del self._download_queue[task_id]
                                    self.logger.info(f"Cleaned up completed download task: {task_id}")
                        
                        cleanup_thread = threading.Thread(target=cleanup_completed_task, daemon=True)
                        cleanup_thread.start()
                    
                    return updated_task
            return task
    
    def get_all_download_tasks(self) -> List[DownloadTask]:
        """
        Get all download tasks.
        
        Returns:
            List of DownloadTask objects
        """
        with self._download_lock:
            tasks = []
            for task_id, task in self._download_queue.items():
                # Get previous status
                previous_status = task.status
                
                # Get updated status from Jellyfin service
                updated_task = self.jellyfin_service.get_download_status(task_id)
                if updated_task:
                    # Preserve custom attributes from the original task
                    if hasattr(task, 'final_destination'):
                        updated_task.final_destination = task.final_destination
                        # Only log once to avoid spam
                        if not hasattr(updated_task, '_final_destination_logged'):
                            updated_task._final_destination_logged = True
                            self.logger.debug(f"Preserved final_destination on updated task: {task.final_destination}")
                    
                    self._download_queue[task_id] = updated_task
                    
                    # Check if download just completed
                    if (previous_status != DownloadStatus.COMPLETED and 
                        updated_task.status == DownloadStatus.COMPLETED):
                        self._handle_download_completion(updated_task)
                        
                        # Schedule cleanup of completed task after a delay to allow UI to show completion
                        import threading
                        def cleanup_completed_task():
                            import time
                            time.sleep(3)  # Wait 3 seconds
                            with self._download_lock:
                                if task_id in self._download_queue:
                                    del self._download_queue[task_id]
                                    self.logger.info(f"Cleaned up completed download task: {task_id}")
                        
                        cleanup_thread = threading.Thread(target=cleanup_completed_task, daemon=True)
                        cleanup_thread.start()
                    
                    tasks.append(updated_task)
                else:
                    tasks.append(task)
            return tasks
    
    def cancel_download(self, task_id: str) -> bool:
        """
        Cancel a download task.
        
        Args:
            task_id: Download task identifier
            
        Returns:
            True if cancelled successfully, False otherwise
        """
        with self._download_lock:
            if task_id not in self._download_queue:
                return False
            
            success = self.jellyfin_service.cancel_download(task_id)
            if success:
                task = self._download_queue[task_id]
                task.mark_failed("Cancelled by user")
                self.logger.info(f"Cancelled download: {task_id}")
            
            return success
    
    def compare_media_libraries(self, force_refresh: bool = False) -> MediaComparison:
        """
        Compare local and remote media libraries.
        
        Args:
            force_refresh: Force refresh of comparison data
            
        Returns:
            MediaComparison object with detailed comparison results
        """
        current_time = time.time()
        
        # Return cached comparison if still valid
        if (not force_refresh and 
            self._comparison_cache and 
            current_time - self._comparison_timestamp < self._cache_ttl):
            return self._comparison_cache
        
        self.logger.info("Comparing media libraries")
        
        # Get media from both sources
        local_media = self._get_local_media_items()
        remote_media = self._get_remote_media_items()
        
        # Create lookup sets for efficient comparison
        local_titles = {self._normalize_title(item.title): item for item in local_media}
        remote_titles = {self._normalize_title(item.title): item for item in remote_media}
        
        # Find items in different categories
        local_only_items = []
        remote_only_items = []
        both_available_items = []
        
        # Items only in local
        for normalized_title, item in local_titles.items():
            if normalized_title not in remote_titles:
                local_only_items.append(item)
        
        # Items only in remote
        for normalized_title, item in remote_titles.items():
            if normalized_title not in local_titles:
                remote_only_items.append(item)
        
        # Items in both (merge them)
        for normalized_title in local_titles.keys() & remote_titles.keys():
            local_item = local_titles[normalized_title]
            remote_item = remote_titles[normalized_title]
            merged_item = self._merge_media_items(local_item, remote_item)
            both_available_items.append(merged_item)
        
        # Create comparison result
        comparison = MediaComparison(
            local_only=local_only_items,
            remote_only=remote_only_items,
            both_available=both_available_items,
            total_local=len(local_media),
            total_remote=len(remote_media),
            total_unified=len(local_only_items) + len(remote_only_items) + len(both_available_items)
        )
        
        # Cache the result
        self._comparison_cache = comparison
        self._comparison_timestamp = current_time
        
        self.logger.info(f"Library comparison: {comparison.total_local} local, "
                        f"{comparison.total_remote} remote, {comparison.total_unified} unified")
        
        return comparison
    
    def synchronize_libraries(self) -> Dict[str, Any]:
        """
        Synchronize local and remote media libraries.
        
        Returns:
            Dictionary with synchronization results
        """
        self.logger.info("Starting library synchronization")
        
        # Force refresh of local media - use configured paths
        # Get configured paths from the app config if available
        try:
            from flask import current_app
            config = current_app.config.get('MEDIA_CONFIG')
            scan_paths = config.local_media_paths if config else ["media/movies", "media/tv-shows", "media/downloads"]
        except Exception:
            # Fallback if not in Flask context
            scan_paths = ["media/movies", "media/tv-shows", "media/downloads"]
        
        self.local_service.scan_media_directories(scan_paths)
        
        # Clear caches to force refresh
        with self._cache_lock:
            self._unified_media_cache.clear()
            self._cache_timestamp = 0
        
        self._comparison_cache = None
        self._comparison_timestamp = 0
        
        # Get fresh comparison
        comparison = self.compare_media_libraries(force_refresh=True)
        
        # Get fresh unified list
        unified_media = self.get_unified_media_list(force_refresh=True)
        
        sync_result = {
            'timestamp': time.time(),
            'local_items': comparison.total_local,
            'remote_items': comparison.total_remote,
            'unified_items': comparison.total_unified,
            'local_only': len(comparison.local_only),
            'remote_only': len(comparison.remote_only),
            'both_available': len(comparison.both_available),
            'sync_successful': True
        }
        
        self.logger.info(f"Library synchronization completed: {sync_result}")
        return sync_result
    
    def cleanup_completed_downloads(self) -> int:
        """
        Clean up completed and failed download tasks.
        
        Returns:
            Number of tasks cleaned up
        """
        with self._download_lock:
            tasks_to_remove = []
            
            for task_id, task in self._download_queue.items():
                if task.is_finished():
                    tasks_to_remove.append(task_id)
            
            for task_id in tasks_to_remove:
                del self._download_queue[task_id]
            
            self.logger.info(f"Cleaned up {len(tasks_to_remove)} completed download tasks")
            return len(tasks_to_remove)
    
    def _handle_download_completion(self, completed_task: DownloadTask) -> None:
        """
        Handle download completion by moving file to final destination and refreshing local media library.
        
        Args:
            completed_task: The completed download task
        """
        try:
            self.logger.info(f"Download completion handler called for: {completed_task.media_id} -> {completed_task.file_path}")
            
            # Debug: Check if final_destination attribute exists
            has_final_dest = hasattr(completed_task, 'final_destination')
            final_dest_value = getattr(completed_task, 'final_destination', None) if has_final_dest else None
            self.logger.info(f"Task has final_destination: {has_final_dest}, value: {final_dest_value}")
            
            import os
            import shutil
            
            if not completed_task.file_path or not os.path.exists(completed_task.file_path):
                self.logger.warning(f"Downloaded file not found: {completed_task.file_path}")
                return
            
            final_file_path = completed_task.file_path
            
            # Store original path for cleanup
            original_file_path = completed_task.file_path
            original_dir = os.path.dirname(original_file_path)
            
            # Check if we need to move the file to a final destination
            if hasattr(completed_task, 'final_destination') and completed_task.final_destination:
                try:
                    self.logger.info(f"Moving file from {completed_task.file_path} to final destination: {completed_task.final_destination}")
                    
                    # Ensure final destination directory exists
                    os.makedirs(completed_task.final_destination, exist_ok=True)
                    self.logger.info(f"Created/verified final destination directory: {completed_task.final_destination}")
                    
                    # Generate final file path
                    filename = os.path.basename(completed_task.file_path)
                    final_file_path = os.path.join(completed_task.final_destination, filename)
                    self.logger.info(f"Final file path will be: {final_file_path}")
                    
                    # Check if source file exists before moving
                    if not os.path.exists(completed_task.file_path):
                        self.logger.error(f"Source file does not exist for move: {completed_task.file_path}")
                        return
                    
                    # Move the file to final destination
                    self.logger.info(f"Executing file move: {completed_task.file_path} -> {final_file_path}")
                    shutil.move(completed_task.file_path, final_file_path)
                    
                    # Update task with final path
                    completed_task.file_path = final_file_path
                    
                    self.logger.info(f"Successfully moved downloaded file to final destination: {final_file_path}")
                    
                    # Verify the file exists at the new location
                    if os.path.exists(final_file_path):
                        file_size = os.path.getsize(final_file_path)
                        self.logger.info(f"File verified at final destination: {final_file_path} ({file_size} bytes)")
                    else:
                        self.logger.error(f"File not found at final destination after move: {final_file_path}")
                    
                except Exception as move_error:
                    self.logger.error(f"Failed to move file to final destination {completed_task.final_destination}: {move_error}")
                    self.logger.error(f"Move error details: {type(move_error).__name__}: {str(move_error)}")
                    # Continue with original path if move fails
                    final_file_path = completed_task.file_path
            else:
                self.logger.info(f"No final destination specified, file will remain at: {completed_task.file_path}")
            
            # Get the directory containing the final file for rescanning
            final_dir = os.path.dirname(final_file_path)
            
            # Rescan the directory containing the final file
            self.local_service.scan_media_directories([final_dir])
            self.logger.info(f"Rescanned local media directory: {final_dir}")
            
            # If file was moved, also clean up the original download directory if it's different
            if (hasattr(completed_task, 'final_destination') and 
                completed_task.final_destination and 
                original_dir != final_dir):
                
                self.local_service.scan_media_directories([original_dir])
                self.logger.info(f"Rescanned original download directory: {original_dir}")
            
            # Clear caches to force refresh on next request
            with self._cache_lock:
                self._unified_media_cache.clear()
                self._cache_timestamp = 0
                self._local_media_cache.clear()
                self._local_cache_timestamp = 0
            
            # Download poster alongside the media file if available
            if hasattr(completed_task, 'thumbnail_url') and completed_task.thumbnail_url:
                self._download_poster_for_local_media(completed_task.thumbnail_url, final_file_path)
            
            # Clear comparison cache
            self._comparison_cache = None
            self._comparison_timestamp = 0
            
            self.logger.info(f"Cleared media caches after download completion: {completed_task.media_id}")
                
        except Exception as e:
            self.logger.error(f"Error handling download completion for {completed_task.media_id}: {e}")
    
    def _download_poster_for_local_media(self, thumbnail_url: str, media_file_path: str) -> Optional[str]:
        """
        Download poster image and save it alongside the media file.
        
        Args:
            thumbnail_url: URL of the poster/thumbnail to download
            media_file_path: Path to the media file
            
        Returns:
            Path to the downloaded poster file or None if failed
        """
        try:
            import os
            import requests
            from urllib.parse import urlparse
            
            # Generate poster filename based on media file
            media_dir = os.path.dirname(media_file_path)
            media_name = os.path.splitext(os.path.basename(media_file_path))[0]
            
            # Try to determine file extension from URL or default to jpg
            parsed_url = urlparse(thumbnail_url)
            url_ext = os.path.splitext(parsed_url.path)[1].lower()
            if url_ext in ['.jpg', '.jpeg', '.png', '.webp']:
                poster_ext = url_ext
            else:
                poster_ext = '.jpg'  # Default extension
            
            poster_filename = f"{media_name}-poster{poster_ext}"
            poster_path = os.path.join(media_dir, poster_filename)
            
            # Skip if poster already exists
            if os.path.exists(poster_path):
                self.logger.info(f"Poster already exists: {poster_path}")
                return poster_path
            
            self.logger.info(f"Downloading poster from {thumbnail_url} to {poster_path}")
            
            # Download the poster
            response = requests.get(thumbnail_url, timeout=30, stream=True)
            response.raise_for_status()
            
            # Check content type and adjust extension if needed
            content_type = response.headers.get('content-type', '').lower()
            if 'jpeg' in content_type or 'jpg' in content_type:
                correct_ext = '.jpg'
            elif 'png' in content_type:
                correct_ext = '.png'
            elif 'webp' in content_type:
                correct_ext = '.webp'
            else:
                correct_ext = poster_ext  # Keep original guess
            
            # Update poster path if extension changed
            if correct_ext != poster_ext:
                poster_filename = f"{media_name}-poster{correct_ext}"
                poster_path = os.path.join(media_dir, poster_filename)
            
            # Save the poster file
            with open(poster_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            self.logger.info(f"Successfully downloaded poster: {poster_path}")
            return poster_path
            
        except Exception as e:
            self.logger.error(f"Failed to download poster from {thumbnail_url}: {e}")
            return None
    
    def _get_local_media_items(self, force_refresh: bool = False) -> List[MediaItem]:
        """
        Get media items from local service with caching.
        
        Args:
            force_refresh: Force refresh of cached data
            
        Returns:
            List of MediaItem objects from local storage
        """
        current_time = time.time()
        
        # Return cached data if still valid and not forcing refresh
        if (not force_refresh and 
            self._local_media_cache and 
            current_time - self._local_cache_timestamp < self._cache_ttl):
            self.logger.debug("Returning cached local media list")
            return self._local_media_cache.copy()
        
        try:
            self.logger.info("Loading local media from disk")
            local_media = self.local_service.get_local_media()
            media_items = self.local_service.to_media_items(local_media)
            
            # Update cache
            self._local_media_cache = media_items
            self._local_cache_timestamp = current_time
            
            return media_items.copy()
        except Exception as e:
            self.logger.error(f"Error getting local media: {e}")
            # Return cached data if available, even if expired
            if self._local_media_cache:
                self.logger.warning("Returning expired cached local media due to error")
                return self._local_media_cache.copy()
            return []
    
    def _get_remote_media_items(self, force_refresh: bool = False) -> List[MediaItem]:
        """
        Get media items from Jellyfin service with caching.
        
        Args:
            force_refresh: Force refresh of cached data
            
        Returns:
            List of MediaItem objects from Jellyfin
        """
        current_time = time.time()
        
        # Return cached data if still valid and not forcing refresh
        if (not force_refresh and 
            self._remote_media_cache and 
            current_time - self._remote_cache_timestamp < self._cache_ttl):
            self.logger.debug("Returning cached remote media list")
            return self._remote_media_cache.copy()
        
        try:
            self.logger.info("Loading remote media from Jellyfin")
            media_items, metadata = self.jellyfin_service.get_media_library()
            
            # Log retrieval metadata
            if metadata.get('errors'):
                self.logger.warning(f"Jellyfin retrieval had errors: {metadata['errors']}")
            if metadata.get('warnings'):
                self.logger.info(f"Jellyfin retrieval warnings: {metadata['warnings']}")
            if metadata.get('partial_success'):
                self.logger.warning("Jellyfin retrieval completed with partial success")
            
            self.logger.info(f"Retrieved {len(media_items)} remote media items in {metadata.get('retrieval_time_ms', 0):.1f}ms")
            self.logger.debug(f"Jellyfin retrieval metadata: {metadata}")
            
            # Update cache
            self._remote_media_cache = media_items
            self._remote_cache_timestamp = current_time
            
            return media_items.copy()
        except Exception as e:
            self.logger.error(f"Error getting remote media: {e}")
            # Return cached data if available, even if expired
            if self._remote_media_cache:
                self.logger.warning("Returning expired cached remote media due to error")
                return self._remote_media_cache.copy()
            return []
    
    def _merge_and_deduplicate(self, local_media: List[MediaItem], remote_media: List[MediaItem]) -> List[MediaItem]:
        """
        Merge local and remote media lists with deduplication.
        
        Args:
            local_media: List of local MediaItem objects
            remote_media: List of remote MediaItem objects
            
        Returns:
            Deduplicated list of MediaItem objects
        """
        # Create lookup dictionaries for efficient matching
        local_by_title = {}
        remote_by_title = {}
        
        for item in local_media:
            normalized_title = self._normalize_title(item.title)
            local_by_title[normalized_title] = item
        
        for item in remote_media:
            normalized_title = self._normalize_title(item.title)
            remote_by_title[normalized_title] = item
        
        unified_media = []
        processed_titles = set()
        
        # Process items that exist in both local and remote
        for normalized_title in local_by_title.keys() & remote_by_title.keys():
            local_item = local_by_title[normalized_title]
            remote_item = remote_by_title[normalized_title]
            merged_item = self._merge_media_items(local_item, remote_item)
            unified_media.append(merged_item)
            processed_titles.add(normalized_title)
        
        # Add local-only items
        for normalized_title, item in local_by_title.items():
            if normalized_title not in processed_titles:
                unified_media.append(item)
                processed_titles.add(normalized_title)
        
        # Add remote-only items
        for normalized_title, item in remote_by_title.items():
            if normalized_title not in processed_titles:
                unified_media.append(item)
                processed_titles.add(normalized_title)
        
        # Sort by title for consistent ordering
        unified_media.sort(key=lambda x: x.title.lower())
        
        return unified_media
    
    def _merge_media_items(self, local_item: MediaItem, remote_item: MediaItem) -> MediaItem:
        """
        Merge local and remote MediaItem objects.
        
        Args:
            local_item: Local MediaItem
            remote_item: Remote MediaItem
            
        Returns:
            Merged MediaItem with BOTH availability
        """
        # Use local item as base and merge remote data
        merged_metadata = {**remote_item.metadata, **local_item.metadata}
        
        # Prioritize local poster if available, otherwise use cached remote thumbnail
        cached_thumbnail_path = local_item.cached_thumbnail_path
        if not cached_thumbnail_path and remote_item.thumbnail_url:
            cached_path = self.get_cached_image_path(remote_item.thumbnail_url)
            if cached_path:
                cached_thumbnail_path = cached_path
        
        return MediaItem(
            id=local_item.id,  # Prefer local ID
            title=local_item.title,  # Prefer local title (usually cleaner)
            type=local_item.type,
            availability=MediaAvailability.BOTH,
            year=local_item.year or remote_item.year,
            duration=local_item.duration or remote_item.duration,
            thumbnail_url=remote_item.thumbnail_url,  # Keep remote thumbnail URL for fallback
            cached_thumbnail_path=cached_thumbnail_path,  # Prioritize local poster
            local_path=local_item.local_path,
            jellyfin_id=remote_item.jellyfin_id,
            metadata=merged_metadata
        )
    
    def _normalize_title(self, title: str) -> str:
        """
        Normalize title for comparison and deduplication.
        
        Args:
            title: Original title
            
        Returns:
            Normalized title string
        """
        import re
        
        # Convert to lowercase
        normalized = title.lower()
        
        # Remove common articles and prepositions
        normalized = re.sub(r'^(the|a|an)\s+', '', normalized)
        
        # Remove special characters and extra spaces
        normalized = re.sub(r'[^\w\s]', '', normalized)
        normalized = re.sub(r'\s+', ' ', normalized)
        
        # Remove year patterns
        normalized = re.sub(r'\b\d{4}\b', '', normalized)
        
        # Remove quality indicators
        quality_patterns = [
            r'\b(1080p?|720p?|480p?|4k|uhd|hdr)\b',
            r'\b(bluray|bdrip|dvdrip|webrip|hdtv)\b',
            r'\b(x264|x265|h\.?264|h\.?265|hevc)\b'
        ]
        for pattern in quality_patterns:
            normalized = re.sub(pattern, '', normalized, flags=re.IGNORECASE)
        
        # Clean up extra spaces
        normalized = ' '.join(normalized.split())
        
        return normalized.strip()
    
    def _generate_download_filename(self, media_item: MediaItem) -> str:
        """
        Generate appropriate filename for downloaded media.
        
        Args:
            media_item: MediaItem to generate filename for
            
        Returns:
            Generated filename
        """
        import re
        
        # Start with title
        filename = media_item.title
        
        # Add year if available
        if media_item.year:
            filename += f" ({media_item.year})"
        
        # Clean filename for filesystem
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        filename = re.sub(r'\s+', ' ', filename).strip()
        
        # Add appropriate extension based on media type
        if media_item.type == MediaType.MOVIE:
            filename += ".mp4"
        elif media_item.type in [MediaType.TV_SHOW, MediaType.EPISODE]:
            filename += ".mkv"
        else:
            filename += ".mp4"  # Default
        
        return filename
    
    def request_jellyfin_sync(self) -> None:
        """
        Set flag to request Jellyfin sync on next media list retrieval.
        This allows the UI to explicitly request a sync without forcing an immediate refresh.
        """
        self.logger.info("Jellyfin sync requested for next media list retrieval")
        self._jellyfin_sync_requested = True
    
    def get_cached_image_path(self, image_url: str) -> Optional[str]:
        """
        Get cached local path for an image URL.
        
        Args:
            image_url: Original image URL
            
        Returns:
            Local file path if cached, None otherwise
        """
        with self._image_cache_lock:
            return self._image_cache.get(image_url)
    
    def _download_thumbnail_async(self, image_url: str, media_id: str) -> None:
        """
        Download and cache a thumbnail image asynchronously.
        
        Args:
            image_url: URL of the image to download
            media_id: Media ID associated with the image
        """
        # Check if already cached
        with self._image_cache_lock:
            if image_url in self._image_cache:
                self.logger.debug(f"Image already cached for {media_id}: {image_url}")
                return
        
        # Start download in a separate thread
        thread = threading.Thread(
            target=self._download_thumbnail,
            args=(image_url, media_id),
            daemon=True
        )
        thread.start()
    
    def _download_thumbnail(self, image_url: str, media_id: str) -> None:
        """
        Download and cache a thumbnail image.
        
        Args:
            image_url: URL of the image to download
            media_id: Media ID associated with the image
        """
        import os
        import requests
        from pathlib import Path
        
        try:
            # Create cache directory if it doesn't exist
            cache_dir = Path("media/cache/thumbnails")
            cache_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate filename based on media_id and URL hash
            import hashlib
            url_hash = hashlib.md5(image_url.encode()).hexdigest()
            file_ext = os.path.splitext(image_url)[1] or ".jpg"
            if file_ext.startswith(".") and len(file_ext) > 5:  # If extension is too long or invalid
                file_ext = ".jpg"
            
            filename = f"{media_id}_{url_hash}{file_ext}"
            local_path = cache_dir / filename
            
            # Skip if already downloaded
            if local_path.exists():
                with self._image_cache_lock:
                    self._image_cache[image_url] = str(local_path)
                self.logger.debug(f"Using existing cached image for {media_id}: {local_path}")
                return
            
            # Download the image
            self.logger.debug(f"Downloading thumbnail for {media_id}: {image_url}")
            response = requests.get(image_url, stream=True, timeout=10)
            response.raise_for_status()
            
            # Save to file
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Update cache
            with self._image_cache_lock:
                self._image_cache[image_url] = str(local_path)
            
            self.logger.info(f"Cached thumbnail for {media_id}: {local_path}")
            
        except Exception as e:
            self.logger.error(f"Error downloading thumbnail for {media_id}: {e}")
    
    def cleanup(self) -> None:
        """Clean up resources and stop background tasks."""
        self.logger.info("Cleaning up MediaManager resources")
        
        # Cancel all active downloads
        with self._download_lock:
            for task_id in list(self._download_queue.keys()):
                self.cancel_download(task_id)
        
        # Shutdown download executor
        self._download_executor.shutdown(wait=True)
        
        # Clean up individual services
        if hasattr(self.local_service, 'cleanup'):
            self.local_service.cleanup()
        
        if hasattr(self.vlc_controller, 'cleanup'):
            self.vlc_controller.cleanup()