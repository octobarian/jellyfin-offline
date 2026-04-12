"""
Media Count Validator Service

Validates media counts across different modes and provides discrepancy reporting.
Ensures accurate media counting by comparing API results with actual file system state.
"""
import os
import logging
import time
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass
from pathlib import Path

from ..models.media_item import MediaItem
from ..models.enums import MediaType, MediaAvailability
from .local_media_service import LocalMediaItem


@dataclass
class ValidationResult:
    """Result of media count validation."""
    is_valid: bool
    expected_count: int
    actual_count: int
    discrepancy: int
    missing_files: List[str]
    invalid_items: List[str]
    validation_timestamp: float
    errors: List[str]


@dataclass
class CountDiscrepancy:
    """Represents a discrepancy in media counts."""
    context: str
    expected: int
    actual: int
    difference: int
    details: Dict[str, Any]
    timestamp: float


class MediaCountValidator:
    """
    Service for validating media counts and ensuring consistency across different modes.
    
    Provides methods to:
    - Scan local directories for actual file counts
    - Validate local media counts against file system
    - Validate unified mode consistency
    - Report discrepancies with detailed logging
    """
    
    # Supported media file extensions (matching LocalMediaService)
    SUPPORTED_EXTENSIONS = {
        '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v',
        '.mpg', '.mpeg', '.3gp', '.ogv', '.ts', '.m2ts', '.mts'
    }
    
    def __init__(self, media_directories: List[str] = None):
        """
        Initialize the MediaCountValidator.
        
        Args:
            media_directories: List of media directory paths to scan
        """
        self.media_directories = media_directories or []
        self.logger = logging.getLogger(__name__)
        
        # Cache for directory scan results
        self._directory_scan_cache: Dict[str, Dict[str, Any]] = {}
        self._scan_cache_ttl = 300  # 5 minutes
        
        # Discrepancy tracking
        self._discrepancies: List[CountDiscrepancy] = []
        self._max_discrepancy_history = 100
    
    def scanLocalDirectories(self) -> Dict[str, Any]:
        """
        Scan local media directories to get actual file counts.
        
        Returns:
            Dictionary containing scan results with file counts and paths
        """
        self.logger.info(f"Scanning {len(self.media_directories)} media directories")
        
        scan_result = {
            'total_files': 0,
            'directories_scanned': 0,
            'files_by_directory': {},
            'files_by_extension': {},
            'valid_media_files': [],
            'invalid_files': [],
            'scan_timestamp': time.time(),
            'scan_duration': 0,
            'errors': []
        }
        
        start_time = time.time()
        
        for directory in self.media_directories:
            if not os.path.exists(directory):
                error_msg = f"Directory does not exist: {directory}"
                self.logger.warning(error_msg)
                scan_result['errors'].append(error_msg)
                continue
            
            if not os.path.isdir(directory):
                error_msg = f"Path is not a directory: {directory}"
                self.logger.warning(error_msg)
                scan_result['errors'].append(error_msg)
                continue
            
            try:
                directory_files = self._scan_single_directory(directory)
                scan_result['directories_scanned'] += 1
                scan_result['files_by_directory'][directory] = directory_files
                scan_result['total_files'] += directory_files['count']
                scan_result['valid_media_files'].extend(directory_files['valid_files'])
                scan_result['invalid_files'].extend(directory_files['invalid_files'])
                
                # Update extension counts
                for ext, count in directory_files['extensions'].items():
                    scan_result['files_by_extension'][ext] = scan_result['files_by_extension'].get(ext, 0) + count
                
            except Exception as e:
                error_msg = f"Error scanning directory {directory}: {str(e)}"
                self.logger.error(error_msg)
                scan_result['errors'].append(error_msg)
        
        scan_result['scan_duration'] = time.time() - start_time
        
        self.logger.info(f"Directory scan completed: {scan_result['total_files']} files found "
                        f"in {scan_result['directories_scanned']} directories "
                        f"({scan_result['scan_duration']:.2f}s)")
        
        return scan_result
    
    def _scan_single_directory(self, directory: str) -> Dict[str, Any]:
        """
        Scan a single directory for media files.
        
        Args:
            directory: Directory path to scan
            
        Returns:
            Dictionary with scan results for the directory
        """
        result = {
            'count': 0,
            'valid_files': [],
            'invalid_files': [],
            'extensions': {},
            'subdirectories': 0
        }
        
        for root, dirs, files in os.walk(directory):
            result['subdirectories'] += len(dirs)
            
            for file in files:
                file_path = os.path.join(root, file)
                file_ext = Path(file).suffix.lower()
                
                if self._is_supported_media_file(file_path):
                    if os.path.isfile(file_path):
                        result['valid_files'].append(file_path)
                        result['count'] += 1
                        result['extensions'][file_ext] = result['extensions'].get(file_ext, 0) + 1
                    else:
                        result['invalid_files'].append(file_path)
                        self.logger.warning(f"Media file path exists but is not a file: {file_path}")
        
        return result
    
    def validateLocalCount(self, media_items: List[MediaItem], expected_count: Optional[int] = None) -> ValidationResult:
        """
        Validate local media count against actual file system state.
        
        Args:
            media_items: List of MediaItem objects to validate
            expected_count: Expected count (if None, uses len(media_items))
            
        Returns:
            ValidationResult with validation details
        """
        self.logger.info(f"Validating local media count for {len(media_items)} items")
        
        validation_start = time.time()
        expected = expected_count if expected_count is not None else len(media_items)
        
        # Scan directories to get actual file count
        scan_result = self.scanLocalDirectories()
        actual_file_count = scan_result['total_files']
        
        # Validate individual media items
        missing_files = []
        invalid_items = []
        valid_count = 0
        
        for item in media_items:
            if not self._validate_media_item_structure(item):
                invalid_items.append(f"Invalid item structure: {getattr(item, 'id', 'unknown')}")
                continue
            
            if item.is_local_available() and hasattr(item, 'local_path') and item.local_path:
                if not os.path.exists(item.local_path) or not os.path.isfile(item.local_path):
                    missing_files.append(item.local_path)
                else:
                    valid_count += 1
            elif item.availability == MediaAvailability.LOCAL_ONLY:
                # Item claims to be local but has no local_path
                invalid_items.append(f"Local item missing path: {item.id}")
        
        # Calculate discrepancy
        discrepancy = expected - actual_file_count
        is_valid = abs(discrepancy) <= 0  # Allow for exact match only
        
        validation_result = ValidationResult(
            is_valid=is_valid,
            expected_count=expected,
            actual_count=actual_file_count,
            discrepancy=discrepancy,
            missing_files=missing_files,
            invalid_items=invalid_items,
            validation_timestamp=time.time(),
            errors=scan_result['errors']
        )
        
        # Log validation results
        if not is_valid:
            self.logger.warning(f"Local count validation failed: expected {expected}, "
                              f"found {actual_file_count} files, discrepancy: {discrepancy}")
        else:
            self.logger.info(f"Local count validation passed: {actual_file_count} files")
        
        # Report discrepancies if found
        if discrepancy != 0 or missing_files or invalid_items:
            self.reportDiscrepancies(
                context="local_count_validation",
                expected=expected,
                actual=actual_file_count,
                details={
                    'missing_files': missing_files,
                    'invalid_items': invalid_items,
                    'scan_errors': scan_result['errors'],
                    'validation_duration': time.time() - validation_start
                }
            )
        
        return validation_result
    
    def validateUnifiedCount(self, local_items: List[MediaItem], remote_items: List[MediaItem], 
                           unified_items: List[MediaItem]) -> ValidationResult:
        """
        Validate unified mode count consistency across local, remote, and unified results.
        
        Args:
            local_items: List of local MediaItem objects
            remote_items: List of remote MediaItem objects  
            unified_items: List of unified MediaItem objects
            
        Returns:
            ValidationResult with consistency validation details
        """
        self.logger.info(f"Validating unified count consistency: "
                        f"local={len(local_items)}, remote={len(remote_items)}, unified={len(unified_items)}")
        
        validation_start = time.time()
        
        # Create sets of item IDs for comparison
        local_ids = {item.id for item in local_items if self._validate_media_item_structure(item)}
        remote_ids = {item.id for item in remote_items if self._validate_media_item_structure(item)}
        unified_ids = {item.id for item in unified_items if self._validate_media_item_structure(item)}
        
        # Calculate expected unified count (union of local and remote)
        expected_unified_ids = local_ids.union(remote_ids)
        expected_count = len(expected_unified_ids)
        actual_count = len(unified_ids)
        
        # Find discrepancies
        missing_from_unified = expected_unified_ids - unified_ids
        extra_in_unified = unified_ids - expected_unified_ids
        
        # Validate individual items
        invalid_items = []
        missing_files = []
        
        for item in unified_items:
            if not self._validate_media_item_structure(item):
                invalid_items.append(f"Invalid unified item: {getattr(item, 'id', 'unknown')}")
                continue
            
            # Check if local items have valid paths
            if item.is_local_available() and hasattr(item, 'local_path') and item.local_path:
                if not os.path.exists(item.local_path):
                    missing_files.append(item.local_path)
        
        discrepancy = expected_count - actual_count
        is_valid = (discrepancy == 0 and 
                   len(missing_from_unified) == 0 and 
                   len(extra_in_unified) == 0 and
                   len(invalid_items) == 0)
        
        validation_result = ValidationResult(
            is_valid=is_valid,
            expected_count=expected_count,
            actual_count=actual_count,
            discrepancy=discrepancy,
            missing_files=missing_files,
            invalid_items=invalid_items,
            validation_timestamp=time.time(),
            errors=[]
        )
        
        # Log validation results
        if not is_valid:
            self.logger.warning(f"Unified count validation failed: expected {expected_count}, "
                              f"got {actual_count}, missing: {len(missing_from_unified)}, "
                              f"extra: {len(extra_in_unified)}")
        else:
            self.logger.info(f"Unified count validation passed: {actual_count} items")
        
        # Report discrepancies
        if not is_valid:
            self.reportDiscrepancies(
                context="unified_count_validation",
                expected=expected_count,
                actual=actual_count,
                details={
                    'missing_from_unified': list(missing_from_unified),
                    'extra_in_unified': list(extra_in_unified),
                    'missing_files': missing_files,
                    'invalid_items': invalid_items,
                    'local_count': len(local_items),
                    'remote_count': len(remote_items),
                    'validation_duration': time.time() - validation_start
                }
            )
        
        return validation_result
    
    def reportDiscrepancies(self, context: str, expected: int, actual: int, details: Dict[str, Any] = None) -> None:
        """
        Report and log media count discrepancies with detailed information.
        
        Args:
            context: Context where discrepancy was found
            expected: Expected count
            actual: Actual count
            details: Additional details about the discrepancy
        """
        difference = expected - actual
        timestamp = time.time()
        
        discrepancy = CountDiscrepancy(
            context=context,
            expected=expected,
            actual=actual,
            difference=difference,
            details=details or {},
            timestamp=timestamp
        )
        
        # Add to discrepancy history
        self._discrepancies.append(discrepancy)
        
        # Limit history size
        if len(self._discrepancies) > self._max_discrepancy_history:
            self._discrepancies = self._discrepancies[-self._max_discrepancy_history:]
        
        # Log the discrepancy
        log_level = logging.ERROR if abs(difference) > 5 else logging.WARNING
        self.logger.log(log_level, 
                       f"Media count discrepancy in {context}: expected {expected}, "
                       f"actual {actual}, difference {difference}")
        
        # Log additional details
        if details:
            if details.get('missing_files'):
                self.logger.warning(f"Missing files ({len(details['missing_files'])}): "
                                  f"{details['missing_files'][:5]}{'...' if len(details['missing_files']) > 5 else ''}")
            
            if details.get('invalid_items'):
                self.logger.warning(f"Invalid items ({len(details['invalid_items'])}): "
                                  f"{details['invalid_items'][:5]}{'...' if len(details['invalid_items']) > 5 else ''}")
            
            if details.get('scan_errors'):
                self.logger.error(f"Scan errors: {details['scan_errors']}")
    
    def _validate_media_item_structure(self, item: MediaItem) -> bool:
        """
        Validate that a MediaItem has the required structure and properties.
        
        Args:
            item: MediaItem to validate
            
        Returns:
            True if item structure is valid, False otherwise
        """
        if not isinstance(item, MediaItem):
            return False
        
        # Check required attributes
        required_attrs = ['id', 'title', 'type', 'availability']
        for attr in required_attrs:
            if not hasattr(item, attr) or getattr(item, attr) is None:
                return False
        
        # Validate availability enum
        if not isinstance(item.availability, MediaAvailability):
            return False
        
        # Validate type enum
        if not isinstance(item.type, MediaType):
            return False
        
        # Check local path if item claims local availability
        if item.is_local_available():
            if not hasattr(item, 'local_path') or not item.local_path:
                return False
        
        return True
    
    def validateMediaItemStructure(self, item: MediaItem) -> bool:
        """
        Validate that a MediaItem has the required structure and properties.
        
        Args:
            item: MediaItem to validate
            
        Returns:
            True if item structure is valid, False otherwise
        """
        return self._validate_media_item_structure(item)
    
    def filterValidMediaItems(self, items: List[MediaItem]) -> List[MediaItem]:
        """
        Filter a list of media items to remove invalid items before counting.
        
        Args:
            items: List of MediaItem objects to filter
            
        Returns:
            List of valid MediaItem objects
        """
        valid_items = []
        invalid_count = 0
        
        for item in items:
            if self.validateMediaItemStructure(item):
                valid_items.append(item)
            else:
                invalid_count += 1
                self.logger.warning(f"Filtered out invalid media item: {getattr(item, 'id', 'unknown')}")
        
        if invalid_count > 0:
            self.logger.info(f"Filtered {invalid_count} invalid items, {len(valid_items)} valid items remain")
        
        return valid_items
    
    def validateMediaItemList(self, items: List[MediaItem]) -> ValidationResult:
        """
        Validate an entire list of media items for structure and consistency.
        
        Args:
            items: List of MediaItem objects to validate
            
        Returns:
            ValidationResult with validation details
        """
        self.logger.info(f"Validating media item list with {len(items)} items")
        
        validation_start = time.time()
        valid_items = []
        invalid_items = []
        missing_files = []
        errors = []
        
        for item in items:
            try:
                if self.validateMediaItemStructure(item):
                    valid_items.append(item)
                    
                    # Additional validation for local items
                    if item.is_local_available() and hasattr(item, 'local_path') and item.local_path:
                        if not os.path.exists(item.local_path):
                            missing_files.append(item.local_path)
                        elif not os.path.isfile(item.local_path):
                            invalid_items.append(f"Local path is not a file: {item.local_path}")
                        elif not self._is_supported_media_file(item.local_path):
                            invalid_items.append(f"Unsupported media file: {item.local_path}")
                else:
                    invalid_items.append(f"Invalid item structure: {getattr(item, 'id', 'unknown')}")
                    
            except Exception as e:
                error_msg = f"Error validating item {getattr(item, 'id', 'unknown')}: {str(e)}"
                errors.append(error_msg)
                self.logger.error(error_msg)
        
        expected_count = len(items)
        actual_count = len(valid_items)
        discrepancy = expected_count - actual_count
        is_valid = discrepancy == 0 and len(missing_files) == 0
        
        validation_result = ValidationResult(
            is_valid=is_valid,
            expected_count=expected_count,
            actual_count=actual_count,
            discrepancy=discrepancy,
            missing_files=missing_files,
            invalid_items=invalid_items,
            validation_timestamp=time.time(),
            errors=errors
        )
        
        # Log results
        if not is_valid:
            self.logger.warning(f"Media item list validation failed: {len(invalid_items)} invalid items, "
                              f"{len(missing_files)} missing files")
        else:
            self.logger.info(f"Media item list validation passed: {actual_count} valid items")
        
        # Report discrepancies if found
        if not is_valid:
            self.reportDiscrepancies(
                context="media_item_list_validation",
                expected=expected_count,
                actual=actual_count,
                details={
                    'invalid_items': invalid_items,
                    'missing_files': missing_files,
                    'validation_errors': errors,
                    'validation_duration': time.time() - validation_start
                }
            )
        
        return validation_result
    
    def _is_supported_media_file(self, file_path: str) -> bool:
        """
        Check if a file is a supported media file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            True if supported, False otherwise
        """
        return Path(file_path).suffix.lower() in self.SUPPORTED_EXTENSIONS
    
    def get_discrepancy_history(self) -> List[CountDiscrepancy]:
        """
        Get the history of count discrepancies.
        
        Returns:
            List of CountDiscrepancy objects
        """
        return self._discrepancies.copy()
    
    def clear_discrepancy_history(self) -> None:
        """Clear the discrepancy history."""
        self._discrepancies.clear()
        self.logger.info("Discrepancy history cleared")