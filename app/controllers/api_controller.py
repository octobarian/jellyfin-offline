"""
API Controller

Handles REST API endpoints for media operations, status, and playback control.
Provides JSON responses for the web interface and external integrations.
"""
from flask import Blueprint, jsonify, request, current_app, send_from_directory, Response
import logging
import os
from typing import Dict, Any, List
import time
import json

from ..services.media_count_validator import MediaCountValidator, ValidationResult

api_bp = Blueprint('api', __name__)
logger = logging.getLogger(__name__)


def _handle_validation_failure(validation_result: ValidationResult, context: str, 
                              loading_metadata: Dict[str, Any], media_items: List,
                              count_validator: MediaCountValidator = None) -> List:
    """
    Handle validation failures with comprehensive error logging and fallback behavior.
    
    Args:
        validation_result: The failed validation result
        context: Context where validation failed (e.g., 'local', 'remote', 'unified')
        loading_metadata: Loading metadata dictionary to update with error info
        media_items: Original media items list
        
    Returns:
        Filtered list of valid media items
    """
    logger.error(f"Media count validation failed in {context} mode:")
    logger.error(f"  Expected: {validation_result.expected_count}")
    logger.error(f"  Actual: {validation_result.actual_count}")
    logger.error(f"  Discrepancy: {validation_result.discrepancy}")
    
    # Log detailed error information
    if validation_result.missing_files:
        logger.error(f"  Missing files ({len(validation_result.missing_files)}):")
        for i, file_path in enumerate(validation_result.missing_files[:10]):  # Log first 10
            logger.error(f"    {i+1}. {file_path}")
        if len(validation_result.missing_files) > 10:
            logger.error(f"    ... and {len(validation_result.missing_files) - 10} more")
    
    if validation_result.invalid_items:
        logger.error(f"  Invalid items ({len(validation_result.invalid_items)}):")
        for i, item_info in enumerate(validation_result.invalid_items[:10]):  # Log first 10
            logger.error(f"    {i+1}. {item_info}")
        if len(validation_result.invalid_items) > 10:
            logger.error(f"    ... and {len(validation_result.invalid_items) - 10} more")
    
    if validation_result.errors:
        logger.error(f"  Validation errors:")
        for error in validation_result.errors:
            logger.error(f"    - {error}")
    
    # Update loading metadata with detailed error information
    error_details = {
        'validation_failed': True,
        'validation_context': context,
        'expected_count': validation_result.expected_count,
        'actual_count': validation_result.actual_count,
        'discrepancy': validation_result.discrepancy,
        'missing_files_count': len(validation_result.missing_files),
        'invalid_items_count': len(validation_result.invalid_items),
        'validation_errors_count': len(validation_result.errors),
        'validation_timestamp': validation_result.validation_timestamp
    }
    
    # Add to loading metadata
    if 'validation_failures' not in loading_metadata:
        loading_metadata['validation_failures'] = []
    loading_metadata['validation_failures'].append(error_details)
    
    # Add user-friendly error messages
    error_messages = []
    if validation_result.discrepancy != 0:
        error_messages.append(
            f"{context.title()} count mismatch: expected {validation_result.expected_count}, "
            f"found {validation_result.actual_count}"
        )
    
    if validation_result.missing_files:
        error_messages.append(f"{len(validation_result.missing_files)} media files are missing or inaccessible")
    
    if validation_result.invalid_items:
        error_messages.append(f"{len(validation_result.invalid_items)} media items have invalid structure")
    
    if validation_result.errors:
        error_messages.append(f"{len(validation_result.errors)} validation errors occurred")
    
    loading_metadata['errors'].extend(error_messages)
    
    # Implement fallback behavior: filter to valid items only
    try:
        if count_validator is None:
            from ..services.media_count_validator import MediaCountValidator
            media_config = current_app.config.get('MEDIA_CONFIG')
            media_directories = media_config.local_media_paths if media_config else []
            count_validator = MediaCountValidator(media_directories)
        
        filtered_items = count_validator.filterValidMediaItems(media_items)
        
        logger.info(f"Fallback: filtered {len(media_items)} items to {len(filtered_items)} valid items")
        loading_metadata['fallback_applied'] = True
        loading_metadata['original_count'] = len(media_items)
        loading_metadata['filtered_count'] = len(filtered_items)
        
        return filtered_items
        
    except Exception as fallback_error:
        logger.error(f"Fallback filtering failed: {fallback_error}")
        loading_metadata['errors'].append(f"Fallback filtering failed: {str(fallback_error)}")
        # Return original items as last resort
        return media_items


def _create_error_response_with_context(error_message: str, context: Dict[str, Any], 
                                       status_code: int = 500) -> tuple:
    """
    Create a detailed error response with context information.
    
    Args:
        error_message: Main error message
        context: Additional context information
        status_code: HTTP status code
        
    Returns:
        Tuple of (jsonify response, status_code)
    """
    response_data = {
        'error': error_message,
        'media': [],
        'count': 0,
        'loading_phase': 'error',
        'loading_metadata': {
            'local_loading': False,
            'remote_loading': False,
            'local_count': 0,
            'remote_count': 0,
            'errors': [error_message],
            'error_context': context,
            'timestamp': time.time()
        }
    }
    
    return jsonify(response_data), status_code


