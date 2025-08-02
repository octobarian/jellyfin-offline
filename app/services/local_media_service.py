"""
Local Media Service for the RV Media Player application.

This service handles scanning, indexing, and managing local media files.
"""
import os
import sqlite3
import hashlib
import logging
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Dict, Any, Set, Tuple
from pathlib import Path
from dataclasses import dataclass, asdict
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from mutagen import File as MutagenFile
from pymediainfo import MediaInfo

from ..models.media_item import MediaItem
from ..models.enums import MediaType, MediaAvailability


@dataclass
class LocalMediaItem:
    """Represents a local media file with metadata."""
    file_path: str
    title: str
    media_type: MediaType
    file_size: int
    duration: Optional[int] = None
    year: Optional[int] = None
    resolution: Optional[str] = None
    codec: Optional[str] = None
    file_hash: Optional[str] = None
    last_modified: Optional[float] = None
    metadata: Dict[str, Any] = None
    file_validated: bool = False
    validation_timestamp: float = 0
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class MediaFileHandler(FileSystemEventHandler):
    """File system event handler for media file changes."""
    
    def __init__(self, service: 'LocalMediaService'):
        self.service = service
        self.logger = logging.getLogger(__name__)
    
    def on_created(self, event):
        """Handle file creation events."""
        if not event.is_directory and self._is_media_file(event.src_path):
            self.logger.info(f"New media file detected: {event.src_path}")
            self.service.add_media_file(event.src_path)
    
    def on_deleted(self, event):
        """Handle file deletion events."""
        if not event.is_directory and self._is_media_file(event.src_path):
            self.logger.info(f"Media file deleted: {event.src_path}")
            self.service.remove_media_file(event.src_path)
    
    def on_moved(self, event):
        """Handle file move events."""
        if not event.is_directory and self._is_media_file(event.dest_path):
            self.logger.info(f"Media file moved: {event.src_path} -> {event.dest_path}")
            self.service.remove_media_file(event.src_path)
            self.service.add_media_file(event.dest_path)
    
    def _is_media_file(self, file_path: str) -> bool:
        """Check if file is a supported media file."""
        return self.service.is_supported_media_file(file_path)