@api_bp.route('/media')
def get_media_list():
    """
    Get media library list with support for different modes.
    
    Query Parameters:
        mode (str): Loading mode - 'local', 'remote', or 'unified' (default: 'unified')
        force_refresh (bool): Force refresh of cached data
        validate_files (bool): Force file existence validation for local mode (default: true)
        
    Returns:
        JSON response with media list and metadata including loading phase indicators
    """
    try:
        media_manager = current_app.config.get('MEDIA_MANAGER')
        if not media_manager:
            return jsonify({
                'error': 'Media services not available',
                'media': [],
                'count': 0,
                'loading_phase': 'error',
                'loading_metadata': {
                    'local_loading': False,
                    'remote_loading': False,
                    'local_count': 0,
                    'remote_count': 0,
                    'errors': ['Media services not available']
                }
            }), 503
        
        # Get query parameters
        mode = request.args.get('mode', 'unified').lower()
        force_refresh = request.args.get('force_refresh', 'false').lower() == 'true'
        validate_files = request.args.get('validate_files', 'true').lower() == 'true'
        
        logger.info(f"Getting media list (mode={mode}, force_refresh={force_refresh}, validate_files={validate_files})")
        
        # Initialize loading metadata
        loading_metadata = {
            'local_loading': False,
            'remote_loading': False,
            'local_count': 0,
            'remote_count': 0,
            'errors': []
        }
        
        media_items = []
        loading_phase = 'complete'
        
        # Initialize MediaCountValidator
        media_config = current_app.config.get('MEDIA_CONFIG')
        media_directories = media_config.local_media_paths if media_config else []
        count_validator = MediaCountValidator(media_directories)
        
        # Handle different modes
        if mode == 'local':
            loading_metadata['local_loading'] = True
            loading_phase = 'loading_local'
            try:
                if hasattr(media_manager, 'get_local_media_with_validation'):
                    result = media_manager.get_local_media_with_validation(force_validation=validate_files)
                    # Handle both tuple and single return value for backward compatibility
                    if isinstance(result, tuple) and len(result) == 2:
                        media_items, validation_metadata = result
                        loading_metadata.update(validation_metadata)
                    else:
                        # Old method that returns only media_items
                        media_items = result
                        loading_metadata['validation_timestamp'] = time.time()
                else:
                    # Fallback to existing method if new method not available yet
                    if hasattr(media_manager, '_get_local_media_items'):
                        media_items = media_manager._get_local_media_items(force_refresh=validate_files)
                        logger.info(f"Got media_items from _get_local_media_items: type={type(media_items)}, len={len(media_items)}")
                        if media_items:
                            logger.info(f"First item type: {type(media_items[0])}")
                    else:
                        # Use the local service directly as another fallback
                        local_items = media_manager.local_service.get_local_media()
                        media_items = media_manager.local_service.to_media_items(local_items)
                        logger.info(f"Got media_items from to_media_items: type={type(media_items)}, len={len(media_items)}")
                        if media_items:
                            logger.info(f"First item type: {type(media_items[0])}")
                
                # Validate local media count using MediaCountValidator
                if validate_files and media_items:
                    logger.info(f"Validating local media count for {len(media_items)} items")
                    try:
                        validation_result = count_validator.validateLocalCount(media_items)
                        
                        # Add validation results to loading metadata
                        loading_metadata.update({
                            'count_validation': {
                                'is_valid': validation_result.is_valid,
                                'expected_count': validation_result.expected_count,
                                'actual_count': validation_result.actual_count,
                                'discrepancy': validation_result.discrepancy,
                                'missing_files_count': len(validation_result.missing_files),
                                'invalid_items_count': len(validation_result.invalid_items),
                                'validation_timestamp': validation_result.validation_timestamp
                            }
                        })
                        
                        # Handle validation failure with comprehensive error handling
                        if not validation_result.is_valid:
                            media_items = _handle_validation_failure(
                                validation_result, 'local', loading_metadata, media_items, count_validator
                            )
                        else:
                            logger.info(f"Local media count validation passed: {len(media_items)} items")
                            
                    except Exception as validation_error:
                        logger.error(f"Local media validation failed with exception: {validation_error}")
                        loading_metadata['errors'].append(f"Validation error: {str(validation_error)}")
                        # Continue with unvalidated items as fallback
                        loading_metadata['validation_skipped'] = True
                
                loading_metadata['local_count'] = len(media_items or [])
                loading_metadata['local_loading'] = False
                loading_phase = 'local_complete'
            except Exception as e:
                logger.error(f"Error loading local media: {e}")
                loading_metadata['errors'].append(f"Local media loading failed: {str(e)}")
                loading_metadata['local_loading'] = False
                loading_phase = 'local_error'
                
        elif mode == 'remote':
            loading_metadata['remote_loading'] = True
            loading_phase = 'loading_remote'
            try:
                if hasattr(media_manager, 'get_remote_media_only'):
                    media_items = media_manager.get_remote_media_only(force_refresh=force_refresh)
                else:
                    # Fallback: get unified list and filter for remote-only items
                    all_items = media_manager.get_unified_media_list(force_refresh=force_refresh)
                    media_items = [item for item in all_items if item.is_remote_available()]
                
                # Validate remote media items structure
                if media_items:
                    logger.info(f"Validating remote media structure for {len(media_items)} items")
                    try:
                        validation_result = count_validator.validateMediaItemList(media_items)
                        
                        # Add validation results to loading metadata
                        loading_metadata.update({
                            'count_validation': {
                                'is_valid': validation_result.is_valid,
                                'expected_count': validation_result.expected_count,
                                'actual_count': validation_result.actual_count,
                                'discrepancy': validation_result.discrepancy,
                                'invalid_items_count': len(validation_result.invalid_items),
                                'validation_timestamp': validation_result.validation_timestamp
                            }
                        })
                        
                        # Handle validation failure with comprehensive error handling
                        if not validation_result.is_valid:
                            media_items = _handle_validation_failure(
                                validation_result, 'remote', loading_metadata, media_items, count_validator
                            )
                        else:
                            logger.info(f"Remote media structure validation passed: {len(media_items)} items")
                            
                    except Exception as validation_error:
                        logger.error(f"Remote media validation failed with exception: {validation_error}")
                        loading_metadata['errors'].append(f"Remote validation error: {str(validation_error)}")
                        # Continue with unvalidated items as fallback
                        loading_metadata['validation_skipped'] = True
                
                loading_metadata['remote_count'] = len(media_items or [])
                loading_metadata['remote_loading'] = False
                loading_phase = 'remote_complete'
            except Exception as e:
                logger.error(f"Error loading remote media: {e}")
                loading_metadata['errors'].append(f"Remote media loading failed: {str(e)}")
                loading_metadata['remote_loading'] = False
                loading_phase = 'remote_error'
                
        else:  # unified mode (default)
            loading_metadata['local_loading'] = True
            loading_metadata['remote_loading'] = True
            loading_phase = 'loading_unified'
            try:
                media_items = media_manager.get_unified_media_list(force_refresh=force_refresh)
                
                # Validate unified results for consistency
                if media_items:
                    logger.info(f"Validating unified media consistency for {len(media_items)} items")
                    
                    try:
                        # Get separate local and remote items for validation
                        local_items = []
                        remote_items = []
                        
                        # Try to get separate lists if available
                        try:
                            if hasattr(media_manager, '_get_local_media_items'):
                                local_result = media_manager._get_local_media_items(force_refresh=validate_files)
                                if isinstance(local_result, list):
                                    local_items = local_result
                            
                            if hasattr(media_manager, 'get_remote_media_only'):
                                remote_result = media_manager.get_remote_media_only(force_refresh=force_refresh)
                                if isinstance(remote_result, list):
                                    remote_items = remote_result
                        except Exception as sep_error:
                            logger.warning(f"Could not get separate local/remote lists for validation: {sep_error}")
                        
                        # If we have separate lists, validate unified consistency
                        if local_items or remote_items:
                            validation_result = count_validator.validateUnifiedCount(
                                local_items, remote_items, media_items
                            )
                            
                            # Add validation results to loading metadata
                            loading_metadata.update({
                                'count_validation': {
                                    'is_valid': validation_result.is_valid,
                                    'expected_count': validation_result.expected_count,
                                    'actual_count': validation_result.actual_count,
                                    'discrepancy': validation_result.discrepancy,
                                    'missing_files_count': len(validation_result.missing_files),
                                    'invalid_items_count': len(validation_result.invalid_items),
                                    'validation_timestamp': validation_result.validation_timestamp,
                                    'local_items_count': len(local_items),
                                    'remote_items_count': len(remote_items)
                                }
                            })
                            
                            # Handle validation failure with comprehensive error handling
                            if not validation_result.is_valid:
                                media_items = _handle_validation_failure(
                                    validation_result, 'unified', loading_metadata, media_items, count_validator
                                )
                            else:
                                logger.info(f"Unified count validation passed: {len(media_items)} items")
                        else:
                            # Fallback: validate just the structure of unified items
                            validation_result = count_validator.validateMediaItemList(media_items)
                            
                            loading_metadata.update({
                                'count_validation': {
                                    'is_valid': validation_result.is_valid,
                                    'expected_count': validation_result.expected_count,
                                    'actual_count': validation_result.actual_count,
                                    'discrepancy': validation_result.discrepancy,
                                    'invalid_items_count': len(validation_result.invalid_items),
                                    'validation_timestamp': validation_result.validation_timestamp
                                }
                            })
                            
                            # Handle validation failure with comprehensive error handling
                            if not validation_result.is_valid:
                                media_items = _handle_validation_failure(
                                    validation_result, 'unified_structure', loading_metadata, media_items, count_validator
                                )
                            else:
                                logger.info(f"Unified structure validation passed: {len(media_items)} items")
                                
                    except Exception as validation_error:
                        logger.error(f"Unified media validation failed with exception: {validation_error}")
                        loading_metadata['errors'].append(f"Unified validation error: {str(validation_error)}")
                        # Continue with unvalidated items as fallback
                        loading_metadata['validation_skipped'] = True
                
                # Count local and remote items for metadata
                for item in media_items or []:
                    if item.is_local_available():
                        loading_metadata['local_count'] += 1
                    if item.is_remote_available():
                        loading_metadata['remote_count'] += 1
                        
                loading_metadata['local_loading'] = False
                loading_metadata['remote_loading'] = False
                loading_phase = 'unified_complete'
            except Exception as e:
                logger.error(f"Error loading unified media: {e}")
                loading_metadata['errors'].append(f"Unified media loading failed: {str(e)}")
                loading_metadata['local_loading'] = False
                loading_metadata['remote_loading'] = False
                loading_phase = 'unified_error'
        
        # Convert to JSON-serializable format
        media_data = []
        media_items = media_items or []  # Ensure we have a list
        
        logger.info(f"Processing {len(media_items)} media items for API response - updated")
        logger.info(f"media_items type: {type(media_items)}")
        if media_items:
            logger.info(f"First item type: {type(media_items[0])}")
        
        # Debug the media_items structure
        logger.error(f"FINAL DEBUG: media_items type: {type(media_items)}, len: {len(media_items)}")
        if media_items:
            logger.error(f"CRITICAL DEBUG: media_items[0] type: {type(media_items[0])}")
            logger.error(f"First item content: {media_items[0]}")
            logger.error(f"First item has thumbnail_url: {hasattr(media_items[0], 'thumbnail_url')}")
            if isinstance(media_items[0], list):
                logger.error(f"ERROR: First item is a list! Content: {media_items[0]}")
                if media_items[0]:
                    logger.error(f"First item's first element: {media_items[0][0]}")
            if hasattr(media_items[0], '__dict__'):
                logger.error(f"First item __dict__: {media_items[0].__dict__}")
        else:
            logger.error("media_items is empty")
        
        # Safety check to prevent the error
        if media_items and not hasattr(media_items[0], 'thumbnail_url'):
            logger.error(f"CRITICAL: media_items contains invalid objects. First item: {media_items[0]}")
            logger.error(f"media_items structure: {[type(item) for item in media_items[:3]]}")
            # Return empty result to prevent crash
            return jsonify({
                'media': [],
                'count': 0,
                'loading_phase': 'error',
                'loading_metadata': {
                    **loading_metadata,
                    'errors': loading_metadata.get('errors', []) + ['Invalid media items structure detected']
                }
            }), 500
        
        if media_items:
            try:
                for item in media_items:
                    # Determine the best poster/thumbnail URL to use
                    poster_url = None
                    logger.info(f"Processing item: {type(item)}, hasattr thumbnail_url: {hasattr(item, 'thumbnail_url')}")
                    thumbnail_url = getattr(item, 'thumbnail_url', None)
                
                    # Debug logging for A Real Pain specifically
                    if hasattr(item, 'title') and getattr(item, 'title', '') == 'A Real Pain':
                        logger.info(f"Processing {getattr(item, 'title', 'Unknown')}: thumbnail_url={thumbnail_url}, has_cached_path={hasattr(item, 'cached_thumbnail_path') and getattr(item, 'cached_thumbnail_path', None)}, is_local_available={getattr(item, 'is_local_available', lambda: False)()}")
                    
                    # Priority 1: Local poster file (for downloaded items)
                    if hasattr(item, 'cached_thumbnail_path') and item.cached_thumbnail_path:
                        # Convert absolute path to web-accessible URL
                        cached_path = item.cached_thumbnail_path.replace(os.sep, '/')
                        if os.path.isabs(item.cached_thumbnail_path):
                            cached_path = os.path.relpath(item.cached_thumbnail_path).replace(os.sep, '/')
                        
                        # Remove leading "media/" if present to avoid double media in URL
                        if cached_path.startswith('media/'):
                            cached_path = cached_path[6:]  # Remove "media/" prefix
                        
                        poster_url = f"/api/static/media/{cached_path}"  # Use API route for media files
                        
                        if item.title == 'A Real Pain':
                            logger.info(f"Using local poster for {item.title}: {poster_url}")
                    
                    # Priority 2: Check if there's a cached thumbnail from the old system
                    elif thumbnail_url and thumbnail_url.startswith('/media/cache/thumbnails/'):
                        # Fix the URL to include the API prefix
                        poster_url = f"/api{thumbnail_url}"
                        
                        if item.title == 'A Real Pain':
                            logger.info(f"Using old cache system for {item.title}: {poster_url}")
                    
                    # Priority 3: For remote URLs, check if we have a cached version
                    elif thumbnail_url and item.is_local_available():
                        # Try to find cached thumbnail for this remote URL
                        # Generate the expected cached filename based on media ID and URL hash
                        import hashlib
                        
                        # Extract jellyfin ID from the thumbnail URL
                        jellyfin_id = None
                        if '/Items/' in thumbnail_url:
                            try:
                                jellyfin_id = thumbnail_url.split('/Items/')[1].split('/')[0]
                            except:
                                pass
                        
                        logger.info(f"Checking cached thumbnail for {item.title}: jellyfin_id={jellyfin_id}, has_local={item.is_local_available()}")
                        
                        if jellyfin_id:
                            url_hash = hashlib.md5(thumbnail_url.encode()).hexdigest()
                            cached_filename = f"jellyfin_{jellyfin_id}_{url_hash}.jpg"
                            cached_path = os.path.join('media', 'cache', 'thumbnails', cached_filename)
                            
                            logger.info(f"Looking for cached file: {cached_path}, exists: {os.path.exists(cached_path)}")
                            
                            if os.path.exists(cached_path):
                                poster_url = f"/api/media/cache/thumbnails/{cached_filename}"
                                logger.info(f"Using cached thumbnail: {poster_url}")
                                if item.title == 'A Real Pain':
                                    logger.info(f"A Real Pain using cached thumbnail: {poster_url}")
                            else:
                                poster_url = thumbnail_url
                                logger.info(f"Cached file not found, using remote URL")
                        else:
                            poster_url = thumbnail_url
                            logger.info(f"Could not extract jellyfin_id from URL: {thumbnail_url}")
                    
                    # Priority 4: Remote thumbnail URL (for streaming-only items)
                    elif thumbnail_url:
                        poster_url = thumbnail_url
                        
                        if item.title == 'A Real Pain':
                            logger.info(f"Using remote URL for {item.title}: {poster_url}")
                    
                    media_data.append({
                        'id': item.id,
                        'title': item.title,
                        'type': item.type.value if item.type else 'unknown',
                        'availability': item.availability.value if item.availability else 'unknown',
                        'year': item.year,
                        'duration': item.duration,
                        'poster_url': poster_url,  # Use poster_url for consistency with frontend
                        'thumbnail_url': getattr(item, 'thumbnail_url', None),  # Keep original for fallback
                        'has_local': item.is_local_available(),
                        'has_remote': item.is_remote_available(),
                        'metadata': item.metadata or {}
                    })
            except Exception as loop_error:
                logger.error(f"Error processing media item: {loop_error}")
                current_item = locals().get('item', 'Unknown')
                logger.error(f"Item causing error: {current_item}")
                logger.error(f"Item type: {type(current_item) if current_item != 'Unknown' else 'Unknown'}")
                raise loop_error
        
        response_data = {
            'media': media_data,
            'count': len(media_data),
            'timestamp': time.time(),
            'loading_phase': loading_phase,
            'loading_metadata': loading_metadata
        }
        
        logger.info(f"Returning {len(media_data)} media items (mode={mode}, phase={loading_phase})")
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Error getting media list: {e}")
        error_context = {
            'mode': mode,
            'force_refresh': force_refresh,
            'validate_files': validate_files,
            'exception_type': type(e).__name__,
            'exception_message': str(e)
        }
        return _create_error_response_with_context(
            'Failed to retrieve media list', error_context, 500
        )


@api_bp.route('/media/<media_id>')
def get_media_details(media_id: str):
    """
    Get detailed information for a specific media item.
    
    Args:
        media_id: Media item identifier
        
    Returns:
        JSON response with media details
    """
    try:
        media_manager = current_app.config.get('MEDIA_MANAGER')
        if not media_manager:
            return jsonify({'error': 'Media services not available'}), 503
        
        logger.info(f"Getting details for media: {media_id}")
        
        media_item = media_manager.get_media_details(media_id)
        if not media_item:
            return jsonify({'error': 'Media item not found'}), 404
        
        # Determine the best poster/thumbnail URL to use
        poster_url = None
        thumbnail_url = media_item.thumbnail_url
        
        # Priority 1: Local poster file (for downloaded items)
        if hasattr(media_item, 'cached_thumbnail_path') and media_item.cached_thumbnail_path:
            # Convert absolute path to web-accessible URL
            cached_path = media_item.cached_thumbnail_path.replace(os.sep, '/')
            if os.path.isabs(media_item.cached_thumbnail_path):
                cached_path = os.path.relpath(media_item.cached_thumbnail_path).replace(os.sep, '/')
            
            # Remove leading "media/" if present to avoid double media in URL
            if cached_path.startswith('media/'):
                cached_path = cached_path[6:]  # Remove "media/" prefix
            
            poster_url = f"/api/static/media/{cached_path}"
        
        # Priority 2: Check if there's a cached thumbnail from the old system
        elif thumbnail_url and thumbnail_url.startswith('/media/cache/thumbnails/'):
            # Fix the URL to include the API prefix
            poster_url = f"/api{thumbnail_url}"
        
        # Priority 3: For remote URLs, check if we have a cached version
        elif thumbnail_url and media_item.is_local_available():
            # Try to find cached thumbnail for this remote URL
            # Generate the expected cached filename based on media ID and URL hash
            import hashlib
            
            # Extract jellyfin ID from the thumbnail URL or use the jellyfin_id field
            jellyfin_id = media_item.jellyfin_id
            if not jellyfin_id and '/Items/' in thumbnail_url:
                try:
                    jellyfin_id = thumbnail_url.split('/Items/')[1].split('/')[0]
                except:
                    pass
            
            if jellyfin_id:
                url_hash = hashlib.md5(thumbnail_url.encode()).hexdigest()
                cached_filename = f"jellyfin_{jellyfin_id}_{url_hash}.jpg"
                cached_path = os.path.join('media', 'cache', 'thumbnails', cached_filename)
                
                if os.path.exists(cached_path):
                    poster_url = f"/api/media/cache/thumbnails/{cached_filename}"
                else:
                    poster_url = thumbnail_url
            else:
                poster_url = thumbnail_url
        
        # Priority 4: Remote thumbnail URL (for streaming-only items)
        elif thumbnail_url:
            poster_url = thumbnail_url
        
        media_data = {
            'id': media_item.id,
            'title': media_item.title,
            'type': media_item.type.value if media_item.type else 'unknown',
            'availability': media_item.availability.value if media_item.availability else 'unknown',
            'year': media_item.year,
            'duration': media_item.duration,
            'poster_url': poster_url,  # Use poster_url for consistency with frontend
            'thumbnail_url': media_item.thumbnail_url,  # Keep original for fallback
            'local_path': media_item.local_path,
            'jellyfin_id': media_item.jellyfin_id,
            'has_local': media_item.is_local_available(),
            'has_remote': media_item.is_remote_available(),
            'metadata': media_item.metadata or {}
        }
        
        return jsonify(media_data)
        
    except Exception as e:
        logger.error(f"Error getting media details for {media_id}: {e}")
        return jsonify({
            'error': 'Failed to retrieve media details',
            'message': str(e)
        }), 500


@api_bp.route('/play/local/<media_id>', methods=['POST'])
def play_local_media(media_id: str):
    """
    Play local media via VLC.
    
    Args:
        media_id: Media item identifier
        
    JSON Body or Form Data:
        fullscreen (bool): Whether to play in fullscreen mode
        
    Returns:
        JSON response with playback status
    """
    try:
        media_manager = current_app.config.get('MEDIA_MANAGER')
        if not media_manager:
            return jsonify({'error': 'Media services not available'}), 503
        
        # Get request data from JSON or form data
        if request.is_json:
            data = request.get_json() or {}
        else:
            data = request.form.to_dict()
        
        fullscreen = data.get('fullscreen', False)
        if isinstance(fullscreen, str):
            fullscreen = fullscreen.lower() in ('true', '1', 'yes')
        
        logger.info(f"Starting local playback: {media_id} (fullscreen={fullscreen})")
        
        success = media_manager.play_local_media(media_id, fullscreen=fullscreen)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Playback started successfully',
                'media_id': media_id,
                'fullscreen': fullscreen
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to start playback',
                'media_id': media_id
            }), 400
        
    except Exception as e:
        logger.error(f"Error starting local playback for {media_id}: {e}")
        return jsonify({
            'success': False,
            'error': 'Playback failed',
            'message': str(e)
        }), 500


@api_bp.route('/play/stream/<media_id>', methods=['POST'])
def stream_media(media_id: str):
    """
    Stream media from Jellyfin via VLC.
    
    Args:
        media_id: Media item identifier
        
    JSON Body or Form Data:
        fullscreen (bool): Whether to play in fullscreen mode
        
    Returns:
        JSON response with streaming status
    """
    try:
        media_manager = current_app.config.get('MEDIA_MANAGER')
        if not media_manager:
            return jsonify({'error': 'Media services not available'}), 503
        
        # Get request data from JSON or form data
        if request.is_json:
            data = request.get_json() or {}
        else:
            data = request.form.to_dict()
        
        fullscreen = data.get('fullscreen', False)
        if isinstance(fullscreen, str):
            fullscreen = fullscreen.lower() in ('true', '1', 'yes')
        
        logger.info(f"Starting stream playback: {media_id} (fullscreen={fullscreen})")
        
        success = media_manager.stream_media(media_id, fullscreen=fullscreen)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Streaming started successfully',
                'media_id': media_id,
                'fullscreen': fullscreen
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to start streaming',
                'media_id': media_id
            }), 400
        
    except Exception as e:
        logger.error(f"Error starting stream playback for {media_id}: {e}")
        return jsonify({
            'success': False,
            'error': 'Streaming failed',
            'message': str(e)
        }), 500


@api_bp.route('/media/directories')
def get_media_directories():
    """
    Get available media directories from configuration.
    
    Returns:
        JSON response with available media directories
    """
    try:
        config = current_app.config.get('MEDIA_CONFIG')
        if not config:
            return jsonify({'error': 'Configuration not available'}), 503
        
        # Get configured media paths
        media_directories = []
        for path in config.local_media_paths:
            # Create directory info
            directory_info = {
                'path': path,
                'name': os.path.basename(path) or path,
                'exists': os.path.exists(path)
            }
            media_directories.append(directory_info)
        
        return jsonify({
            'directories': media_directories,
            'default_download_dir': config.download_directory
        })
        
    except Exception as e:
        logger.error(f"Error getting media directories: {e}")
        return jsonify({
            'error': 'Failed to retrieve media directories',
            'message': str(e)
        }), 500


@api_bp.route('/download/<media_id>', methods=['POST'])
def download_media(media_id: str):
    """
    Download media from Jellyfin to local storage.
    
    Args:
        media_id: Media item identifier
        
    JSON Body or Form Data:
        destination_dir (str): Optional destination directory
        final_destination (str): Optional final destination directory (will move after download)
        
    Returns:
        JSON response with download task information
    """
    try:
        media_manager = current_app.config.get('MEDIA_MANAGER')
        if not media_manager:
            return jsonify({'error': 'Media services not available'}), 503
        
        # Get request data from JSON or form data
        data = {}
        if request.is_json:
            try:
                data = request.get_json() or {}
            except Exception as e:
                logger.warning(f"Failed to parse JSON request body for download {media_id}: {e}")
                data = {}
        else:
            data = request.form.to_dict()
        
        destination_dir = data.get('destination_dir')
        final_destination = data.get('final_destination')
        
        logger.info(f"Download API received data: {data}")
        logger.info(f"Starting download: {media_id} (destination: {destination_dir}, final: {final_destination})")
        
        download_task = media_manager.download_media(media_id, destination_dir, final_destination)
        
        if download_task:
            return jsonify({
                'success': True,
                'message': 'Download started successfully',
                'task_id': download_task.task_id,
                'media_id': download_task.media_id,
                'status': download_task.status.value,
                'progress': download_task.progress,
                'destination_dir': destination_dir,
                'final_destination': final_destination
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to start download',
                'media_id': media_id
            }), 400
        
    except Exception as e:
        logger.error(f"Error starting download for {media_id}: {e}")
        return jsonify({
            'success': False,
            'error': 'Download failed',
            'message': str(e)
        }), 500


@api_bp.route('/downloads')
def get_downloads():
    """
    Get all download tasks and their status.
    
    Returns:
        JSON response with download tasks list
    """
    try:
        media_manager = current_app.config.get('MEDIA_MANAGER')
        if not media_manager:
            return jsonify({'error': 'Media services not available'}), 503
        
        logger.debug("Getting download tasks")
        
        download_tasks = media_manager.get_all_download_tasks()
        
        tasks_data = []
        for task in download_tasks:
            tasks_data.append({
                'task_id': task.task_id,
                'media_id': task.media_id,
                'status': task.status.value,
                'progress': task.progress,
                'file_path': task.file_path,
                'error_message': task.error_message
            })
        
        return jsonify({
            'downloads': tasks_data,
            'count': len(tasks_data)
        })
        
    except Exception as e:
        logger.error(f"Error getting download tasks: {e}")
        return jsonify({
            'error': 'Failed to retrieve download tasks',
            'message': str(e),
            'downloads': [],
            'count': 0
        }), 500