class LocalMediaService:
    """Service for managing local media files and metadata."""
    
    # Supported media file extensions
    SUPPORTED_EXTENSIONS = {
        '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v',
        '.mpg', '.mpeg', '.3gp', '.ogv', '.ts', '.m2ts', '.mts'
    }
    
    def __init__(self, db_path: str = "media/local_media.db", validation_cache_ttl: int = 300, max_validation_workers: int = 10):
        """
        Initialize the LocalMediaService.
        
        Args:
            db_path: Path to the SQLite database file
            validation_cache_ttl: Cache TTL in seconds for validation results (default: 300 = 5 minutes)
            max_validation_workers: Maximum number of concurrent validation threads (default: 10)
        """
        self.db_path = db_path
        self.logger = logging.getLogger(__name__)
        self.observer = Observer()
        self.watched_paths: List[str] = []
        
        # File validation caching with configurable TTL
        self._validation_cache: Dict[str, float] = {}  # file_path -> validation_timestamp
        self._validation_cache_ttl = validation_cache_ttl
        self._cache_lock = threading.RLock()  # Thread-safe cache access
        
        # Performance optimization settings
        self._max_validation_workers = max_validation_workers
        self._validation_stats = {
            'total_validations': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'files_validated': 0,
            'files_missing': 0,
            'validation_time_total': 0.0,
            'last_validation_batch_size': 0,
            'last_validation_duration': 0.0
        }
        self._stats_lock = threading.Lock()
        
        # Initialize database
        self._init_database()
    
    def _init_database(self) -> None:
        """Initialize the SQLite database with required tables and optimizations."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            # Enable WAL mode for better concurrency and performance
            conn.execute('PRAGMA journal_mode=WAL')
            
            # Set synchronous mode to NORMAL for better performance
            conn.execute('PRAGMA synchronous=NORMAL')
            
            # Enable memory-mapped I/O for better performance with large databases
            conn.execute('PRAGMA mmap_size=268435456')  # 256MB
            
            # Create the main table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS local_media (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    duration INTEGER,
                    year INTEGER,
                    resolution TEXT,
                    codec TEXT,
                    file_hash TEXT,
                    last_modified REAL,
                    metadata TEXT,
                    file_validated BOOLEAN DEFAULT 0,
                    validation_timestamp REAL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Add new columns if they don't exist (for existing databases)
            try:
                conn.execute('ALTER TABLE local_media ADD COLUMN file_validated BOOLEAN DEFAULT 0')
                self.logger.info("Added file_validated column to existing database")
            except sqlite3.OperationalError:
                # Column already exists
                pass
            
            try:
                conn.execute('ALTER TABLE local_media ADD COLUMN validation_timestamp REAL DEFAULT 0')
                self.logger.info("Added validation_timestamp column to existing database")
            except sqlite3.OperationalError:
                # Column already exists
                pass
            
            # Create indexes for better performance
            conn.execute('CREATE INDEX IF NOT EXISTS idx_file_path ON local_media(file_path)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_media_type ON local_media(media_type)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_file_hash ON local_media(file_hash)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_title ON local_media(title COLLATE NOCASE)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_year ON local_media(year)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_file_validated ON local_media(file_validated)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_validation_timestamp ON local_media(validation_timestamp)')
            
            # Optimize the database
            conn.execute('PRAGMA optimize')
            
            conn.commit()
    
    def scan_media_directories(self, directories: List[str]) -> List[LocalMediaItem]:
        """
        Scan directories for media files and update the database.
        
        Args:
            directories: List of directory paths to scan
            
        Returns:
            List of LocalMediaItem objects found during scan
        """
        self.logger.info(f"Starting media scan of directories: {directories}")
        found_media = []
        scan_stats = {
            'directories_scanned': 0,
            'directories_missing': 0,
            'files_found': 0,
            'media_files_found': 0,
            'media_files_processed': 0,
            'processing_errors': 0,
            'expected_files': ["A Moment to Remember", "3000 Miles to Graceland"]  # Files we expect to find
        }
        
        for directory in directories:
            self.logger.info(f"Processing directory: {directory}")
            
            if not os.path.exists(directory):
                self.logger.warning(f"Directory does not exist: {directory}")
                scan_stats['directories_missing'] += 1
                continue
            
            scan_stats['directories_scanned'] += 1
            self.logger.info(f"Scanning directory: {directory}")
            
            # Track files in this directory
            dir_files_found = 0
            dir_media_files = 0
            
            for root, dirs, files in os.walk(directory):
                self.logger.debug(f"Walking subdirectory: {root}")
                self.logger.debug(f"Found {len(files)} files in {root}")
                
                for file in files:
                    file_path = os.path.join(root, file)
                    dir_files_found += 1
                    scan_stats['files_found'] += 1
                    
                    self.logger.debug(f"Examining file: {file}")
                    
                    # Check if it's a supported media file
                    if self.is_supported_media_file(file_path):
                        dir_media_files += 1
                        scan_stats['media_files_found'] += 1
                        self.logger.info(f"Found media file: {file_path}")
                        
                        # Check if this is one of our expected files
                        for expected_file in scan_stats['expected_files']:
                            if expected_file.lower() in file.lower():
                                self.logger.info(f"✓ Found expected file: {expected_file} -> {file}")
                        
                        try:
                            self.logger.debug(f"Processing media file: {file_path}")
                            media_item = self._process_media_file(file_path)
                            if media_item:
                                found_media.append(media_item)
                                scan_stats['media_files_processed'] += 1
                                self.logger.info(f"Successfully processed: {media_item.title} ({file_path})")
                            else:
                                self.logger.warning(f"Failed to process media file (returned None): {file_path}")
                        except Exception as e:
                            scan_stats['processing_errors'] += 1
                            self.logger.error(f"Error processing {file_path}: {e}", exc_info=True)
                    else:
                        self.logger.debug(f"Skipping non-media file: {file} (extension: {os.path.splitext(file)[1]})")
            
            self.logger.info(f"Directory {directory} scan complete: {dir_files_found} total files, {dir_media_files} media files")
        
        # Log final scan statistics
        self.logger.info(f"Media scan completed. Statistics:")
        self.logger.info(f"  - Directories scanned: {scan_stats['directories_scanned']}")
        self.logger.info(f"  - Directories missing: {scan_stats['directories_missing']}")
        self.logger.info(f"  - Total files found: {scan_stats['files_found']}")
        self.logger.info(f"  - Media files found: {scan_stats['media_files_found']}")
        self.logger.info(f"  - Media files processed: {scan_stats['media_files_processed']}")
        self.logger.info(f"  - Processing errors: {scan_stats['processing_errors']}")
        self.logger.info(f"  - Final media items: {len(found_media)}")
        
        # Check for expected files
        found_titles = [item.title for item in found_media]
        for expected_file in scan_stats['expected_files']:
            found_match = any(expected_file.lower() in title.lower() for title in found_titles)
            if found_match:
                self.logger.info(f"✓ Expected file found in results: {expected_file}")
            else:
                self.logger.warning(f"✗ Expected file NOT found in results: {expected_file}")
        
        return found_media
    
    def validate_file_existence(self, media_items: List[LocalMediaItem], concurrent: bool = True) -> List[LocalMediaItem]:
        """
        Validate that media files actually exist on the filesystem with concurrent processing.
        
        Args:
            media_items: List of local media items to validate
            concurrent: Whether to use concurrent validation for better performance
            
        Returns:
            List of media items that exist on disk
        """
        if not media_items:
            return []
        
        start_time = time.time()
        current_time = start_time
        
        # Update performance stats
        with self._stats_lock:
            self._validation_stats['total_validations'] += 1
            self._validation_stats['last_validation_batch_size'] = len(media_items)
        
        # Separate items that need validation from cached items
        items_to_validate = []
        validated_items = []
        
        with self._cache_lock:
            for item in media_items:
                cached_validation = self._validation_cache.get(item.file_path)
                if (cached_validation and 
                    (current_time - cached_validation) < self._validation_cache_ttl and 
                    item.file_validated and 
                    item.validation_timestamp > 0):
                    # File was recently validated and marked as valid, trust the cache
                    validated_items.append(item)
                    with self._stats_lock:
                        self._validation_stats['cache_hits'] += 1
                else:
                    items_to_validate.append(item)
                    with self._stats_lock:
                        self._validation_stats['cache_misses'] += 1
        
        self.logger.info(f"Validation cache: {len(validated_items)} hits, {len(items_to_validate)} misses")
        
        # Validate remaining items
        if items_to_validate:
            if concurrent and len(items_to_validate) > 5:  # Use concurrent validation for larger batches
                newly_validated, missing_files = self._validate_files_concurrent(items_to_validate, current_time)
            else:
                newly_validated, missing_files = self._validate_files_sequential(items_to_validate, current_time)
            
            validated_items.extend(newly_validated)
            
            # Clean up database entries for missing files
            if missing_files:
                self._cleanup_missing_files_optimized(missing_files)
                self.logger.info(f"Removed {len(missing_files)} missing files from database")
                
                with self._stats_lock:
                    self._validation_stats['files_missing'] += len(missing_files)
        
        # Update performance stats
        validation_duration = time.time() - start_time
        with self._stats_lock:
            self._validation_stats['files_validated'] += len(validated_items)
            self._validation_stats['validation_time_total'] += validation_duration
            self._validation_stats['last_validation_duration'] = validation_duration
        
        self.logger.info(f"Validation completed: {len(validated_items)} valid files, "
                        f"{len(missing_files) if 'missing_files' in locals() else 0} missing files, "
                        f"duration: {validation_duration:.2f}s")
        
        return validated_items
    
    def _validate_files_concurrent(self, items: List[LocalMediaItem], current_time: float) -> Tuple[List[LocalMediaItem], List[str]]:
        """
        Validate files concurrently using ThreadPoolExecutor.
        
        Args:
            items: List of items to validate
            current_time: Current timestamp for validation
            
        Returns:
            Tuple of (validated_items, missing_file_paths)
        """
        validated_items = []
        missing_files = []
        
        # Use ThreadPoolExecutor for concurrent file validation
        with ThreadPoolExecutor(max_workers=self._max_validation_workers) as executor:
            # Submit validation tasks
            future_to_item = {
                executor.submit(self._validate_single_file, item, current_time): item 
                for item in items
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_item):
                item = future_to_item[future]
                try:
                    is_valid = future.result()
                    if is_valid:
                        validated_items.append(item)
                    else:
                        missing_files.append(item.file_path)
                        self.logger.warning(f"Local media file not found: {item.file_path}")
                except Exception as e:
                    self.logger.error(f"Error validating file {item.file_path}: {e}")
                    missing_files.append(item.file_path)
        
        return validated_items, missing_files
    
    def _validate_files_sequential(self, items: List[LocalMediaItem], current_time: float) -> Tuple[List[LocalMediaItem], List[str]]:
        """
        Validate files sequentially (fallback for small batches).
        
        Args:
            items: List of items to validate
            current_time: Current timestamp for validation
            
        Returns:
            Tuple of (validated_items, missing_file_paths)
        """
        validated_items = []
        missing_files = []
        
        for item in items:
            try:
                if self._validate_single_file(item, current_time):
                    validated_items.append(item)
                else:
                    missing_files.append(item.file_path)
                    self.logger.warning(f"Local media file not found: {item.file_path}")
            except Exception as e:
                self.logger.error(f"Error validating file {item.file_path}: {e}")
                missing_files.append(item.file_path)
        
        return validated_items, missing_files
    
    def _validate_single_file(self, item: LocalMediaItem, current_time: float) -> bool:
        """
        Validate a single file and update cache and item status.
        
        Args:
            item: Media item to validate
            current_time: Current timestamp
            
        Returns:
            True if file exists and is valid, False otherwise
        """
        try:
            # Perform actual file existence check
            if os.path.exists(item.file_path) and os.path.isfile(item.file_path):
                # File exists, update validation status
                item.file_validated = True
                item.validation_timestamp = current_time
                
                # Update cache (thread-safe)
                with self._cache_lock:
                    self._validation_cache[item.file_path] = current_time
                
                # Update database with validation status
                self._update_validation_status(item.file_path, True, current_time)
                return True
            else:
                # File doesn't exist, remove from cache if present
                with self._cache_lock:
                    self._validation_cache.pop(item.file_path, None)
                return False
                
        except Exception as e:
            self.logger.error(f"Error validating file {item.file_path}: {e}")
            # Remove from cache on error
            with self._cache_lock:
                self._validation_cache.pop(item.file_path, None)
            return False
    
    def get_local_media(self, validate_files: bool = True) -> List[LocalMediaItem]:
        """
        Get all local media items from the database with optional file validation.
        
        Args:
            validate_files: Whether to validate file existence (default: True)
        
        Returns:
            List of LocalMediaItem objects that exist on disk
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('''
                SELECT file_path, title, media_type, file_size, duration, year,
                       resolution, codec, file_hash, last_modified, metadata,
                       file_validated, validation_timestamp
                FROM local_media
                ORDER BY title
            ''')
            
            media_items = []
            for row in cursor.fetchall():
                metadata = {}
                if row['metadata']:
                    try:
                        import json
                        metadata = json.loads(row['metadata'])
                    except json.JSONDecodeError:
                        self.logger.warning(f"Invalid metadata JSON for {row['file_path']}")
                
                media_item = LocalMediaItem(
                    file_path=row['file_path'],
                    title=row['title'],
                    media_type=MediaType(row['media_type']),
                    file_size=row['file_size'],
                    duration=row['duration'],
                    year=row['year'],
                    resolution=row['resolution'],
                    codec=row['codec'],
                    file_hash=row['file_hash'],
                    last_modified=row['last_modified'],
                    metadata=metadata,
                    file_validated=bool(row['file_validated']),
                    validation_timestamp=row['validation_timestamp'] or 0
                )
                media_items.append(media_item)
            
            # Validate file existence if requested
            if validate_files:
                media_items = self.validate_file_existence(media_items)
            
            return media_items
    
    def add_media_file(self, file_path: str) -> Optional[LocalMediaItem]:
        """
        Add a media file to the database.
        
        Args:
            file_path: Path to the media file
            
        Returns:
            LocalMediaItem if successful, None otherwise
        """
        if not self.is_supported_media_file(file_path):
            return None
        
        return self._process_media_file(file_path)
    
    def remove_media_file(self, file_path: str) -> bool:
        """
        Remove a media file from the database.
        
        Args:
            file_path: Path to the media file
            
        Returns:
            True if removed successfully, False otherwise
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('DELETE FROM local_media WHERE file_path = ?', (file_path,))
                removed = cursor.rowcount > 0
                conn.commit()
                
                if removed:
                    self.logger.info(f"Removed media file from database: {file_path}")
                
                return removed
        except Exception as e:
            self.logger.error(f"Error removing media file {file_path}: {e}")
            return False
    
    def get_media_info(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Extract detailed media information from a file.
        
        Args:
            file_path: Path to the media file
            
        Returns:
            Dictionary containing media metadata
        """
        if not os.path.exists(file_path):
            return None
        
        try:
            # Use pymediainfo for detailed technical information
            media_info = MediaInfo.parse(file_path)
            
            info = {
                'file_path': file_path,
                'file_size': os.path.getsize(file_path),
                'last_modified': os.path.getmtime(file_path)
            }
            
            # Extract video track information
            for track in media_info.tracks:
                if track.track_type == 'Video':
                    info.update({
                        'duration': track.duration,
                        'width': track.width,
                        'height': track.height,
                        'resolution': f"{track.width}x{track.height}" if track.width and track.height else None,
                        'codec': track.codec,
                        'frame_rate': track.frame_rate,
                        'bit_rate': track.bit_rate
                    })
                elif track.track_type == 'Audio':
                    info.setdefault('audio_tracks', []).append({
                        'codec': track.codec,
                        'channels': track.channel_s,
                        'sample_rate': track.sampling_rate,
                        'bit_rate': track.bit_rate,
                        'language': track.language
                    })
                elif track.track_type == 'Text':
                    info.setdefault('subtitle_tracks', []).append({
                        'language': track.language,
                        'title': track.title
                    })
            
            # Try to extract metadata using mutagen
            try:
                mutagen_file = MutagenFile(file_path)
                if mutagen_file and mutagen_file.tags:
                    tags = {}
                    for key, value in mutagen_file.tags.items():
                        if isinstance(value, list) and len(value) == 1:
                            tags[key] = str(value[0])
                        else:
                            tags[key] = str(value)
                    info['tags'] = tags
            except Exception as e:
                self.logger.debug(f"Could not extract tags from {file_path}: {e}")
            
            return info
            
        except Exception as e:
            self.logger.error(f"Error extracting media info from {file_path}: {e}")
            return None
    
    def is_supported_media_file(self, file_path: str) -> bool:
        """
        Check if a file is a supported media file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            True if supported, False otherwise
        """
        file_extension = Path(file_path).suffix.lower()
        is_supported = file_extension in self.SUPPORTED_EXTENSIONS
        
        if not is_supported:
            self.logger.debug(f"File extension '{file_extension}' not supported for: {file_path}")
            self.logger.debug(f"Supported extensions: {sorted(self.SUPPORTED_EXTENSIONS)}")
        else:
            self.logger.debug(f"File extension '{file_extension}' is supported for: {file_path}")
        
        return is_supported
    
    def start_watching(self, directories: List[str]) -> None:
        """
        Start watching directories for file system changes.
        
        Args:
            directories: List of directory paths to watch
        """
        if self.observer.is_alive():
            self.stop_watching()
        
        handler = MediaFileHandler(self)
        
        for directory in directories:
            if os.path.exists(directory):
                self.observer.schedule(handler, directory, recursive=True)
                self.watched_paths.append(directory)
                self.logger.info(f"Started watching directory: {directory}")
            else:
                self.logger.warning(f"Cannot watch non-existent directory: {directory}")
        
        if self.watched_paths:
            self.observer.start()
            self.logger.info("File system watcher started")
    
    def stop_watching(self) -> None:
        """Stop watching directories for file system changes."""
        if self.observer.is_alive():
            self.observer.stop()
            self.observer.join()
            self.watched_paths.clear()
            self.logger.info("File system watcher stopped")
    
    def _process_media_file(self, file_path: str) -> Optional[LocalMediaItem]:
        """
        Process a media file and add it to the database.
        
        Args:
            file_path: Path to the media file
            
        Returns:
            LocalMediaItem if successful, None otherwise
        """
        try:
            self.logger.debug(f"Processing media file: {file_path}")
            
            # Verify file exists and is accessible
            if not os.path.exists(file_path):
                self.logger.error(f"File does not exist: {file_path}")
                return None
            
            if not os.path.isfile(file_path):
                self.logger.error(f"Path is not a file: {file_path}")
                return None
            
            # Check if file already exists in database
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('SELECT last_modified FROM local_media WHERE file_path = ?', (file_path,))
                existing = cursor.fetchone()
                
                current_mtime = os.path.getmtime(file_path)
                
                # Skip if file hasn't been modified
                if existing and existing[0] == current_mtime:
                    self.logger.debug(f"File unchanged since last scan, skipping: {file_path}")
                    return None
            
            self.logger.debug(f"Extracting media information from: {file_path}")
            
            # Extract media information
            media_info = self.get_media_info(file_path)
            if not media_info:
                self.logger.error(f"Failed to extract media info from: {file_path}")
                return None
            
            # Determine media type and title
            file_name = os.path.splitext(os.path.basename(file_path))[0]
            self.logger.debug(f"File name (without extension): {file_name}")
            
            title = self._extract_title(file_name)
            self.logger.debug(f"Extracted title: {title}")
            
            media_type = self._determine_media_type(file_path, file_name)
            self.logger.debug(f"Determined media type: {media_type}")
            
            year = self._extract_year(file_name)
            self.logger.debug(f"Extracted year: {year}")
            
            # Calculate file hash for deduplication
            self.logger.debug(f"Calculating file hash for: {file_path}")
            file_hash = self._calculate_file_hash(file_path)
            self.logger.debug(f"File hash: {file_hash[:16]}..." if file_hash else "No hash calculated")
            
            # Create LocalMediaItem with validation status
            current_time = time.time()
            media_item = LocalMediaItem(
                file_path=file_path,
                title=title,
                media_type=media_type,
                file_size=media_info['file_size'],
                duration=media_info.get('duration'),
                year=year,
                resolution=media_info.get('resolution'),
                codec=media_info.get('codec'),
                file_hash=file_hash,
                last_modified=current_mtime,
                metadata=media_info,
                file_validated=True,  # File exists since we're processing it
                validation_timestamp=current_time
            )
            
            self.logger.info(f"Created LocalMediaItem: {media_item.title} ({media_item.file_size} bytes)")
            
            # Update validation cache
            self._validation_cache[file_path] = current_time
            
            # Save to database
            self.logger.debug(f"Saving media item to database: {file_path}")
            self._save_media_item(media_item)
            
            self.logger.info(f"Successfully processed media file: {title} -> {file_path}")
            return media_item
            
        except Exception as e:
            self.logger.error(f"Error processing media file {file_path}: {e}", exc_info=True)
            return None
    
    def _save_media_item(self, media_item: LocalMediaItem) -> None:
        """Save a LocalMediaItem to the database."""
        import json
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO local_media 
                (file_path, title, media_type, file_size, duration, year, resolution, 
                 codec, file_hash, last_modified, metadata, file_validated, validation_timestamp, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (
                media_item.file_path,
                media_item.title,
                media_item.media_type.value,
                media_item.file_size,
                media_item.duration,
                media_item.year,
                media_item.resolution,
                media_item.codec,
                media_item.file_hash,
                media_item.last_modified,
                json.dumps(media_item.metadata) if media_item.metadata else None,
                media_item.file_validated,
                media_item.validation_timestamp
            ))
            conn.commit()
    
    def _update_validation_status(self, file_path: str, validated: bool, timestamp: float) -> None:
        """Update the validation status of a media item in the database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    UPDATE local_media 
                    SET file_validated = ?, validation_timestamp = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE file_path = ?
                ''', (validated, timestamp, file_path))
                conn.commit()
        except Exception as e:
            self.logger.error(f"Error updating validation status for {file_path}: {e}")
    
    def _cleanup_missing_files(self, missing_file_paths: List[str]) -> None:
        """Remove database entries for files that no longer exist."""
        if not missing_file_paths:
            return
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Use parameterized query with IN clause
                placeholders = ','.join('?' * len(missing_file_paths))
                query = f'DELETE FROM local_media WHERE file_path IN ({placeholders})'
                cursor = conn.execute(query, missing_file_paths)
                removed_count = cursor.rowcount
                conn.commit()
                
                self.logger.info(f"Cleaned up {removed_count} missing file entries from database")
        except Exception as e:
            self.logger.error(f"Error cleaning up missing files: {e}")
    
    def _cleanup_missing_files_optimized(self, missing_file_paths: List[str]) -> None:
        """
        Optimized removal of database entries for files that no longer exist.
        Uses batch processing for better performance with large numbers of missing files.
        """
        if not missing_file_paths:
            return
        
        batch_size = 500  # Process in batches to avoid SQL parameter limits
        total_removed = 0
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Enable WAL mode for better concurrent performance
                conn.execute('PRAGMA journal_mode=WAL')
                
                # Process in batches
                for i in range(0, len(missing_file_paths), batch_size):
                    batch = missing_file_paths[i:i + batch_size]
                    placeholders = ','.join('?' * len(batch))
                    query = f'DELETE FROM local_media WHERE file_path IN ({placeholders})'
                    cursor = conn.execute(query, batch)
                    total_removed += cursor.rowcount
                
                conn.commit()
                
                # Optimize database after cleanup
                if total_removed > 100:  # Only optimize for significant cleanups
                    conn.execute('PRAGMA optimize')
                
                self.logger.info(f"Optimized cleanup: removed {total_removed} missing file entries from database")
        except Exception as e:
            self.logger.error(f"Error in optimized cleanup of missing files: {e}")
    
    def _extract_title(self, filename: str) -> str:
        """Extract a clean title from filename."""
        # Remove common patterns like year, quality indicators, etc.
        import re
        
        # First replace dots, underscores, and dashes with spaces for easier pattern matching
        title = re.sub(r'[._-]+', ' ', filename)
        
        # Remove content in brackets and parentheses that contain years or quality indicators
        title = re.sub(r'\([^)]*\d{4}[^)]*\)', '', title)  # Remove (content with year)
        title = re.sub(r'\[[^\]]*\d{4}[^\]]*\]', '', title)  # Remove [content with year]
        title = re.sub(r'\([^)]*(?:1080p?|720p?|480p?|4K|UHD|HDR|BluRay|BDRip|DVDRip|WEBRip|HDTV|x264|x265)[^)]*\)', '', title, flags=re.IGNORECASE)
        title = re.sub(r'\[[^\]]*(?:1080p?|720p?|480p?|4K|UHD|HDR|BluRay|BDRip|DVDRip|WEBRip|HDTV|x264|x265)[^\]]*\]', '', title, flags=re.IGNORECASE)
        
        # Remove remaining quality indicators and year patterns
        removal_patterns = [
            r'\b\d{4}\b',  # Year (4 digits)
            r'\b1080p?\b', r'\b720p?\b', r'\b480p?\b', r'\b4K\b', r'\bUHD\b', r'\bHDR\b',
            r'\bBluRay\b', r'\bBDRip\b', r'\bDVDRip\b', r'\bWEBRip\b', r'\bHDTV\b',
            r'\bx264\b', r'\bx265\b', r'\bH\.264\b', r'\bH\.265\b', r'\bHEVC\b'
        ]
        for pattern in removal_patterns:
            title = re.sub(pattern, '', title, flags=re.IGNORECASE)
        
        # Remove empty brackets and parentheses
        title = re.sub(r'\(\s*\)', '', title)
        title = re.sub(r'\[\s*\]', '', title)
        
        # Clean up extra spaces
        title = ' '.join(title.split())
        
        return title.strip() or filename
    
    def _determine_media_type(self, file_path: str, filename: str) -> MediaType:
        """Determine media type based on file path and name."""
        path_lower = file_path.lower()
        filename_lower = filename.lower()
        
        # Check for TV show patterns
        import re
        tv_patterns = [
            r's\d+e\d+',  # S01E01
            r'season\s*\d+',  # Season 1
            r'episode\s*\d+',  # Episode 1
            r'\d+x\d+',  # 1x01
        ]
        
        for pattern in tv_patterns:
            if re.search(pattern, filename_lower):
                return MediaType.EPISODE
        
        # Check if in TV shows directory
        if 'tv' in path_lower or 'series' in path_lower or 'shows' in path_lower:
            return MediaType.EPISODE
        
        # Default to movie
        return MediaType.MOVIE
    
    def _extract_year(self, filename: str) -> Optional[int]:
        """Extract year from filename."""
        import re
        
        # Look for 4-digit year
        year_match = re.search(r'(\d{4})', filename)
        if year_match:
            year = int(year_match.group(1))
            # Reasonable year range for media
            if 1900 <= year <= 2030:
                return year
        
        return None
    
    def _calculate_file_hash(self, file_path: str) -> str:
        """Calculate SHA-256 hash of file for deduplication."""
        hash_sha256 = hashlib.sha256()
        
        try:
            with open(file_path, 'rb') as f:
                # Read first and last 64KB for large files
                chunk_size = 65536
                hash_sha256.update(f.read(chunk_size))
                
                # Seek to end and read last chunk if file is large
                f.seek(0, 2)  # Seek to end
                file_size = f.tell()
                if file_size > chunk_size * 2:
                    f.seek(-chunk_size, 2)  # Seek to last 64KB
                    hash_sha256.update(f.read(chunk_size))
                
            return hash_sha256.hexdigest()
        except Exception as e:
            self.logger.error(f"Error calculating hash for {file_path}: {e}")
            return ""
    
    def to_media_items(self, local_media_items: List[LocalMediaItem]) -> List[MediaItem]:
        """
        Convert LocalMediaItem objects to MediaItem objects.
        
        Args:
            local_media_items: List of LocalMediaItem objects
            
        Returns:
            List of MediaItem objects
        """
        media_items = []
        
        for local_item in local_media_items:
            # Look for local poster file
            local_poster_path = self._find_local_poster(local_item.file_path)
            
            media_item = MediaItem(
                id=f"local_{local_item.file_hash or abs(hash(local_item.file_path))}",
                title=local_item.title,
                type=local_item.media_type,
                availability=MediaAvailability.LOCAL_ONLY,
                year=local_item.year,
                duration=local_item.duration,
                local_path=local_item.file_path,
                cached_thumbnail_path=local_poster_path,
                metadata=local_item.metadata.copy() if local_item.metadata else {},
                file_validated=local_item.file_validated,
                validation_timestamp=local_item.validation_timestamp
            )
            media_items.append(media_item)
        
        return media_items
    
    def _find_local_poster(self, media_file_path: str) -> Optional[str]:
        """
        Find local poster file for a media file.
        
        Args:
            media_file_path: Path to the media file
            
        Returns:
            Path to local poster file or None if not found
        """
        try:
            media_dir = os.path.dirname(media_file_path)
            media_name = os.path.splitext(os.path.basename(media_file_path))[0]
            
            # Common poster filename patterns
            poster_patterns = [
                f"{media_name}-poster",
                f"{media_name}.poster",
                f"{media_name}_poster",
                f"poster",  # Generic poster file in same directory
            ]
            
            # Common image extensions
            image_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif']
            
            # Check each pattern with each extension
            for pattern in poster_patterns:
                for ext in image_extensions:
                    poster_path = os.path.join(media_dir, f"{pattern}{ext}")
                    if os.path.exists(poster_path):
                        # Return relative path from static directory for web serving
                        # Convert absolute path to relative path for web access
                        return poster_path.replace('\\', '/')
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error finding local poster for {media_file_path}: {e}")
            return None
    
    def get_validation_performance_stats(self) -> Dict[str, Any]:
        """
        Get performance statistics for file validation operations.
        
        Returns:
            Dictionary containing validation performance metrics
        """
        with self._stats_lock:
            stats = self._validation_stats.copy()
        
        # Calculate derived metrics
        if stats['total_validations'] > 0:
            stats['avg_validation_duration'] = stats['validation_time_total'] / stats['total_validations']
            stats['cache_hit_rate'] = stats['cache_hits'] / (stats['cache_hits'] + stats['cache_misses']) if (stats['cache_hits'] + stats['cache_misses']) > 0 else 0.0
        else:
            stats['avg_validation_duration'] = 0.0
            stats['cache_hit_rate'] = 0.0
        
        # Add cache information
        with self._cache_lock:
            stats['cache_size'] = len(self._validation_cache)
            stats['cache_ttl'] = self._validation_cache_ttl
        
        stats['max_validation_workers'] = self._max_validation_workers
        
        return stats
    
    def clear_validation_cache(self) -> int:
        """
        Clear the validation cache.
        
        Returns:
            Number of cache entries cleared
        """
        with self._cache_lock:
            cache_size = len(self._validation_cache)
            self._validation_cache.clear()
            
        self.logger.info(f"Cleared validation cache: {cache_size} entries removed")
        return cache_size
    
    def cleanup_expired_cache_entries(self) -> int:
        """
        Remove expired entries from the validation cache.
        
        Returns:
            Number of expired entries removed
        """
        current_time = time.time()
        expired_keys = []
        
        with self._cache_lock:
            for file_path, validation_time in self._validation_cache.items():
                if (current_time - validation_time) > self._validation_cache_ttl:
                    expired_keys.append(file_path)
            
            for key in expired_keys:
                del self._validation_cache[key]
        
        if expired_keys:
            self.logger.info(f"Cleaned up {len(expired_keys)} expired cache entries")
        
        return len(expired_keys)
    
    def set_validation_cache_ttl(self, ttl_seconds: int) -> None:
        """
        Set the validation cache TTL (Time To Live).
        
        Args:
            ttl_seconds: Cache TTL in seconds
        """
        if ttl_seconds < 0:
            raise ValueError("Cache TTL must be non-negative")
        
        self._validation_cache_ttl = ttl_seconds
        self.logger.info(f"Validation cache TTL set to {ttl_seconds} seconds")
    
    def set_max_validation_workers(self, max_workers: int) -> None:
        """
        Set the maximum number of concurrent validation workers.
        
        Args:
            max_workers: Maximum number of worker threads
        """
        if max_workers < 1:
            raise ValueError("Maximum workers must be at least 1")
        
        self._max_validation_workers = max_workers
        self.logger.info(f"Maximum validation workers set to {max_workers}")
    
    def reset_validation_stats(self) -> None:
        """Reset validation performance statistics."""
        with self._stats_lock:
            self._validation_stats = {
                'total_validations': 0,
                'cache_hits': 0,
                'cache_misses': 0,
                'files_validated': 0,
                'files_missing': 0,
                'validation_time_total': 0.0,
                'last_validation_batch_size': 0,
                'last_validation_duration': 0.0
            }
        
        self.logger.info("Validation performance statistics reset")
    
    def cleanup(self) -> None:
        """
        Cleanup resources used by the service.
        Should be called when the service is no longer needed.
        """
        # Stop file system watcher
        self.stop_watching()
        
        # Clear validation cache
        self.clear_validation_cache()
        
        # Reset stats
        self.reset_validation_stats()
        
        self.logger.info("LocalMediaService cleanup completed")