@api_bp.route('/downloads/<task_id>')
def get_download_status(task_id: str):
    """
    Get status of a specific download task.
    
    Args:
        task_id: Download task identifier
        
    Returns:
        JSON response with download task status
    """
    try:
        media_manager = current_app.config.get('MEDIA_MANAGER')
        if not media_manager:
            return jsonify({'error': 'Media services not available'}), 503
        
        logger.debug(f"Getting download status: {task_id}")
        
        download_task = media_manager.get_download_status(task_id)
        
        if not download_task:
            return jsonify({'error': 'Download task not found'}), 404
        
        task_data = {
            'task_id': download_task.task_id,
            'media_id': download_task.media_id,
            'status': download_task.status.value,
            'progress': download_task.progress,
            'file_path': download_task.file_path,
            'error_message': download_task.error_message
        }
        
        return jsonify(task_data)
        
    except Exception as e:
        logger.error(f"Error getting download status for {task_id}: {e}")
        return jsonify({
            'error': 'Failed to retrieve download status',
            'message': str(e)
        }), 500


@api_bp.route('/downloads/<task_id>', methods=['DELETE'])
def cancel_download(task_id: str):
    """
    Cancel a download task.
    
    Args:
        task_id: Download task identifier
        
    Returns:
        JSON response with cancellation status
    """
    try:
        media_manager = current_app.config.get('MEDIA_MANAGER')
        if not media_manager:
            return jsonify({'error': 'Media services not available'}), 503
        
        logger.info(f"Cancelling download: {task_id}")
        
        success = media_manager.cancel_download(task_id)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Download cancelled successfully',
                'task_id': task_id
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to cancel download',
                'task_id': task_id
            }), 400
        
    except Exception as e:
        logger.error(f"Error cancelling download {task_id}: {e}")
        return jsonify({
            'success': False,
            'error': 'Cancellation failed',
            'message': str(e)
        }), 500


@api_bp.route('/download/progress')
def download_progress_stream():
    """
    Server-Sent Events endpoint for real-time download progress updates.
    
    Returns:
        Server-Sent Events stream with download progress data
    """
    # Capture the media manager reference before starting the generator
    media_manager = current_app.config.get('MEDIA_MANAGER')
    app = current_app._get_current_object()
    
    def generate_progress_events():
        """Generate Server-Sent Events for download progress."""
        try:
            if not media_manager:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Media services not available'})}\n\n"
                return
            
            # Send initial connection confirmation
            yield f"data: {json.dumps({'type': 'connected', 'message': 'Download progress stream connected'})}\n\n"
            
            # Continuously send download progress updates
            while True:
                try:
                    with app.app_context():
                        # Get all active download tasks
                        download_tasks = media_manager.get_all_download_tasks()
                        
                        # Send progress for each active task
                        for task in download_tasks:
                            if task.is_active() or task.is_finished():
                                progress_data = {
                                    'type': 'progress',
                                    'task_id': task.task_id,
                                    'media_id': task.media_id,
                                    'status': task.status.value,
                                    'progress': task.progress * 100,  # Convert to percentage for frontend
                                    'file_path': task.file_path,
                                    'error_message': task.error_message
                                }
                                # Debug logging to see what progress is being sent
                                if task.is_active():
                                    logger.debug(f"Sending progress to UI: {task.progress * 100:.1f}% for task {task.task_id}")
                                yield f"data: {json.dumps(progress_data)}\n\n"
                        
                        # Send heartbeat to keep connection alive
                        yield f"data: {json.dumps({'type': 'heartbeat', 'timestamp': time.time()})}\n\n"
                    
                    # Wait before next update (reduced for more responsive UI)
                    time.sleep(0.2)
                    
                except Exception as e:
                    logger.error(f"Error in download progress stream: {e}")
                    yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
                    time.sleep(5)  # Wait longer on error
                    
        except Exception as e:
            logger.error(f"Fatal error in download progress stream: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': f'Stream error: {str(e)}'})}\n\n"
    
    return Response(
        generate_progress_events(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*'
        }
    )


@api_bp.route('/media/local')
def get_local_media_list():
    """
    Get local media library with file existence validation.
    
    Query Parameters:
        validate_files (bool): Force file existence validation (default: true)
        
    Returns:
        JSON response with validated local media list and metadata
    """
    try:
        media_manager = current_app.config.get('MEDIA_MANAGER')
        if not media_manager:
            return jsonify({
                'error': 'Media services not available',
                'media': [],
                'count': 0,
                'validation_metadata': {
                    'validation_timestamp': None,
                    'missing_files_count': 0
                }
            }), 503
        
        # Get query parameters
        validate_files = request.args.get('validate_files', 'true').lower() == 'true'
        
        logger.info(f"Getting local media list (validate_files={validate_files})")
        
        # Get local media with validation
        if hasattr(media_manager, 'get_local_media_with_validation'):
            logger.info("Using get_local_media_with_validation method")
            result = media_manager.get_local_media_with_validation(force_validation=validate_files)
            logger.info(f"get_local_media_with_validation returned: {type(result)}")
            
            # Handle both tuple and single return value for backward compatibility
            if isinstance(result, tuple) and len(result) == 2:
                media_items, validation_metadata = result
            else:
                # Old method that returns only media_items
                media_items = result
                validation_metadata = {
                    'validation_timestamp': time.time(),
                    'missing_files_count': 0
                }
        else:
            # Fallback to existing method if new method not available yet
            logger.info("Using _get_local_media_items fallback method")
            media_items = media_manager._get_local_media_items(force_refresh=validate_files)
            validation_metadata = {
                'validation_timestamp': time.time(),
                'missing_files_count': 0
            }
        
        # Ensure media_items is always a list
        if not isinstance(media_items, list):
            logger.error(f"Expected list of media items, got {type(media_items)}: {media_items}")
            media_items = [media_items] if media_items else []
        
        # Convert to JSON-serializable format
        media_data = []
        for item in media_items:
            # Determine the best poster/thumbnail URL to use
            poster_url = None
            thumbnail_url = item.thumbnail_url
            
            # Priority 1: Local poster file (for downloaded items)
            if hasattr(item, 'cached_thumbnail_path') and item.cached_thumbnail_path:
                # Convert absolute path to web-accessible URL
                cached_path = item.cached_thumbnail_path.replace(os.sep, '/')
                if os.path.isabs(item.cached_thumbnail_path):
                    cached_path = os.path.relpath(item.cached_thumbnail_path).replace(os.sep, '/')
                
                # Remove leading "media/" if present to avoid double media in URL
                if cached_path.startswith('media/'):
                    cached_path = cached_path[6:]  # Remove "media/" prefix
                
                poster_url = f"/api/static/media/{cached_path}"
            
            # Priority 2: Check if there's a cached thumbnail from the old system
            elif thumbnail_url and thumbnail_url.startswith('/media/cache/thumbnails/'):
                # Fix the URL to include the API prefix
                poster_url = f"/api{thumbnail_url}"
            
            # Priority 3: For remote URLs, check if we have a cached version
            elif thumbnail_url and item.is_local_available():
                # Try to find cached thumbnail for this remote URL
                import hashlib
                
                # Extract jellyfin ID from the thumbnail URL
                jellyfin_id = None
                if '/Items/' in thumbnail_url:
                    try:
                        jellyfin_id = thumbnail_url.split('/Items/')[1].split('/')[0]
                    except:
                        pass
                
                if jellyfin_id:
                    url_hash = hashlib.md5(thumbnail_url.encode()).hexdigest()
                    cached_filename = f"jellyfin_{jellyfin_id}_{url_hash}.jpg"
                    cached_path = os.path.join('media', 'cache', 'thumbnails', cached_filename)
                    
                    if os.path.exists(cached_path):
                        poster_url = f"/api/media/cache/thumbnails/{cached_filename}"
                    else:
                        poster_url = thumbnail_url
                else:
                    poster_url = thumbnail_url
            
            # Priority 4: Remote thumbnail URL (for streaming-only items)
            elif thumbnail_url:
                poster_url = thumbnail_url
            
            media_data.append({
                'id': item.id,
                'title': item.title,
                'type': item.type.value if item.type else 'unknown',
                'availability': item.availability.value if item.availability else 'unknown',
                'year': item.year,
                'duration': item.duration,
                'poster_url': poster_url,
                'thumbnail_url': item.thumbnail_url,
                'has_local': item.is_local_available(),
                'has_remote': item.is_remote_available(),
                'metadata': item.metadata or {},
                'file_validated': getattr(item, 'file_validated', False),
                'validation_timestamp': getattr(item, 'validation_timestamp', 0)
            })
        
        response_data = {
            'media': media_data,
            'count': len(media_data),
            'timestamp': time.time(),
            'validation_metadata': validation_metadata
        }
        
        logger.info(f"Returning {len(media_data)} local media items")
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Error getting local media list: {e}")
        return jsonify({
            'error': 'Failed to retrieve local media list',
            'message': str(e),
            'media': [],
            'count': 0,
            'validation_metadata': {
                'validation_timestamp': None,
                'missing_files_count': 0
            }
        }), 500


@api_bp.route('/tv-shows')
def get_tv_shows_list():
    """
    Get TV shows aggregated into show/season/episode hierarchy.

    Query Parameters:
        mode (str): Loading mode - 'local', 'remote', or 'unified' (default: 'unified')
        force_refresh (bool): Force refresh of cached data

    Returns:
        JSON response with TV shows hierarchy and metadata
    """
    try:
        media_manager = current_app.config.get('MEDIA_MANAGER')
        if not media_manager:
            return jsonify({
                'error': 'Media services not available',
                'tv_shows': [],
                'count': 0
            }), 503

        # Get query parameters
        mode = request.args.get('mode', 'unified').lower()
        force_refresh = request.args.get('force_refresh', 'false').lower() == 'true'

        logger.info(f"Getting TV shows list (mode={mode}, force_refresh={force_refresh})")

        # Get media items based on mode
        if mode == 'local':
            if hasattr(media_manager, 'get_local_media_with_validation'):
                result = media_manager.get_local_media_with_validation(force_validation=force_refresh)
                media_items, _ = result if isinstance(result, tuple) else (result, {})
            else:
                media_items = media_manager._get_local_media_items(force_refresh)
        elif mode == 'remote':
            media_items = media_manager.get_remote_media_only(force_refresh)
        else:  # unified
            media_items = media_manager.get_unified_media_list(force_refresh)

        # Import and use TV show aggregator
        from app.services.tv_show_aggregator import TVShowAggregator
        aggregator = TVShowAggregator()

        # Aggregate episodes into TV shows
        tv_shows = aggregator.aggregate_episodes_to_shows(media_items)

        # Convert to dictionaries for JSON serialization
        tv_shows_data = [show.to_dict() for show in tv_shows]

        response_data = {
            'tv_shows': tv_shows_data,
            'count': len(tv_shows_data),
            'timestamp': time.time(),
            'mode': mode
        }

        logger.info(f"Returning {len(tv_shows_data)} TV shows")
        return jsonify(response_data)

    except Exception as e:
        logger.error(f"Error getting TV shows list: {e}")
        return jsonify({
            'error': 'Failed to retrieve TV shows list',
            'message': str(e),
            'tv_shows': [],
            'count': 0
        }), 500


@api_bp.route('/media/remote')
def get_remote_media_list():
    """
    Get remote media library from Jellyfin.
    
    Query Parameters:
        force_refresh (bool): Force refresh of cached data (default: false)
        
    Returns:
        JSON response with remote media list
    """
    try:
        media_manager = current_app.config.get('MEDIA_MANAGER')
        if not media_manager:
            return jsonify({
                'error': 'Media services not available',
                'media': [],
                'count': 0
            }), 503
        
        # Get query parameters
        force_refresh = request.args.get('force_refresh', 'false').lower() == 'true'
        
        logger.info(f"Getting remote media list (force_refresh={force_refresh})")
        
        # Get remote media only
        if hasattr(media_manager, 'get_remote_media_only'):
            media_items = media_manager.get_remote_media_only(force_refresh=force_refresh)
        else:
            # Fallback to existing method if new method not available yet
            media_items = media_manager._get_remote_media_items(force_refresh=force_refresh)
        
        # Convert to JSON-serializable format
        media_data = []
        for item in media_items:
            # Determine the best poster/thumbnail URL to use
            poster_url = None
            thumbnail_url = item.thumbnail_url
            
            # Priority 1: Local poster file (for downloaded items)
            if hasattr(item, 'cached_thumbnail_path') and item.cached_thumbnail_path:
                # Convert absolute path to web-accessible URL
                cached_path = item.cached_thumbnail_path.replace(os.sep, '/')
                if os.path.isabs(item.cached_thumbnail_path):
                    cached_path = os.path.relpath(item.cached_thumbnail_path).replace(os.sep, '/')
                
                # Remove leading "media/" if present to avoid double media in URL
                if cached_path.startswith('media/'):
                    cached_path = cached_path[6:]  # Remove "media/" prefix
                
                poster_url = f"/api/static/media/{cached_path}"
            
            # Priority 2: Check if there's a cached thumbnail from the old system
            elif thumbnail_url and thumbnail_url.startswith('/media/cache/thumbnails/'):
                # Fix the URL to include the API prefix
                poster_url = f"/api{thumbnail_url}"
            
            # Priority 3: For remote URLs, check if we have a cached version
            elif thumbnail_url:
                # Try to find cached thumbnail for this remote URL
                import hashlib
                
                # Extract jellyfin ID from the thumbnail URL
                jellyfin_id = None
                if '/Items/' in thumbnail_url:
                    try:
                        jellyfin_id = thumbnail_url.split('/Items/')[1].split('/')[0]
                    except:
                        pass
                
                if jellyfin_id:
                    url_hash = hashlib.md5(thumbnail_url.encode()).hexdigest()
                    cached_filename = f"jellyfin_{jellyfin_id}_{url_hash}.jpg"
                    cached_path = os.path.join('media', 'cache', 'thumbnails', cached_filename)
                    
                    if os.path.exists(cached_path):
                        poster_url = f"/api/media/cache/thumbnails/{cached_filename}"
                    else:
                        poster_url = thumbnail_url
                else:
                    poster_url = thumbnail_url
            
            media_data.append({
                'id': item.id,
                'title': item.title,
                'type': item.type.value if item.type else 'unknown',
                'availability': item.availability.value if item.availability else 'unknown',
                'year': item.year,
                'duration': item.duration,
                'poster_url': poster_url,
                'thumbnail_url': item.thumbnail_url,
                'has_local': item.is_local_available(),
                'has_remote': item.is_remote_available(),
                'metadata': item.metadata or {}
            })
        
        response_data = {
            'media': media_data,
            'count': len(media_data),
            'timestamp': time.time()
        }
        
        logger.info(f"Returning {len(media_data)} remote media items")
        return jsonify(response_data)
        
    except Exception as e:
        logger.error(f"Error getting remote media list: {e}")
        
        # Handle Jellyfin connection errors gracefully
        error_message = str(e)
        if 'connection' in error_message.lower() or 'timeout' in error_message.lower():
            return jsonify({
                'error': 'Remote media service unavailable',
                'message': 'Unable to connect to Jellyfin server',
                'media': [],
                'count': 0,
                'service_status': 'unavailable'
            }), 503
        elif 'authentication' in error_message.lower() or 'unauthorized' in error_message.lower():
            return jsonify({
                'error': 'Remote media service authentication failed',
                'message': 'Jellyfin authentication error',
                'media': [],
                'count': 0,
                'service_status': 'authentication_error'
            }), 401
        else:
            return jsonify({
                'error': 'Failed to retrieve remote media list',
                'message': error_message,
                'media': [],
                'count': 0,
                'service_status': 'error'
            }), 500


@api_bp.route('/status/fast')
def get_fast_status():
    """
    Get essential status information quickly (< 2 seconds).
    Only checks critical services needed for immediate UI display.
    
    Returns:
        JSON response with fast status information
    """
    import socket
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    try:
        start_time = time.time()
        media_manager = current_app.config.get('MEDIA_MANAGER')
        config = current_app.config.get('MEDIA_CONFIG')
        
        # Initialize enhanced fast status data structure with detailed service reporting
        status_data = {
            'timestamp': time.time(),
            'request_id': f"fast_status_{int(time.time() * 1000)}",
            'services': {
                'internet': {
                    'connected': False,
                    'check_duration': 0,
                    'method': None,
                    'status': 'unknown',
                    'last_check': time.time()
                },
                'jellyfin': {
                    'connected': False,
                    'check_duration': 0,
                    'server_url': config.jellyfin_server_url if config else None,
                    'skipped': False,
                    'status': 'unknown',
                    'last_check': time.time(),
                    'error_message': None
                },
                'local_media': {
                    'available': False,
                    'count': 0,
                    'status': 'unknown',
                    'last_check': time.time(),
                    'paths': config.local_media_paths if config else []
                },
                'media_manager': {
                    'available': media_manager is not None,
                    'status': 'available' if media_manager else 'unavailable'
                },
                'configuration': {
                    'available': config is not None,
                    'status': 'loaded' if config else 'missing'
                }
            },
            'system_health': {
                'overall_status': 'unknown',
                'warnings': [],
                'last_successful_operations': {}
            },
            'services_ready': False,
            'check_duration': 0
        }
        
        def check_internet_connectivity():
            """Fast internet connectivity check with multiple fallback methods."""
            internet_start = time.time()
            
            # Method 1: DNS resolution (fastest)
            try:
                socket.setdefaulttimeout(2)
                socket.gethostbyname('8.8.8.8')
                duration = time.time() - internet_start
                return True, duration, 'dns'
            except:
                pass
            
            # Method 2: HTTP request to reliable endpoint
            try:
                response = requests.get('http://httpbin.org/status/200', timeout=2)
                if response.status_code == 200:
                    duration = time.time() - internet_start
                    return True, duration, 'http'
            except:
                pass
            
            # Method 3: Socket connection test
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(('8.8.8.8', 53))
                sock.close()
                if result == 0:
                    duration = time.time() - internet_start
                    return True, duration, 'socket'
            except:
                pass
            
            duration = time.time() - internet_start
            return False, duration, 'failed'
        
        def check_jellyfin_lightweight():
            """Lightweight Jellyfin connectivity check."""
            jellyfin_start = time.time()
            
            if not media_manager or not config or not config.jellyfin_server_url:
                return False, time.time() - jellyfin_start
            
            try:
                # Quick ping to public info endpoint (no auth required)
                from urllib.parse import urljoin
                public_url = urljoin(config.jellyfin_server_url, '/System/Info/Public')
                response = requests.get(public_url, timeout=3)
                connected = response.status_code == 200
                duration = time.time() - jellyfin_start
                return connected, duration
            except:
                duration = time.time() - jellyfin_start
                return False, duration
        
        def check_local_media_count():
            """Quick local media availability check."""
            if not media_manager:
                return False, 0
            
            try:
                local_media = media_manager.local_service.get_local_media()
                return True, len(local_media)
            except:
                return False, 0
        
        # Run checks in parallel with timeout
        with ThreadPoolExecutor(max_workers=3) as executor:
            # Submit all checks
            internet_future = executor.submit(check_internet_connectivity)
            jellyfin_future = executor.submit(check_jellyfin_lightweight)
            local_future = executor.submit(check_local_media_count)
            
            # Collect results with enhanced timeout handling and detailed status reporting
            try:
                # Internet check with detailed status reporting
                internet_connected, internet_duration, internet_method = internet_future.result(timeout=3)
                status_data['services']['internet'].update({
                    'connected': internet_connected,
                    'check_duration': internet_duration,
                    'method': internet_method,
                    'status': 'connected' if internet_connected else 'disconnected'
                })
                
                if internet_connected:
                    status_data['system_health']['last_successful_operations']['internet_check'] = time.time()
                else:
                    status_data['system_health']['warnings'].append('No internet connectivity detected')
                    
            except Exception as e:
                status_data['services']['internet'].update({
                    'connected': False,
                    'check_duration': 3.0,
                    'method': 'timeout',
                    'status': 'timeout',
                    'error_message': str(e)
                })
                status_data['system_health']['warnings'].append('Internet connectivity check timed out')
            
            # Jellyfin check with enhanced error handling (only if internet is available)
            if status_data['services']['internet']['connected']:
                try:
                    jellyfin_connected, jellyfin_duration = jellyfin_future.result(timeout=2)
                    status_data['services']['jellyfin'].update({
                        'connected': jellyfin_connected,
                        'check_duration': jellyfin_duration,
                        'status': 'connected' if jellyfin_connected else 'connection_failed'
                    })
                    
                    if jellyfin_connected:
                        status_data['system_health']['last_successful_operations']['jellyfin_check'] = time.time()
                    else:
                        status_data['system_health']['warnings'].append('Jellyfin server is not responding')
                        
                except Exception as e:
                    status_data['services']['jellyfin'].update({
                        'connected': False,
                        'check_duration': 2.0,
                        'status': 'timeout',
                        'error_message': str(e)
                    })
                    status_data['system_health']['warnings'].append('Jellyfin connectivity check timed out')
            else:
                status_data['services']['jellyfin'].update({
                    'skipped': True,
                    'check_duration': 0,
                    'status': 'skipped_no_internet'
                })
            
            # Local media check with enhanced status reporting
            try:
                local_available, local_count = local_future.result(timeout=1)
                status_data['services']['local_media'].update({
                    'available': local_available,
                    'count': local_count,
                    'status': 'available' if local_available else 'no_media_found'
                })
                
                if local_available:
                    status_data['system_health']['last_successful_operations']['local_media_check'] = time.time()
                elif local_count == 0:
                    status_data['system_health']['warnings'].append('No local media files found')
                    
            except Exception as e:
                status_data['services']['local_media'].update({
                    'available': False,
                    'count': 0,
                    'status': 'error',
                    'error_message': str(e)
                })
                status_data['system_health']['warnings'].append('Local media check failed')
        
        # Calculate overall system health and readiness
        critical_services_healthy = (
            status_data['services']['media_manager']['available'] and
            status_data['services']['configuration']['available']
        )
        
        if not critical_services_healthy:
            status_data['system_health']['overall_status'] = 'critical'
        elif len(status_data['system_health']['warnings']) > 2:
            status_data['system_health']['overall_status'] = 'degraded'
        elif len(status_data['system_health']['warnings']) > 0:
            status_data['system_health']['overall_status'] = 'warning'
        else:
            status_data['system_health']['overall_status'] = 'healthy'
        
        # Legacy services_ready field for backward compatibility
        status_data['services_ready'] = (
            status_data['services']['local_media']['available'] and
            (status_data['services']['jellyfin']['connected'] or not status_data['services']['internet']['connected'])
        )
        
        # Record total check duration
        status_data['check_duration'] = time.time() - start_time
        
        # Determine appropriate HTTP status code
        http_status = 200
        if status_data['system_health']['overall_status'] == 'critical':
            http_status = 503
        elif status_data['system_health']['overall_status'] == 'degraded':
            http_status = 206
        
        logger.info(f"Fast status check completed in {status_data['check_duration']:.2f}s - Overall: {status_data['system_health']['overall_status']}")
        return jsonify(status_data), http_status
        
    except Exception as e:
        logger.error(f"Critical error in fast status check: {e}")
        return jsonify({
            'error': 'Fast status check failed',
            'message': str(e),
            'timestamp': time.time(),
            'request_id': f"fast_status_error_{int(time.time() * 1000)}",
            'system_health': {
                'overall_status': 'critical',
                'warnings': [f'Fast status check failure: {str(e)}']
            },
            'services': {
                'media_manager': {'available': False, 'status': 'unknown'},
                'configuration': {'available': False, 'status': 'unknown'},
                'internet': {'connected': False, 'status': 'unknown'},
                'jellyfin': {'connected': False, 'status': 'unknown'},
                'local_media': {'available': False, 'status': 'unknown'}
            },
            'check_duration': time.time() - start_time if 'start_time' in locals() else 0
        }), 500


@api_bp.route('/status/background')
def get_background_status():
    """
    Get comprehensive status information for background monitoring.
    Includes detailed service checks and performance metrics with server-side caching.
    
    Returns:
        JSON response with comprehensive status information
    """
    try:
        start_time = time.time()
        media_manager = current_app.config.get('MEDIA_MANAGER')
        config = current_app.config.get('MEDIA_CONFIG')
        
        # Check for cached status (TTL: 30 seconds for background checks)
        cache_key = 'background_status_cache'
        cached_status = getattr(current_app, cache_key, None)
        cache_timestamp = getattr(current_app, f'{cache_key}_timestamp', 0)
        
        if cached_status and (time.time() - cache_timestamp) < 30:
            logger.debug("Returning cached background status")
            cached_status['from_cache'] = True
            cached_status['cache_age'] = time.time() - cache_timestamp
            return jsonify(cached_status)
        
        # Initialize comprehensive status data
        status_data = {
            'timestamp': time.time(),
            'services': {
                'media_manager': media_manager is not None,
                'configuration': config is not None,
                'internet': {
                    'connected': False,
                    'check_duration': 0,
                    'quality': 'unknown',  # excellent, good, poor
                    'methods_tested': []
                },
                'jellyfin': {
                    'connected': False,
                    'authenticated': False,
                    'server_url': config.jellyfin_server_url if config else None,
                    'server_name': None,
                    'check_duration': 0,
                    'last_error': None
                },
                'vlc': {
                    'installed': False,
                    'path': config.vlc_path if config else None,
                    'version': None
                },
                'local_media': {
                    'available': False,
                    'paths': config.local_media_paths if config else [],
                    'scan_duration': 0
                }
            },
            'statistics': {
                'total_media': 0,
                'local_media': 0,
                'remote_media': 0,
                'active_downloads': 0,
                'failed_downloads': 0
            },
            'performance': {
                'total_check_duration': 0,
                'average_response_time': 0,
                'failed_checks': 0,
                'successful_checks': 0
            },
            'from_cache': False
        }
        
        # Detailed internet connectivity check with quality assessment
        def check_internet_detailed():
            internet_start = time.time()
            methods_tested = []
            quality_scores = []
            
            # Test multiple endpoints for reliability assessment
            test_endpoints = [
                ('http://httpbin.org/status/200', 'httpbin'),
                ('https://www.google.com', 'google'),
                ('https://1.1.1.1', 'cloudflare')
            ]
            
            successful_tests = 0
            total_response_time = 0
            
            for url, name in test_endpoints:
                try:
                    test_start = time.time()
                    response = requests.get(url, timeout=5)
                    test_duration = time.time() - test_start
                    
                    if response.status_code in [200, 301, 302]:
                        successful_tests += 1
                        total_response_time += test_duration
                        
                        # Quality scoring based on response time
                        if test_duration < 1:
                            quality_scores.append(3)  # excellent
                        elif test_duration < 3:
                            quality_scores.append(2)  # good
                        else:
                            quality_scores.append(1)  # poor
                    
                    methods_tested.append({
                        'endpoint': name,
                        'success': response.status_code in [200, 301, 302],
                        'duration': test_duration,
                        'status_code': response.status_code
                    })
                except Exception as e:
                    methods_tested.append({
                        'endpoint': name,
                        'success': False,
                        'duration': time.time() - test_start if 'test_start' in locals() else 0,
                        'error': str(e)
                    })
            
            # Determine overall quality
            if successful_tests == 0:
                quality = 'offline'
                connected = False
            elif successful_tests == len(test_endpoints):
                avg_quality = sum(quality_scores) / len(quality_scores)
                if avg_quality >= 2.5:
                    quality = 'excellent'
                elif avg_quality >= 1.5:
                    quality = 'good'
                else:
                    quality = 'poor'
                connected = True
            else:
                quality = 'degraded'
                connected = True
            
            avg_response_time = total_response_time / successful_tests if successful_tests > 0 else 0
            total_duration = time.time() - internet_start
            
            return connected, quality, methods_tested, avg_response_time, total_duration
        
        # Detailed Jellyfin check with authentication status
        def check_jellyfin_detailed():
            jellyfin_start = time.time()
            
            if not media_manager or not config or not config.jellyfin_server_url:
                return False, False, None, None, 0, "Configuration not available"
            
            try:
                # Use the existing comprehensive test_connection method
                conn_status = media_manager.jellyfin_service.test_connection()
                duration = time.time() - jellyfin_start
                
                # Extract server name if available
                server_name = None
                if conn_status.connected:
                    try:
                        from urllib.parse import urljoin
                        info_url = urljoin(config.jellyfin_server_url, '/System/Info/Public')
                        response = requests.get(info_url, timeout=5)
                        if response.status_code == 200:
                            server_info = response.json()
                            server_name = server_info.get('ServerName', 'Unknown')
                    except:
                        pass
                
                return (
                    conn_status.connected,
                    conn_status.connected,  # If connected, assume authenticated
                    server_name,
                    conn_status.error_message,
                    duration,
                    None
                )
                
            except Exception as e:
                duration = time.time() - jellyfin_start
                return False, False, None, None, duration, str(e)
        
        # Enhanced local media check with scan timing
        def check_local_media_detailed():
            scan_start = time.time()
            
            if not media_manager:
                return False, 0, time.time() - scan_start
            
            try:
                local_media = media_manager.local_service.get_local_media()
                scan_duration = time.time() - scan_start
                return True, len(local_media), scan_duration
            except Exception as e:
                scan_duration = time.time() - scan_start
                logger.warning(f"Local media scan failed: {e}")
                return False, 0, scan_duration
        
        # Run detailed checks
        try:
            # Internet connectivity check
            (internet_connected, internet_quality, methods_tested, 
             avg_response_time, internet_duration) = check_internet_detailed()
            
            status_data['services']['internet']['connected'] = internet_connected
            status_data['services']['internet']['quality'] = internet_quality
            status_data['services']['internet']['methods_tested'] = methods_tested
            status_data['services']['internet']['check_duration'] = internet_duration
            status_data['performance']['average_response_time'] = avg_response_time
            
            # Jellyfin check (only if internet is available)
            if internet_connected:
                (jellyfin_connected, jellyfin_authenticated, server_name, 
                 error_message, jellyfin_duration, jellyfin_error) = check_jellyfin_detailed()
                
                status_data['services']['jellyfin']['connected'] = jellyfin_connected
                status_data['services']['jellyfin']['authenticated'] = jellyfin_authenticated
                status_data['services']['jellyfin']['server_name'] = server_name
                status_data['services']['jellyfin']['check_duration'] = jellyfin_duration
                status_data['services']['jellyfin']['last_error'] = jellyfin_error or error_message
            
            # VLC check
            if media_manager:
                status_data['services']['vlc']['installed'] = media_manager.vlc_controller.is_vlc_installed()
            
            # Local media check
            local_available, local_count, scan_duration = check_local_media_detailed()
            status_data['services']['local_media']['available'] = local_available
            status_data['services']['local_media']['scan_duration'] = scan_duration
            
            # Get comprehensive statistics
            if media_manager:
                try:
                    unified_media = media_manager.get_unified_media_list()
                    comparison = media_manager.compare_media_libraries()
                    download_tasks = media_manager.get_all_download_tasks()
                    
                    status_data['statistics']['total_media'] = len(unified_media)
                    status_data['statistics']['local_media'] = comparison.total_local
                    status_data['statistics']['remote_media'] = comparison.total_remote
                    status_data['statistics']['active_downloads'] = len([t for t in download_tasks if t.is_active()])
                    status_data['statistics']['failed_downloads'] = len([t for t in download_tasks if hasattr(t, 'status') and t.status.value == 'failed'])
                except Exception as e:
                    logger.warning(f"Error getting statistics: {e}")
            
        except Exception as e:
            logger.error(f"Error during background status checks: {e}")
            status_data['services']['internet']['connected'] = False
            status_data['services']['jellyfin']['last_error'] = str(e)
        
        # Calculate performance metrics
        total_duration = time.time() - start_time
        status_data['performance']['total_check_duration'] = total_duration
        
        # Count successful vs failed checks
        successful_checks = sum([
            1 if status_data['services']['internet']['connected'] else 0,
            1 if status_data['services']['jellyfin']['connected'] else 0,
            1 if status_data['services']['local_media']['available'] else 0,
            1 if status_data['services']['vlc']['installed'] else 0
        ])
        failed_checks = 4 - successful_checks
        
        status_data['performance']['successful_checks'] = successful_checks
        status_data['performance']['failed_checks'] = failed_checks
        
        # Cache the results
        setattr(current_app, cache_key, status_data.copy())
        setattr(current_app, f'{cache_key}_timestamp', time.time())
        
        logger.info(f"Background status check completed in {total_duration:.2f}s")
        return jsonify(status_data)
        
    except Exception as e:
        logger.error(f"Error in background status check: {e}")
        return jsonify({
            'error': 'Background status check failed',
            'message': str(e),
            'timestamp': time.time(),
            'performance': {
                'total_check_duration': time.time() - start_time if 'start_time' in locals() else 0
            }
        }), 500


@api_bp.route('/status')
def get_system_status():
    """
    Get comprehensive system status with enhanced error handling and detailed service reporting.

    Query Parameters:
        skip_jellyfin (bool): If true, skip Jellyfin connection test to reduce server load
        jellyfin_skip (bool): Alternative parameter name for skip_jellyfin (for backward compatibility)
        timeout (int): Maximum timeout for status checks in seconds (default: 10)

    Returns:
        JSON response with system status information including detailed service status,
        connection timing, and actionable error messages for troubleshooting
    """
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
    
    try:
        start_time = time.time()
        media_manager = current_app.config.get('MEDIA_MANAGER')
        config = current_app.config.get('MEDIA_CONFIG')
        
        # Parse parameters with better handling
        skip_jellyfin_param = request.args.get('skip_jellyfin', request.args.get('jellyfin_skip', 'false'))
        skip_jellyfin = skip_jellyfin_param.lower() in ('true', '1', 'yes')
        timeout = min(int(request.args.get('timeout', '10')), 30)  # Cap at 30 seconds
        
        logger.info(f"Status request: skip_jellyfin={skip_jellyfin}, timeout={timeout}s")

        # Initialize enhanced status data structure with detailed service status reporting
        status_data = {
            'timestamp': time.time(),
            'request_id': f"status_{int(time.time() * 1000)}",
            'services': {
                'media_manager': {
                    'available': media_manager is not None,
                    'status': 'available' if media_manager else 'unavailable',
                    'last_check': time.time()
                },
                'configuration': {
                    'available': config is not None,
                    'status': 'loaded' if config else 'missing',
                    'last_check': time.time()
                },
                'jellyfin': {
                    'connected': False,
                    'authenticated': False,
                    'server_url': config.jellyfin_server_url if config else None,
                    'skipped_check': skip_jellyfin,
                    'check_duration': 0,
                    'error_message': None,
                    'error_type': None,
                    'last_successful_connection': None,
                    'response_time_ms': None,
                    'status': 'unknown',
                    'troubleshooting_hints': []
                },
                'vlc': {
                    'installed': False,
                    'path': config.vlc_path if config else None,
                    'check_duration': 0,
                    'error_message': None,
                    'status': 'unknown',
                    'last_check': time.time()
                },
                'local_media': {
                    'available': False,
                    'paths': config.local_media_paths if config else [],
                    'count': 0,
                    'check_duration': 0,
                    'error_message': None,
                    'status': 'unknown',
                    'last_scan': None,
                    'scan_errors': []
                }
            },
            'statistics': {
                'total_media': 0,
                'local_media': 0,
                'remote_media': 0,
                'active_downloads': 0,
                'failed_downloads': 0,
                'last_updated': time.time()
            },
            'performance': {
                'total_check_duration': 0,
                'checks_completed': 0,
                'checks_failed': 0,
                'timeout_seconds': timeout
            },
            'system_health': {
                'overall_status': 'unknown',
                'critical_errors': [],
                'warnings': [],
                'recommendations': []
            }
        }

        if not media_manager:
            logger.warning("Media manager not available - critical system error")
            status_data['services']['media_manager']['status'] = 'critical_error'
            status_data['system_health']['overall_status'] = 'critical'
            status_data['system_health']['critical_errors'].append('Media manager service is not available')
            status_data['system_health']['recommendations'].append('Restart the application to reinitialize services')
            status_data['performance']['total_check_duration'] = time.time() - start_time
            return jsonify(status_data), 503

        # Define enhanced check functions with comprehensive error handling
        def check_jellyfin_with_timeout():
            jellyfin_start = time.time()
            try:
                if skip_jellyfin:
                    logger.debug("Skipping Jellyfin connection test as requested")
                    return {
                        'connected': False,
                        'authenticated': False,
                        'duration': 0,
                        'error_message': "Check skipped by request",
                        'error_type': 'skipped',
                        'status': 'skipped',
                        'response_time_ms': None,
                        'troubleshooting_hints': ['Connection test was skipped - use skip_jellyfin=false to test connection']
                    }
                
                # Use the enhanced connection test that returns ConnectionStatus object
                conn_status = media_manager.jellyfin_service.test_connection()
                duration = time.time() - jellyfin_start
                
                # Safely convert ConnectionStatus to dict to avoid JSON serialization errors
                if hasattr(conn_status, 'to_dict'):
                    conn_dict = conn_status.to_dict()
                else:
                    # Fallback for older ConnectionStatus objects
                    conn_dict = {
                        'connected': getattr(conn_status, 'connected', False),
                        'authenticated': getattr(conn_status, 'authenticated', False),
                        'error_message': getattr(conn_status, 'error_message', None),
                        'error_type': getattr(conn_status, 'error_type', None),
                        'response_time_ms': getattr(conn_status, 'response_time_ms', None),
                        'user_id': getattr(conn_status, 'user_id', None),
                        'server_info': getattr(conn_status, 'server_info', {})
                    }
                
                # Determine status and add troubleshooting hints
                if conn_dict['connected'] and conn_dict['authenticated']:
                    status = 'healthy'
                    hints = ['Jellyfin connection is working properly']
                elif conn_dict['connected'] and not conn_dict['authenticated']:
                    status = 'authentication_failed'
                    hints = [
                        'Server is reachable but authentication failed',
                        'Check API key and username in configuration',
                        'Verify user has proper permissions on Jellyfin server'
                    ]
                elif not conn_dict['connected']:
                    status = 'connection_failed'
                    hints = [
                        'Cannot connect to Jellyfin server',
                        'Check server URL and network connectivity',
                        'Verify Jellyfin server is running and accessible'
                    ]
                else:
                    status = 'unknown'
                    hints = ['Connection status could not be determined']
                
                return {
                    'connected': conn_dict['connected'],
                    'authenticated': conn_dict['authenticated'],
                    'duration': duration,
                    'error_message': conn_dict['error_message'],
                    'error_type': conn_dict['error_type'],
                    'status': status,
                    'response_time_ms': conn_dict['response_time_ms'],
                    'troubleshooting_hints': hints,
                    'user_id': conn_dict.get('user_id'),
                    'server_info': conn_dict.get('server_info', {})
                }
                
            except Exception as e:
                duration = time.time() - jellyfin_start
                logger.error(f"Jellyfin check failed with exception: {e}")
                return {
                    'connected': False,
                    'authenticated': False,
                    'duration': duration,
                    'error_message': str(e),
                    'error_type': 'exception',
                    'status': 'error',
                    'response_time_ms': None,
                    'troubleshooting_hints': [
                        f'Jellyfin service check failed: {str(e)}',
                        'Check application logs for detailed error information',
                        'Verify Jellyfin service configuration'
                    ]
                }

        def check_vlc_with_timeout():
            vlc_start = time.time()
            try:
                installed = media_manager.vlc_controller.is_vlc_installed()
                duration = time.time() - vlc_start
                
                status = 'available' if installed else 'not_installed'
                error_msg = None if installed else 'VLC media player is not installed or not found'
                
                return {
                    'installed': installed,
                    'duration': duration,
                    'error_message': error_msg,
                    'status': status
                }
            except Exception as e:
                duration = time.time() - vlc_start
                logger.error(f"VLC check failed: {e}")
                return {
                    'installed': False,
                    'duration': duration,
                    'error_message': str(e),
                    'status': 'error'
                }

        def check_local_media_with_timeout():
            local_start = time.time()
            try:
                local_media = media_manager.local_service.get_local_media()
                duration = time.time() - local_start
                
                # Get additional local media information
                scan_errors = []
                last_scan = getattr(media_manager.local_service, 'last_scan_time', None)
                
                status = 'available' if local_media else 'no_media_found'
                if not config or not config.local_media_paths:
                    status = 'no_paths_configured'
                    scan_errors.append('No local media paths configured')
                
                return {
                    'available': len(local_media) > 0,
                    'count': len(local_media),
                    'duration': duration,
                    'error_message': None,
                    'status': status,
                    'last_scan': last_scan,
                    'scan_errors': scan_errors
                }
            except Exception as e:
                duration = time.time() - local_start
                logger.error(f"Local media check failed: {e}")
                return {
                    'available': False,
                    'count': 0,
                    'duration': duration,
                    'error_message': str(e),
                    'status': 'error',
                    'last_scan': None,
                    'scan_errors': [str(e)]
                }

        def get_statistics_with_timeout():
            stats_start = time.time()
            try:
                # Use cached data if available to improve performance
                unified_media = media_manager.get_unified_media_list()
                comparison = media_manager.compare_media_libraries()
                download_tasks = media_manager.get_all_download_tasks()
                
                stats = {
                    'total_media': len(unified_media),
                    'local_media': comparison.total_local,
                    'remote_media': comparison.total_remote,
                    'active_downloads': len([t for t in download_tasks if t.is_active()]),
                    'failed_downloads': len([t for t in download_tasks if hasattr(t, 'status') and t.status.value == 'failed']),
                    'last_updated': time.time()
                }
                duration = time.time() - stats_start
                return stats, duration, None
            except Exception as e:
                duration = time.time() - stats_start
                logger.error(f"Statistics gathering failed: {e}")
                return None, duration, str(e)

        # Run checks in parallel with enhanced timeout handling
        with ThreadPoolExecutor(max_workers=4) as executor:
            # Submit all checks
            jellyfin_future = executor.submit(check_jellyfin_with_timeout)
            vlc_future = executor.submit(check_vlc_with_timeout)
            local_future = executor.submit(check_local_media_with_timeout)
            stats_future = executor.submit(get_statistics_with_timeout)
            
            checks_completed = 0
            checks_failed = 0
            
            # Collect Jellyfin results with comprehensive error handling
            try:
                jellyfin_result = jellyfin_future.result(timeout=timeout/2)
                status_data['services']['jellyfin'].update({
                    'connected': jellyfin_result['connected'],
                    'authenticated': jellyfin_result['authenticated'],
                    'check_duration': jellyfin_result['duration'],
                    'error_message': jellyfin_result['error_message'],
                    'error_type': jellyfin_result['error_type'],
                    'status': jellyfin_result['status'],
                    'response_time_ms': jellyfin_result['response_time_ms'],
                    'troubleshooting_hints': jellyfin_result['troubleshooting_hints']
                })
                
                # Set last successful connection timestamp if connected
                if jellyfin_result['connected']:
                    status_data['services']['jellyfin']['last_successful_connection'] = time.time()
                
                checks_completed += 1
            except FutureTimeoutError:
                timeout_msg = f"Jellyfin check timed out after {timeout/2}s"
                status_data['services']['jellyfin'].update({
                    'error_message': timeout_msg,
                    'error_type': 'timeout',
                    'check_duration': timeout/2,
                    'status': 'timeout',
                    'troubleshooting_hints': [
                        'Jellyfin server is not responding within timeout period',
                        'Check server availability and network connectivity',
                        'Consider increasing timeout parameter'
                    ]
                })
                status_data['system_health']['warnings'].append(timeout_msg)
                checks_failed += 1
            except Exception as e:
                error_msg = f"Jellyfin check failed: {str(e)}"
                status_data['services']['jellyfin'].update({
                    'error_message': error_msg,
                    'error_type': 'exception',
                    'status': 'error',
                    'troubleshooting_hints': [
                        f'Unexpected error during Jellyfin check: {str(e)}',
                        'Check application logs for detailed error information'
                    ]
                })
                status_data['system_health']['critical_errors'].append(error_msg)
                checks_failed += 1

            # Collect VLC results with enhanced error handling
            try:
                vlc_result = vlc_future.result(timeout=2)
                status_data['services']['vlc'].update({
                    'installed': vlc_result['installed'],
                    'check_duration': vlc_result['duration'],
                    'error_message': vlc_result['error_message'],
                    'status': vlc_result['status']
                })
                
                if not vlc_result['installed']:
                    status_data['system_health']['warnings'].append('VLC media player is not installed')
                    status_data['system_health']['recommendations'].append('Install VLC media player for local playback support')
                
                checks_completed += 1
            except FutureTimeoutError:
                timeout_msg = "VLC check timed out after 2s"
                status_data['services']['vlc'].update({
                    'check_duration': 2,
                    'error_message': timeout_msg,
                    'status': 'timeout'
                })
                status_data['system_health']['warnings'].append(timeout_msg)
                checks_failed += 1
            except Exception as e:
                error_msg = f"VLC check failed: {str(e)}"
                status_data['services']['vlc'].update({
                    'error_message': error_msg,
                    'status': 'error'
                })
                status_data['system_health']['warnings'].append(error_msg)
                checks_failed += 1

            # Collect local media results with enhanced error handling
            try:
                local_result = local_future.result(timeout=3)
                status_data['services']['local_media'].update({
                    'available': local_result['available'],
                    'count': local_result['count'],
                    'check_duration': local_result['duration'],
                    'error_message': local_result['error_message'],
                    'status': local_result['status'],
                    'last_scan': local_result['last_scan'],
                    'scan_errors': local_result['scan_errors']
                })
                
                if local_result['scan_errors']:
                    status_data['system_health']['warnings'].extend(local_result['scan_errors'])
                
                if not local_result['available'] and local_result['status'] != 'no_paths_configured':
                    status_data['system_health']['recommendations'].append('Check local media paths and file permissions')
                
                checks_completed += 1
            except FutureTimeoutError:
                timeout_msg = "Local media check timed out after 3s"
                status_data['services']['local_media'].update({
                    'check_duration': 3,
                    'error_message': timeout_msg,
                    'status': 'timeout'
                })
                status_data['system_health']['warnings'].append(timeout_msg)
                checks_failed += 1
            except Exception as e:
                error_msg = f"Local media check failed: {str(e)}"
                status_data['services']['local_media'].update({
                    'error_message': error_msg,
                    'status': 'error'
                })
                status_data['system_health']['warnings'].append(error_msg)
                checks_failed += 1

            # Collect statistics with enhanced error handling
            try:
                stats, stats_duration, stats_error = stats_future.result(timeout=timeout/2)
                if stats:
                    status_data['statistics'].update(stats)
                if stats_error:
                    logger.warning(f"Statistics error: {stats_error}")
                    status_data['system_health']['warnings'].append(f"Statistics gathering error: {stats_error}")
                checks_completed += 1
            except FutureTimeoutError:
                timeout_msg = f"Statistics gathering timed out after {timeout/2}s"
                logger.warning(timeout_msg)
                status_data['system_health']['warnings'].append(timeout_msg)
                checks_failed += 1
            except Exception as e:
                error_msg = f"Statistics gathering failed: {str(e)}"
                logger.error(error_msg)
                status_data['system_health']['warnings'].append(error_msg)
                checks_failed += 1

        # Calculate overall system health with comprehensive assessment
        jellyfin_ready = skip_jellyfin or status_data['services']['jellyfin']['connected']
        
        # Determine overall system status
        critical_services_healthy = (
            status_data['services']['media_manager']['available'] and
            status_data['services']['configuration']['available']
        )
        
        if not critical_services_healthy:
            status_data['system_health']['overall_status'] = 'critical'
        elif checks_failed > checks_completed:
            status_data['system_health']['overall_status'] = 'degraded'
        elif len(status_data['system_health']['warnings']) > 0:
            status_data['system_health']['overall_status'] = 'warning'
        else:
            status_data['system_health']['overall_status'] = 'healthy'
        
        # Legacy services_ready field for backward compatibility
        status_data['services_ready'] = (
            status_data['services']['media_manager']['available'] and
            status_data['services']['configuration']['available'] and
            jellyfin_ready and
            status_data['services']['vlc']['installed'] and
            status_data['services']['local_media']['available']
        )

        # Add system-wide recommendations based on service status
        if not jellyfin_ready and not skip_jellyfin:
            status_data['system_health']['recommendations'].append('Fix Jellyfin connectivity for remote media access')
        
        if not status_data['services']['vlc']['installed']:
            status_data['system_health']['recommendations'].append('Install VLC for local media playback')
        
        if not status_data['services']['local_media']['available']:
            status_data['system_health']['recommendations'].append('Configure local media paths or add media files')

        # Update performance metrics
        total_duration = time.time() - start_time
        status_data['performance']['total_check_duration'] = total_duration
        status_data['performance']['checks_completed'] = checks_completed
        status_data['performance']['checks_failed'] = checks_failed

        # Determine appropriate HTTP status code based on system health
        http_status = 200
        if status_data['system_health']['overall_status'] == 'critical':
            http_status = 503  # Service Unavailable
        elif status_data['system_health']['overall_status'] == 'degraded':
            http_status = 206  # Partial Content
        
        logger.info(f"Status check completed in {total_duration:.2f}s ({checks_completed}/{checks_completed + checks_failed} checks successful) - Overall: {status_data['system_health']['overall_status']}")
        
        return jsonify(status_data), http_status

    except Exception as e:
        total_duration = time.time() - start_time if 'start_time' in locals() else 0
        logger.error(f"Critical error in system status endpoint: {e}")
        
        # Return comprehensive error response with troubleshooting information
        error_response = {
            'error': 'System status check failed',
            'message': str(e),
            'timestamp': time.time(),
            'request_id': f"status_error_{int(time.time() * 1000)}",
            'system_health': {
                'overall_status': 'critical',
                'critical_errors': [f'Status endpoint failure: {str(e)}'],
                'troubleshooting_hints': [
                    'Check application logs for detailed error information',
                    'Verify all services are properly initialized',
                    'Restart the application if the error persists'
                ]
            },
            'performance': {
                'total_check_duration': total_duration,
                'checks_completed': 0,
                'checks_failed': 1,
                'error_occurred_at': time.time()
            },
            'services': {
                'media_manager': {'available': False, 'status': 'unknown'},
                'configuration': {'available': False, 'status': 'unknown'},
                'jellyfin': {'connected': False, 'status': 'unknown'},
                'vlc': {'installed': False, 'status': 'unknown'},
                'local_media': {'available': False, 'status': 'unknown'}
            }
        }
        
        return jsonify(error_response), 500


@api_bp.route('/sync', methods=['POST'])
def sync_libraries():
    """
    Synchronize local and remote media libraries.
    
    Returns:
        JSON response with synchronization results
    """
    try:
        media_manager = current_app.config.get('MEDIA_MANAGER')
        if not media_manager:
            return jsonify({'error': 'Media services not available'}), 503
        
        logger.info("Starting library synchronization")
        
        # Get request data to check for sync mode
        if request.is_json:
            data = request.get_json() or {}
        else:
            data = request.form.to_dict()
        
        # Check if this is a request to just set the sync flag for next load
        if data.get('mode') == 'request':
            media_manager.request_jellyfin_sync()
            return jsonify({
                'success': True,
                'message': 'Jellyfin sync requested for next media list retrieval',
                'sync_mode': 'requested'
            })
        
        # Otherwise perform a full synchronization
        sync_result = media_manager.synchronize_libraries()
        
        return jsonify({
            'success': True,
            'message': 'Library synchronization completed',
            'result': sync_result,
            'sync_mode': 'immediate'
        })
        
    except Exception as e:
        logger.error(f"Error synchronizing libraries: {e}")
        return jsonify({
            'success': False,
            'error': 'Synchronization failed',
            'message': str(e)
        }), 500
@api_bp.route('/media/cache/thumbnails/<filename>')
def get_cached_thumbnail(filename):
    """
    Serve cached thumbnail images.
    
    Args:
        filename: Cached thumbnail filename
        
    Returns:
        Image file response
    """
    try:
        cache_dir = os.path.abspath(os.path.join('media', 'cache', 'thumbnails'))
        logger.debug(f"Serving cached thumbnail: {filename} from {cache_dir}")
        
        if not os.path.exists(cache_dir):
            logger.error(f"Cache directory does not exist: {cache_dir}")
            return jsonify({'error': 'Cache directory not found'}), 404
            
        file_path = os.path.join(cache_dir, filename)
        if not os.path.exists(file_path):
            logger.error(f"Cached thumbnail file does not exist: {file_path}")
            return jsonify({'error': 'Thumbnail file not found'}), 404
        
        return send_from_directory(cache_dir, filename)
    except Exception as e:
        logger.error(f"Error serving cached thumbnail {filename}: {e}")
        return jsonify({
            'error': 'Failed to retrieve cached thumbnail',
            'message': str(e)
        }), 404


@api_bp.route('/static/media/<path:filepath>')
def serve_media_file(filepath):
    """
    Serve media files including poster images.
    
    Args:
        filepath: Relative path to the media file
        
    Returns:
        File response
    """
    try:
        # Construct the full path relative to the media directory
        media_path = os.path.join('media', filepath)
        full_path = os.path.abspath(media_path)
        directory = os.path.dirname(full_path)
        filename = os.path.basename(full_path)
        
        # Security check: ensure the path is within the media directory
        media_dir = os.path.abspath('media')
        if not full_path.startswith(media_dir):
            logger.warning(f"Access denied for path outside media directory: {filepath} (full_path: {full_path}, media_dir: {media_dir})")
            return jsonify({'error': 'Access denied'}), 403
        
        # Check if file exists
        if not os.path.exists(full_path):
            logger.warning(f"Media file not found: {full_path}")
            return jsonify({'error': 'File not found'}), 404
        
        return send_from_directory(directory, filename)
    except Exception as e:
        logger.error(f"Error serving media file {filepath}: {e}")
        return jsonify({
            'error': 'Failed to retrieve media file',
            'message': str(e)
        }), 404