"""
Jellyfin API service for the RV Media Player application.
"""
import requests
import time
import logging
import platform # Added for device name
import hashlib # Added for device ID hashing
from typing import List, Optional, Dict, Any, Tuple
from urllib.parse import urljoin, urlparse
import os
import threading
import json
import pickle
from ..models.media_item import MediaItem
from ..models.download_task import DownloadTask
from ..models.enums import MediaType, MediaAvailability, DownloadStatus


logger = logging.getLogger(__name__)


class ConnectionStatus:
    """Represents detailed connection status to Jellyfin server."""
    
    def __init__(self, connected: bool, error_message: Optional[str] = None, 
                 authenticated: bool = False, user_id: Optional[str] = None,
                 server_info: Optional[Dict[str, Any]] = None, 
                 response_time_ms: Optional[float] = None,
                 error_type: Optional[str] = None):
        self.connected = connected
        self.authenticated = authenticated
        self.user_id = user_id
        self.server_info = server_info or {}
        self.error_message = error_message
        self.error_type = error_type  # 'network', 'auth', 'server', 'timeout'
        self.response_time_ms = response_time_ms
        self.timestamp = time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert ConnectionStatus to dictionary for JSON serialization."""
        return {
            'connected': self.connected,
            'authenticated': self.authenticated,
            'user_id': self.user_id,
            'server_info': self.server_info,
            'error_message': self.error_message,
            'error_type': self.error_type,
            'response_time_ms': self.response_time_ms,
            'timestamp': self.timestamp
        }
    
    def __bool__(self) -> bool:
        """Allow ConnectionStatus to be used in boolean contexts."""
        return self.connected


class JellyfinService:
    """
    Service for interacting with Jellyfin media server API.
    
    Provides authentication, media library fetching, streaming URL generation,
    and download functionality with progress tracking.
    """
    
    def __init__(self, server_url: str = None, username: str = None, api_key: str = None):
        """
        Initialize the Jellyfin service.
        
        Args:
            server_url: Jellyfin server URL
            username: Username for authentication
            api_key: API key for authentication
        """
        self.server_url = server_url
        self.username = username
        self.api_key = api_key
        self.user_id = None
        self.authenticated = False  # Initialize authentication state
        self.session = requests.Session()
        self.session.timeout = 30
        self._download_tasks: Dict[str, DownloadTask] = {}
        self._download_threads: Dict[str, threading.Thread] = {}
        self._download_state_file = "media/downloads/.download_state.pkl"
        
        # Load persistent download state
        self._load_download_state()
        
        # Configure session headers (these are base headers, Authorization will be added dynamically)
        self.session.headers.update({
            'User-Agent': 'RV Media Player/1.0',
            'Content-Type': 'application/json',
            'Accept': 'application/json' # Always good to explicitly accept JSON
        })
        
        # Connection retry settings
        self.max_retries = 3
        self.retry_delay = 2.0
        self.backoff_multiplier = 2.0
    
    def authenticate(self, server_url: str, api_key: str, username: Optional[str] = None) -> bool:
        """
        Authenticate with the Jellyfin server using API key and
        then attempt to find the user_id for the given username.

        Args:
            server_url: Jellyfin server URL
            username: Username for authentication (expected to be the user whose media library will be accessed)
            api_key: API key for authentication

        Returns:
            True if authentication successful and user_id found, False otherwise
        """
        logger.info(f"Attempting Jellyfin authentication for server: {server_url} with username: {username}")
        logger.debug(f"API Key (first 8 chars): {api_key[:8] if api_key else 'N/A'}...")

        # Clear previous authentication state at the start
        self._clear_authentication_state()

        if not api_key:
            logger.error("API Key is missing for Jellyfin authentication.")
            return False

        if not server_url:
            logger.error("Server URL is missing for Jellyfin authentication.")
            return False

        try:
            # Store credentials
            self.server_url = server_url.rstrip('/')
            self.username = username
            self.api_key = api_key

            # 1. First, validate the API key by hitting a general server endpoint
            logger.info(f"Step 1: Validating API key with /System/Info")
            system_info_url = urljoin(self.server_url, '/System/Info')
            response = self._make_request('GET', system_info_url, authenticated=True)

            if response is None or response.status_code != 200:
                error_detail = response.text if response else "No response"
                logger.error(f"API key validation failed: HTTP Status {response.status_code if response else 'N/A'}. Response: {error_detail}")
                self._clear_authentication_state()
                return False
            
            logger.info("Jellyfin API key validated successfully using /System/Info.")
            self.authenticated = True  # API key is valid

            # 2. If API key is valid, proceed to get user_id if a username is provided
            if not self.username:
                logger.warning("No username provided. Jellyfin service authenticated for server access, but user-specific media access will not be possible without a user_id.")
                return True  # Server is accessible, but user-specific functions won't work
            
            logger.info(f"Step 2: Fetching user ID for username '{self.username}'")
            users_url = urljoin(self.server_url, '/Users')
            
            users_response = self._make_request('GET', users_url, authenticated=True)

            if users_response is None or users_response.status_code != 200:
                error_detail = users_response.text if users_response else "No response"
                logger.error(f"Failed to fetch user list: HTTP Status {users_response.status_code if users_response else 'N/A'}. Response: {error_detail}")
                self._clear_authentication_state()
                return False

            users_data = users_response.json()
            found_user_id = None
            for user in users_data:
                if user.get('Name', '').lower() == self.username.lower():
                    found_user_id = user.get('Id')
                    break
            
            if found_user_id:
                self.user_id = found_user_id
                logger.info(f"Successfully found user ID '{self.user_id}' for username '{self.username}'.")
                return True
            else:
                logger.error(f"Username '{self.username}' not found on Jellyfin server. Please check your settings.")
                self._clear_authentication_state()
                return False

        except requests.exceptions.RequestException as req_e:
            logger.error(f"Authentication network error: {req_e.__class__.__name__} - {str(req_e)}")
            self._clear_authentication_state()
            return False
        except Exception as e:
            logger.error(f"Authentication error: {e.__class__.__name__} - {str(e)}")
            self._clear_authentication_state()
            return False
    
    def get_media_library(self) -> Tuple[List[MediaItem], Dict[str, Any]]:
        """
        Fetch the media library from Jellyfin server with robust error handling.
        
        Returns:
            Tuple of (List of MediaItem objects, metadata dict with retrieval details)
        """
        if not self._is_authenticated(require_user_id=True):
            error_msg = "Not authenticated with Jellyfin server or user_id not set. Cannot fetch media library."
            logger.error(error_msg)
            return [], {
                'success': False,
                'error': 'Not authenticated or user_id missing',
                'pages_fetched': 0,
                'items_processed': 0,
                'total_expected': 0,
                'retrieval_time_ms': 0,
                'errors': [error_msg]
            }
        
        start_time = time.time()
        logger.info(f"Attempting to fetch media library for user ID: {self.user_id}")
        
        # Initialize metadata tracking
        metadata = {
            'success': False,
            'pages_fetched': 0,
            'items_processed': 0,
            'valid_items': 0,
            'total_expected': 0,
            'retrieval_time_ms': 0,
            'errors': [],
            'warnings': [],
            'retry_attempts': 0,
            'partial_success': False
        }
        
        try:
            media_items = []
            
            # Get all library items with pagination to handle large libraries
            url = urljoin(self.server_url, f'/Users/{self.user_id}/Items')
            
            # Use pagination to get all items
            start_index = 0
            limit = 200  # Reasonable page size
            total_fetched = 0
            total_expected = None
            page_count = 0
            failed_pages = []
            
            logger.info("=== PAGINATION DEBUG: Starting media library retrieval ===")
            
            while True:
                page_count += 1
                params = {
                    'Recursive': 'true',
                    'IncludeItemTypes': 'Movie,Series,Episode',
                    'Fields': 'BasicSyncInfo,MediaSources,Path,Overview,Genres,ProductionYear,RunTimeTicks,ImageTags,ParentThumbItemId,ParentThumbImageTag,ParentPrimaryImageItemId,ParentPrimaryImageTag,SeriesId,SeriesPrimaryImageTag,HasPrimaryImage',
                    'SortBy': 'SortName',
                    'SortOrder': 'Ascending',
                    'StartIndex': start_index,
                    'Limit': limit
                }
                
                logger.info(f"PAGINATION DEBUG: Page {page_count} - Fetching from StartIndex={start_index}, Limit={limit}")
                logger.debug(f"PAGINATION DEBUG: Full URL: {url} with params: {params}")
                
                # Retry logic for individual page requests
                page_success = False
                page_retry_count = 0
                max_page_retries = 3
                
                while not page_success and page_retry_count < max_page_retries:
                    try:
                        response = self._make_request('GET', url, authenticated=True, params=params)
                        
                        if not response:
                            raise requests.exceptions.RequestException("No response received")
                        
                        if response.status_code != 200:
                            raise requests.exceptions.HTTPError(f"HTTP {response.status_code}: {response.text}")
                        
                        page_success = True
                        
                    except (requests.exceptions.RequestException, requests.exceptions.HTTPError) as e:
                        page_retry_count += 1
                        metadata['retry_attempts'] += 1
                        error_msg = f"Page {page_count} attempt {page_retry_count} failed: {str(e)}"
                        logger.warning(f"PAGINATION DEBUG: {error_msg}")
                        metadata['warnings'].append(error_msg)
                        
                        if page_retry_count < max_page_retries:
                            retry_delay = 1.0 * (2 ** (page_retry_count - 1))  # Exponential backoff
                            logger.info(f"PAGINATION DEBUG: Retrying page {page_count} in {retry_delay}s...")
                            time.sleep(retry_delay)
                        else:
                            failed_pages.append(page_count)
                            error_msg = f"Page {page_count} failed after {max_page_retries} attempts"
                            logger.error(f"PAGINATION DEBUG: {error_msg}")
                            metadata['errors'].append(error_msg)
                            break
                
                if not page_success:
                    # If this is the first page, we can't continue
                    if page_count == 1:
                        logger.error("PAGINATION DEBUG: First page failed, cannot continue")
                        metadata['success'] = False
                        metadata['retrieval_time_ms'] = (time.time() - start_time) * 1000
                        return media_items, metadata
                    else:
                        # For subsequent pages, we can continue with partial success
                        logger.warning(f"PAGINATION DEBUG: Skipping failed page {page_count}, continuing with partial results")
                        metadata['partial_success'] = True
                        start_index += limit  # Skip to next page
                        continue
                
                data = response.json()
                items = data.get('Items', [])
                total_count = data.get('TotalRecordCount', 0)
                
                logger.info(f"PAGINATION DEBUG: Page {page_count} response - Items in page: {len(items)}, TotalRecordCount: {total_count}")
                
                if total_expected is None:
                    total_expected = total_count
                    metadata['total_expected'] = total_expected
                    logger.info(f"PAGINATION DEBUG: Set total_expected to {total_expected} from first page response")
                elif total_count != total_expected:
                    warning_msg = f"TotalRecordCount changed from {total_expected} to {total_count} on page {page_count}"
                    logger.warning(f"PAGINATION DEBUG: {warning_msg}")
                    metadata['warnings'].append(warning_msg)
                    total_expected = total_count  # Update to latest count
                    metadata['total_expected'] = total_expected
                
                if not items:
                    logger.info(f"PAGINATION DEBUG: Page {page_count} returned empty items list - stopping pagination")
                    logger.info(f"PAGINATION DEBUG: Final state - total_fetched: {total_fetched}, total_expected: {total_expected}")
                    break
                
                logger.info(f"PAGINATION DEBUG: Page {page_count} - Processing {len(items)} items (StartIndex {start_index} to {start_index + len(items) - 1})")
                
                # Process items from this page
                page_valid_items = 0
                page_conversion_errors = 0
                for i, item in enumerate(items):
                    try:
                        media_item = self._convert_jellyfin_item_to_media_item(item)
                        if media_item:
                            media_items.append(media_item)
                            page_valid_items += 1
                        else:
                            logger.debug(f"PAGINATION DEBUG: Item {i} on page {page_count} converted to None (filtered out)")
                    except Exception as e:
                        page_conversion_errors += 1
                        error_msg = f"Failed to convert item {i} on page {page_count} (Jellyfin ID: {item.get('Id', 'unknown')}): {e.__class__.__name__} - {str(e)}"
                        logger.warning(f"PAGINATION DEBUG: {error_msg}")
                        metadata['warnings'].append(error_msg)
                        continue
                
                total_fetched += len(items)
                metadata['pages_fetched'] = page_count
                metadata['items_processed'] = total_fetched
                metadata['valid_items'] = len(media_items)
                
                if page_conversion_errors > 0:
                    metadata['warnings'].append(f"Page {page_count}: {page_conversion_errors} item conversion errors")
                
                logger.info(f"PAGINATION DEBUG: Page {page_count} complete - Valid items: {page_valid_items}/{len(items)}, Total fetched so far: {total_fetched}/{total_expected}")
                
                # Check pagination termination conditions
                items_less_than_limit = len(items) < limit
                reached_total_expected = total_fetched >= total_expected
                
                logger.info(f"PAGINATION DEBUG: Checking termination conditions:")
                logger.info(f"  - Items in page ({len(items)}) < limit ({limit}): {items_less_than_limit}")
                logger.info(f"  - Total fetched ({total_fetched}) >= total expected ({total_expected}): {reached_total_expected}")
                
                if items_less_than_limit or reached_total_expected:
                    logger.info(f"PAGINATION DEBUG: Terminating pagination after page {page_count}")
                    logger.info(f"PAGINATION DEBUG: Final counts - Fetched: {total_fetched}, Expected: {total_expected}, Valid items: {len(media_items)}")
                    break
                
                # Move to next page
                start_index += limit
                logger.info(f"PAGINATION DEBUG: Moving to next page - new StartIndex: {start_index}")
                
                # Safety check to prevent infinite loops
                if page_count > 1000:  # Reasonable upper bound
                    error_msg = f"Safety break - processed {page_count} pages, stopping to prevent infinite loop"
                    logger.error(f"PAGINATION DEBUG: {error_msg}")
                    metadata['errors'].append(error_msg)
                    break
            
            # Calculate final metadata
            metadata['retrieval_time_ms'] = (time.time() - start_time) * 1000
            metadata['success'] = len(media_items) > 0 or (total_expected == 0)  # Success if we got items or if library is empty
            
            if failed_pages:
                metadata['partial_success'] = True
                metadata['errors'].append(f"Failed to retrieve {len(failed_pages)} pages: {failed_pages}")
            
            logger.info("=== PAGINATION DEBUG: Media library retrieval complete ===")
            logger.info(f"PAGINATION DEBUG: Final summary - Pages: {page_count}, Raw items fetched: {total_fetched}, Valid MediaItems: {len(media_items)}")
            logger.info(f"Processed {len(media_items)} valid media items from Jellyfin (fetched {total_fetched} total items across {page_count} pages)")
            logger.info(f"Retrieval metadata: {metadata}")
            
            return media_items, metadata
            
        except requests.exceptions.RequestException as req_e:
            error_msg = f"Network error fetching media library: {req_e.__class__.__name__} - {str(req_e)}"
            logger.error(error_msg)
            metadata['errors'].append(error_msg)
            metadata['retrieval_time_ms'] = (time.time() - start_time) * 1000
            return media_items, metadata
        except Exception as e:
            error_msg = f"Error fetching media library: {e.__class__.__name__} - {str(e)}"
            logger.error(error_msg)
            metadata['errors'].append(error_msg)
            metadata['retrieval_time_ms'] = (time.time() - start_time) * 1000
            return media_items, metadata
    
    def get_streaming_url(self, media_id: str) -> Optional[str]:
        """
        Generate a streaming URL for VLC playback.
        
        Args:
            media_id: Jellyfin media item ID
            
        Returns:
            Streaming URL or None if failed
        """
        if not self._is_authenticated(require_user_id=True):
            logger.error("Not authenticated with Jellyfin server or user_id not set. Cannot generate streaming URL.")
            return None
        
        logger.info(f"Attempting to generate streaming URL for media ID: {media_id}")
        try:
            # Get media info to determine best stream (optional, but good for richer info)
            url_info = urljoin(self.server_url, f'/Users/{self.user_id}/Items/{media_id}')
            response_info = self._make_request('GET', url_info, authenticated=True)
            
            if not response_info or response_info.status_code != 200:
                logger.error(f"Failed to get media info for streaming {media_id}: {response_info.status_code if response_info else 'No response'}. Response: {response_info.text if response_info else 'N/A'}")
                return None
            
            # Direct stream URL (using api_key in query param as a fallback/alternative,
            # though Authorization header is preferred for other calls)
            # For direct stream, `api_key` in query param is often used by players.
            stream_url = urljoin(
                self.server_url,
                f'/Videos/{media_id}/stream?api_key={self.api_key}&Static=true&UserId={self.user_id}' # Added UserId param
            )
            
            logger.info(f"Generated streaming URL for media {media_id}: {stream_url}")
            return stream_url
            
        except requests.exceptions.RequestException as req_e:
            logger.error(f"Network error generating streaming URL: {req_e.__class__.__name__} - {str(req_e)}")
            return None
        except Exception as e:
            logger.error(f"Error generating streaming URL for {media_id}: {e.__class__.__name__} - {str(e)}")
            return None
    
    def download_media(self, media_id: str, destination: str, completion_callback=None) -> DownloadTask:
        """
        Initiate media download with progress tracking.
        
        Args:
            media_id: Jellyfin media item ID
            destination: Local destination path for download
            completion_callback: Optional callback function to call when download completes
            
        Returns:
            DownloadTask object for tracking progress
        """
        if not self._is_authenticated():
            logger.error("Not authenticated with Jellyfin server. Cannot initiate download.")
            task = DownloadTask(media_id=media_id)
            task.mark_failed("Not authenticated with Jellyfin server")
            return task
        
        logger.info(f"Initiating download for media ID: {media_id} to {destination}")
        
        # Get media info for progress tracking
        media_info = {}
        try:
            media_url = urljoin(self.server_url, f'/Users/{self.user_id}/Items/{media_id}')
            response = self._make_request('GET', media_url, authenticated=True)
            if response and response.status_code == 200:
                media_data = response.json()
                media_info = {
                    'title': media_data.get('Name', 'Unknown'),
                    'type': media_data.get('Type', 'Unknown'),
                    'year': media_data.get('ProductionYear'),
                    'runtime': media_data.get('RunTimeTicks')
                }
        except Exception as e:
            logger.warning(f"Could not fetch media info for {media_id}: {str(e)}")
        
        # Check if this media is already being downloaded
        for existing_task in self._download_tasks.values():
            if existing_task.media_id == media_id and existing_task.is_active():
                logger.info(f"Media {media_id} is already being downloaded (task {existing_task.task_id})")
                return existing_task
        
        # Create download task
        task = DownloadTask(media_id=media_id, file_path=destination)
        # Store completion callback if provided
        if completion_callback:
            task._completion_callback = completion_callback
        self._download_tasks[task.task_id] = task
        
        # Save download state
        self._save_download_state()
        
        # Notify progress tracker
        try:
            from ..api.download_progress import progress_tracker
            progress_tracker.start_download(task.task_id, media_id, media_info)
        except ImportError:
            logger.warning("Progress tracker not available for download notifications")
        
        # Start download in separate thread
        download_thread = threading.Thread(
            target=self._download_worker_with_progress,
            args=(task, media_id, destination),
            daemon=True
        )
        self._download_threads[task.task_id] = download_thread
        download_thread.start()
        
        return task
    
    def get_download_status(self, task_id: str) -> Optional[DownloadTask]:
        """
        Get the status of a download task.
        
        Args:
            task_id: Download task ID
            
        Returns:
            DownloadTask object or None if not found
        """
        return self._download_tasks.get(task_id)
    
    def cancel_download(self, task_id: str) -> bool:
        """
        Cancel a download task.
        
        Args:
            task_id: Download task ID
            
        Returns:
            True if cancelled successfully, False otherwise
        """
        task = self._download_tasks.get(task_id)
        if not task:
            logger.info(f"Download task {task_id} not found for cancellation.")
            return False
        
        if not task.is_active():
            logger.info(f"Download task {task_id} not active for cancellation (status: {task.status}).")
            return False
        
        # Mark task as failed with cancellation message
        task.mark_failed("Download cancelled by user")
        logger.info(f"Download task {task_id} marked for cancellation.")
        
        # Notify progress tracker
        try:
            from ..api.download_progress import progress_tracker
            progress_tracker.cancel_download(task_id)
        except ImportError:
            logger.warning("Progress tracker not available for cancellation notification")
        
        # Try to interrupt the download thread if it exists
        download_thread = self._download_threads.get(task_id)
        if download_thread and download_thread.is_alive():
            logger.debug(f"Download thread for {task_id} is still running, task status should cause it to exit")
            
            # Give the thread a moment to notice the status change and exit gracefully
            import threading
            def cleanup_thread():
                time.sleep(1.0)  # Wait 1 second for graceful exit
                if download_thread.is_alive():
                    logger.warning(f"Download thread for {task_id} did not exit gracefully")
                    # Note: Python doesn't support forceful thread termination
                    # The thread should exit when it checks task.is_active()
            
            cleanup_thread_timer = threading.Thread(target=cleanup_thread, daemon=True)
            cleanup_thread_timer.start()
        
        return True
    
    # Assuming you have an attribute like self.authenticated in your JellyfinService
    # that is set to True upon successful authentication and False otherwise.
    # Also assuming self.client is your authenticated Jellyfin API client or
    # self.authenticated_token stores the API key obtained during authentication.

    def test_connection(self) -> ConnectionStatus:
        """
        Test connection to Jellyfin server with detailed diagnostics.

        Returns:
            ConnectionStatus object with comprehensive connection details
        """
        if not self.server_url:
            logger.warning("No Jellyfin server URL configured for connection test.")
            return ConnectionStatus(
                connected=False, 
                error_message="No server URL configured",
                error_type="config"
            )

        logger.info(f"Testing Jellyfin connection to: {self.server_url}")
        start_time = time.time()
        
        try:
            # Step 1: Test basic server connectivity with public endpoint
            logger.debug("Step 1: Testing basic server connectivity")
            public_url = urljoin(self.server_url, '/System/Info/Public')
            
            try:
                public_response = self._make_request('GET', public_url, timeout=10)
                basic_response_time = (time.time() - start_time) * 1000
                
                if not public_response or public_response.status_code != 200:
                    error_msg = f"Server returned status {public_response.status_code}" if public_response else "No response from server"
                    logger.error(f"Basic connectivity test failed: {error_msg}")
                    return ConnectionStatus(
                        connected=False,
                        error_message=f"Server unreachable: {error_msg}",
                        error_type="server",
                        response_time_ms=basic_response_time
                    )
                
                server_info = public_response.json()
                logger.info(f"Server reachable: {server_info.get('ServerName', 'Unknown')}")
                
            except requests.exceptions.Timeout:
                response_time = (time.time() - start_time) * 1000
                logger.error("Basic connectivity test timed out")
                return ConnectionStatus(
                    connected=False,
                    error_message="Connection timeout",
                    error_type="timeout",
                    response_time_ms=response_time
                )
            except requests.exceptions.ConnectionError as ce:
                response_time = (time.time() - start_time) * 1000
                logger.error(f"Connection refused or network unreachable: {str(ce)}")
                return ConnectionStatus(
                    connected=False,
                    error_message=f"Network error: {str(ce)}",
                    error_type="network",
                    response_time_ms=response_time
                )
            
            # Step 2: Test authentication if we have credentials
            if not self.api_key:
                logger.info("No API key configured - server reachable but not authenticated")
                return ConnectionStatus(
                    connected=True,
                    authenticated=False,
                    server_info=server_info,
                    error_message="No API key configured",
                    error_type="config",
                    response_time_ms=basic_response_time
                )
            
            logger.debug("Step 2: Testing authentication")
            auth_start_time = time.time()
            auth_url = urljoin(self.server_url, '/System/Info')
            
            try:
                auth_response = self._make_request('GET', auth_url, authenticated=True, timeout=10)
                auth_response_time = (time.time() - auth_start_time) * 1000
                
                if not auth_response:
                    logger.error("Authentication test failed - no response")
                    return ConnectionStatus(
                        connected=True,
                        authenticated=False,
                        server_info=server_info,
                        error_message="Authentication failed - no response",
                        error_type="auth",
                        response_time_ms=auth_response_time
                    )
                
                if auth_response.status_code == 401:
                    logger.error("Authentication failed - invalid API key")
                    self._clear_authentication_state()
                    return ConnectionStatus(
                        connected=True,
                        authenticated=False,
                        server_info=server_info,
                        error_message="Invalid API key",
                        error_type="auth",
                        response_time_ms=auth_response_time
                    )
                
                if auth_response.status_code != 200:
                    error_msg = f"Authentication test returned status {auth_response.status_code}"
                    logger.error(error_msg)
                    return ConnectionStatus(
                        connected=True,
                        authenticated=False,
                        server_info=server_info,
                        error_message=error_msg,
                        error_type="server",
                        response_time_ms=auth_response_time
                    )
                
                # Authentication successful
                auth_server_info = auth_response.json()
                logger.info("Authentication successful")
                
                # Step 3: Test user lookup if username is provided
                final_response_time = (time.time() - start_time) * 1000
                
                if not self.username:
                    logger.info("No username provided - authenticated but no user context")
                    return ConnectionStatus(
                        connected=True,
                        authenticated=True,
                        server_info=auth_server_info,
                        error_message="No username configured",
                        error_type="config",
                        response_time_ms=final_response_time
                    )
                
                logger.debug("Step 3: Testing user lookup")
                users_url = urljoin(self.server_url, '/Users')
                users_response = self._make_request('GET', users_url, authenticated=True, timeout=10)
                
                if not users_response or users_response.status_code != 200:
                    error_msg = f"User lookup failed: {users_response.status_code if users_response else 'No response'}"
                    logger.error(error_msg)
                    return ConnectionStatus(
                        connected=True,
                        authenticated=True,
                        server_info=auth_server_info,
                        error_message=error_msg,
                        error_type="server",
                        response_time_ms=final_response_time
                    )
                
                users_data = users_response.json()
                found_user_id = None
                for user in users_data:
                    if user.get('Name', '').lower() == self.username.lower():
                        found_user_id = user.get('Id')
                        break
                
                final_response_time = (time.time() - start_time) * 1000
                
                if found_user_id:
                    logger.info(f"Full authentication successful for user: {self.username}")
                    return ConnectionStatus(
                        connected=True,
                        authenticated=True,
                        user_id=found_user_id,
                        server_info=auth_server_info,
                        response_time_ms=final_response_time
                    )
                else:
                    logger.error(f"Username '{self.username}' not found on server")
                    return ConnectionStatus(
                        connected=True,
                        authenticated=True,
                        server_info=auth_server_info,
                        error_message=f"Username '{self.username}' not found",
                        error_type="auth",
                        response_time_ms=final_response_time
                    )
                    
            except requests.exceptions.Timeout:
                response_time = (time.time() - start_time) * 1000
                logger.error("Authentication test timed out")
                return ConnectionStatus(
                    connected=True,
                    authenticated=False,
                    server_info=server_info,
                    error_message="Authentication timeout",
                    error_type="timeout",
                    response_time_ms=response_time
                )
            except requests.exceptions.ConnectionError as ce:
                response_time = (time.time() - start_time) * 1000
                logger.error(f"Authentication test connection error: {str(ce)}")
                return ConnectionStatus(
                    connected=True,
                    authenticated=False,
                    server_info=server_info,
                    error_message=f"Authentication network error: {str(ce)}",
                    error_type="network",
                    response_time_ms=response_time
                )
                
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            logger.error(f"Unexpected error during connection test: {e.__class__.__name__} - {str(e)}")
            return ConnectionStatus(
                connected=False,
                error_message=f"Unexpected error: {str(e)}",
                error_type="server",
                response_time_ms=response_time
            )

    def get_connection_details(self) -> Dict[str, Any]:
        """
        Get detailed connection status information for debugging.
        
        Returns:
            Dictionary with comprehensive connection details
        """
        return {
            'server_url': self.server_url,
            'username': self.username,
            'has_api_key': bool(self.api_key),
            'authenticated': self.authenticated,
            'user_id': self.user_id,
            'session_timeout': self.session.timeout,
            'max_retries': self.max_retries,
            'retry_delay': self.retry_delay,
            'has_auth_header': 'Authorization' in self.session.headers,
            'timestamp': time.time()
        }

    def _clear_authentication_state(self) -> None:
        """Clear all authentication state and session headers."""
        self.authenticated = False
        self.user_id = None
        # Remove Authorization header from session if it exists
        if 'Authorization' in self.session.headers:
            del self.session.headers['Authorization']
        logger.debug("Authentication state cleared")

    def _is_authenticated(self, require_user_id: bool = False) -> bool:
        """
        Check if service is properly authenticated.

        Args:
            require_user_id: If True, also checks that user_id is set for user-specific operations
        """
        # First check the authenticated flag
        if not self.authenticated:
            logger.debug("Authentication check failed: authenticated flag is False")
            return False

        # Then check required credentials
        required_fields = [self.server_url, self.api_key]
        if not all(required_fields):
            missing = []
            if not self.server_url: missing.append("server_url")
            if not self.api_key: missing.append("api_key")
            logger.debug(f"Authentication check failed. Missing: {', '.join(missing)}")
            return False

        # For user-specific operations, user_id is also required
        if require_user_id and not self.user_id:
            logger.debug("Authentication check failed: user_id is required but not set")
            return False

        return True
            
    def _make_request(self, method: str, url: str, authenticated: bool = False, **kwargs) -> Optional[requests.Response]:
        """
        Make HTTP request with retry logic.

        Args:
            method: HTTP method (e.g., 'GET', 'POST')
            url: Request URL
            authenticated: If True, adds the Authorization header using self.api_key.
                           Defaults to False.
            **kwargs: Additional request parameters (e.g., params, data, json, headers, timeout)

        Returns:
            Response object or None if all retries failed
        """
        last_exception = None
        
        # Create a copy of session headers to modify for this specific request
        # This prevents permanent modification of self.session.headers if not intended
        request_headers = self.session.headers.copy()

        # If authentication is required for this specific call, add the Authorization header
        if authenticated and self.api_key:
            # Use the simpler and more reliable X-Emby-Token header for API key authentication
            # This is the recommended approach for API keys according to Jellyfin documentation
            request_headers['X-Emby-Token'] = self.api_key
            logger.debug(f"Adding X-Emby-Token header for authenticated request to {url}")
        elif authenticated and not self.api_key:
            logger.warning(f"Attempted authenticated request to {url} but no API key is available in service instance.")
            # If no API key, we cannot make an authenticated request, so we might as well fail early
            return None
        
        # Merge any additional headers from kwargs, giving them precedence
        if 'headers' in kwargs:
            request_headers.update(kwargs.pop('headers')) # Pop 'headers' from kwargs to avoid passing twice

        for attempt in range(self.max_retries):
            try:
                logger.debug(f"Making request (Attempt {attempt + 1}/{self.max_retries}): {method} {url}")
                
                # Log headers for debugging, but be careful with sensitive info
                logged_headers = {k: v for k, v in request_headers.items() if k != 'Authorization'}
                if 'Authorization' in request_headers:
                    auth_val = request_headers['Authorization']
                    if 'Token=' in auth_val:
                        logged_headers['Authorization'] = auth_val.split('Token=')[0] + 'Token="***"'
                    else:
                        logged_headers['Authorization'] = '***'
                logger.debug(f"Request headers: {logged_headers}")

                response = self.session.request(method, url, headers=request_headers, **kwargs) # Pass headers explicitly
                logger.debug(f"Received response status: {response.status_code} for {method} {url}")
                
                # Check for 401 Unauthorized specifically for authenticated requests
                if authenticated and response.status_code == 401:
                    logger.error(f"Authentication failed (401 Unauthorized) for {url}. API key might be invalid or expired.")
                    self._clear_authentication_state()
                    # No retry for 401 on authenticated requests, as it's likely a bad token
                    return None

                response.raise_for_status() # Raise HTTPError for other bad responses (4xx or 5xx)
                return response
                
            except requests.exceptions.RequestException as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (self.backoff_multiplier ** attempt)
                    logger.warning(f"Request failed (attempt {attempt + 1}/{self.max_retries}), retrying in {delay}s: {e.__class__.__name__} - {str(e)}")
                    time.sleep(delay)
                else:
                    logger.error(f"Request failed after {self.max_retries} attempts: {e.__class__.__name__} - {str(e)}")
        
        logger.error(f"All {self.max_retries} request attempts failed for {url}.")
        return None
    
    def _convert_jellyfin_item_to_media_item(self, item: Dict[str, Any]) -> Optional[MediaItem]:
        """
        Convert Jellyfin API item to MediaItem.

        Args:
            item: Jellyfin item dictionary

        Returns:
            MediaItem object or None if conversion failed
        """
        try:
            # Determine media type
            item_type = item.get('Type', '').lower()
            if item_type == 'movie':
                media_type = MediaType.MOVIE
            elif item_type == 'series':
                media_type = MediaType.TV_SHOW
            elif item_type == 'episode':
                media_type = MediaType.EPISODE
            else:
                logger.debug(f"Skipping unsupported media type: {item_type} for item ID: {item.get('Id', 'unknown')}")
                return None

            # Extract basic info
            jellyfin_id = item.get('Id')
            title = item.get('Name', 'Unknown Title')
            year = item.get('ProductionYear')

            # Calculate duration from RunTimeTicks (100ns units)
            run_time_ticks = item.get('RunTimeTicks')
            duration = int(run_time_ticks / 10000000) if run_time_ticks else None

            thumbnail_url = None

            # --- REFINED LOGIC FOR THUMBNAIL URL GENERATION ---

            # For Movies and TV Shows, directly check ImageTags for 'Primary' or 'Thumb'
            if media_type in [MediaType.MOVIE, MediaType.TV_SHOW]:
                primary_image_tag = item.get('ImageTags', {}).get('Primary')
                if primary_image_tag:
                    thumbnail_url = urljoin(
                        self.server_url,
                        f'/Items/{jellyfin_id}/Images/Primary?tag={primary_image_tag}&api_key={self.api_key}'
                    )
                    # logger.debug(f"Generated primary image URL for {title} (ID: {jellyfin_id}): {thumbnail_url}")
                else: # Fallback to 'Thumb' if 'Primary' is not found for movies/series
                    thumb_image_tag = item.get('ImageTags', {}).get('Thumb')
                    if thumb_image_tag:
                        thumbnail_url = urljoin(
                            self.server_url,
                            f'/Items/{jellyfin_id}/Images/Thumb?tag={thumb_image_tag}&api_key={self.api_key}'
                        )
                        # logger.debug(f"Generated fallback thumb image URL for {title} (ID: {jellyfin_id}): {thumbnail_url}")

            # For Episodes, the existing logic (checking parent images) is generally correct.
            # We can still add an initial check for episode's own primary/thumb if HasPrimaryImage is reliable for episodes.
            elif media_type == MediaType.EPISODE:
                # First, try the episode's own primary image if it has one and HasPrimaryImage is true
                if item.get('HasPrimaryImage'):
                    primary_image_tag = item.get('ImageTags', {}).get('Primary')
                    if primary_image_tag:
                        thumbnail_url = urljoin(
                            self.server_url,
                            f'/Items/{jellyfin_id}/Images/Primary?tag={primary_image_tag}&api_key={self.api_key}'
                        )
                        # logger.debug(f"Generated episode's own primary image URL for {title} (ID: {jellyfin_id}): {thumbnail_url}")

                # If no episode-specific image, then try parent images (Series, then Season)
                if not thumbnail_url:
                    # Try Series poster first
                    series_id = item.get('SeriesId')
                    series_image_tag = item.get('SeriesPrimaryImageTag') # This tag corresponds to the Series' Primary image
                    if series_id and series_image_tag:
                        thumbnail_url = urljoin(
                            self.server_url,
                            f'/Items/{series_id}/Images/Primary?tag={series_image_tag}&api_key={self.api_key}'
                        )
                        # logger.debug(f"Generated series primary image URL for episode {title} (Series ID: {series_id}): {thumbnail_url}")

                    # Fallback: Try Season primary image (could be a poster or a thumbnail)
                    if not thumbnail_url:
                        season_id = item.get('SeasonId')
                        season_primary_image_tag = item.get('ParentPrimaryImageTag') 
                        if season_id and season_primary_image_tag:
                            thumbnail_url = urljoin(
                                self.server_url,
                                f'/Items/{season_id}/Images/Primary?tag={season_primary_image_tag}&api_key={self.api_key}'
                            )
                            # logger.debug(f"Generated season primary image URL for episode {title} (Season ID: {season_id}): {thumbnail_url}")
                        
                        # Fallback: Try Season thumbnail
                        if not thumbnail_url:
                            season_thumb_tag = item.get('ParentThumbImageTag')
                            if season_id and season_thumb_tag:
                                thumbnail_url = urljoin(
                                    self.server_url,
                                    f'/Items/{season_id}/Images/Thumb?tag={season_thumb_tag}&api_key={self.api_key}'
                                )
                                # logger.debug(f"Generated season thumbnail URL for episode {title} (Season ID: {season_id}): {thumbnail_url}")

            # If still no thumbnail, log a warning (optional)
            if not thumbnail_url:
                logger.warning(f"No thumbnail URL generated for item: {title} (ID: {jellyfin_id}, Type: {item_type})")

            # --- END REFINED LOGIC FOR THUMBNAIL URL GENERATION ---

            # Create MediaItem
            media_item = MediaItem(
                id=f"jellyfin_{jellyfin_id}",
                title=title,
                type=media_type,
                availability=MediaAvailability.REMOTE_ONLY,
                year=year,
                duration=duration,
                thumbnail_url=thumbnail_url,
                jellyfin_id=jellyfin_id,
                metadata={
                    'overview': item.get('Overview', ''),
                    'genres': item.get('Genres', []),
                    'path': item.get('Path', ''),
                    'server_id': item.get('ServerId', ''),
                    'etag': item.get('Etag', '')
                }
            )
            
            return media_item
            
        except Exception as e:
            logger.error(f"Error converting Jellyfin item {item.get('Id', 'unknown')}: {e.__class__.__name__} - {str(e)}")
            return None
    
    def _download_worker(self, task: DownloadTask, media_id: str, destination: str) -> None:
        """
        Worker function for downloading media files with enhanced progress tracking.
        
        Args:
            task: DownloadTask to update
            media_id: Jellyfin media item ID
            destination: Local destination path
        """
        logger.info(f"Download worker started for media ID: {media_id} to {destination}")
        start_time = time.time()
        last_progress_update = 0
        last_progress_time = 0
        response = None
        
        try:
            # Use correct Jellyfin download API endpoint
            download_url = urljoin(self.server_url, f'/Items/{media_id}/Download')
            logger.debug(f"Download URL: {download_url}")
            
            # Prepare authentication headers for download request
            # Use the simpler X-Emby-Token header for consistency with other API calls
            download_headers = {
                'X-Emby-Token': self.api_key,
                'User-Agent': 'RV Media Player/1.0'
            }
            
            # Start download with streaming and proper authentication
            logger.debug(f"Starting download request for {media_id}")
            response = self.session.get(download_url, headers=download_headers, stream=True, timeout=30)
            
            # Handle different response types with proper error detection
            if response.status_code == 401:
                task.mark_failed("Authentication failed - invalid API key or insufficient permissions")
                logger.error(f"Download authentication failed for media {media_id}: 401 Unauthorized")
                return
            elif response.status_code == 404:
                task.mark_failed("Media item not found or not available for download")
                logger.error(f"Download failed for media {media_id}: 404 Not Found")
                return
            elif response.status_code == 403:
                task.mark_failed("Access forbidden - insufficient permissions for download")
                logger.error(f"Download failed for media {media_id}: 403 Forbidden")
                return
            elif response.status_code >= 400:
                # Check if response is JSON error message
                content_type = response.headers.get('content-type', '').lower()
                if 'application/json' in content_type:
                    try:
                        error_data = response.json()
                        error_msg = error_data.get('message', f'HTTP {response.status_code} error')
                        task.mark_failed(f"Server error: {error_msg}")
                        logger.error(f"Download failed for media {media_id}: {error_msg}")
                        return
                    except ValueError:
                        # JSON parsing failed, treat as generic error
                        pass
                
                task.mark_failed(f"HTTP {response.status_code}: {response.reason}")
                logger.error(f"Download failed for media {media_id}: HTTP {response.status_code} - {response.reason}")
                return
            
            # Verify we got binary content, not JSON error
            content_type = response.headers.get('content-type', '').lower()
            if 'application/json' in content_type:
                # This shouldn't happen for successful downloads, but handle it
                try:
                    error_data = response.json()
                    error_msg = error_data.get('message', 'Unexpected JSON response for download')
                    task.mark_failed(f"Server returned JSON instead of file: {error_msg}")
                    logger.error(f"Download failed for media {media_id}: Got JSON response instead of binary content")
                    return
                except ValueError:
                    # JSON parsing failed, continue as if it's binary
                    logger.warning(f"Content-Type indicates JSON but parsing failed, treating as binary for media {media_id}")
            
            response.raise_for_status()  # Final check for any remaining HTTP errors
            
            # Get file size for progress tracking
            total_size = int(response.headers.get('content-length', 0))
            logger.info(f"Starting download of {total_size} bytes for media {media_id}")
            
            # Store total size for progress tracking calculations
            task._total_size = total_size
            
            # Extract filename from Content-Disposition header if available
            content_disposition = response.headers.get('content-disposition', '')
            if content_disposition and 'filename=' in content_disposition:
                # Parse filename from Content-Disposition header
                import re
                filename_match = re.search(r'filename[*]?=([^;]+)', content_disposition)
                if filename_match:
                    suggested_filename = filename_match.group(1).strip('"\'')
                    logger.debug(f"Server suggested filename: {suggested_filename}")
            
            # Ensure destination directory exists
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            
            # Mark task as downloading and update initial progress
            task.status = DownloadStatus.DOWNLOADING
            task.update_progress(0.0)
            
            # Download file with enhanced progress tracking and cancellation support
            downloaded_size = 0
            chunk_size = 8192  # 8KB chunks for good balance of memory and progress updates
            progress_update_threshold = 0.001  # Update progress every 0.1% for smoother UI updates
            
            with open(destination, 'wb') as f:
                try:
                    # Use a more responsive approach to handle cancellation
                    content_iterator = response.iter_content(chunk_size=chunk_size)
                    
                    while True:
                        # Check cancellation before each chunk read
                        if task.status == DownloadStatus.FAILED:
                            logger.info(f"Download for {media_id} cancelled during transfer at {downloaded_size}/{total_size} bytes")
                            return  # Exit immediately on cancellation
                        elif task.status == DownloadStatus.COMPLETED:
                            logger.info(f"Download for {media_id} already completed during transfer at {downloaded_size}/{total_size} bytes")
                            break  # Exit the download loop normally
                        
                        try:
                            # Get next chunk with timeout to allow cancellation checks
                            chunk = next(content_iterator)
                        except StopIteration:
                            # End of stream
                            break
                        except Exception as chunk_e:
                            # Check if cancellation or completion caused the error
                            if task.status == DownloadStatus.FAILED:
                                logger.info(f"Download for {media_id} cancelled during chunk read")
                                return
                            elif task.status == DownloadStatus.COMPLETED:
                                logger.info(f"Download for {media_id} completed during chunk read")
                                break
                            else:
                                raise chunk_e
                        
                        if chunk:
                            f.write(chunk)
                            downloaded_size += len(chunk)
                            
                            # Update progress with throttling to avoid excessive updates
                            if total_size > 0:
                                current_progress = downloaded_size / total_size
                                current_time = time.time()
                                
                                # Update progress if we've made significant progress OR enough time has passed
                                progress_changed = current_progress - last_progress_update >= progress_update_threshold
                                time_elapsed = current_time - last_progress_time >= 0.2  # Update at least every 0.2 seconds
                                
                                if (progress_changed or time_elapsed or current_progress >= 1.0):
                                    task.update_progress(current_progress)
                                    last_progress_update = current_progress
                                    last_progress_time = current_time
                                
                                # Log progress at key milestones (this shows the real progress in console)
                                progress_percent = int(current_progress * 100)
                                if progress_percent % 5 == 0 and progress_percent > 0:  # Log every 5% instead of 25%
                                    elapsed_time = time.time() - start_time
                                    speed_mbps = (downloaded_size / (1024 * 1024)) / elapsed_time if elapsed_time > 0 else 0
                                    logger.info(f"Download progress for {media_id}: {progress_percent}% ({downloaded_size}/{total_size} bytes, {speed_mbps:.2f} MB/s)")
                            else:
                                # For unknown size downloads, just update periodically
                                current_time = time.time()
                                if current_time - start_time > 5:  # Update every 5 seconds for unknown size
                                    logger.info(f"Download progress for {media_id}: {downloaded_size} bytes downloaded (size unknown)")
                                    start_time = current_time
                        
                        # Additional cancellation check after processing chunk
                        # Check for cancellation but allow completion
                        if task.status == DownloadStatus.FAILED:
                            logger.info(f"Download for {media_id} cancelled after processing chunk at {downloaded_size}/{total_size} bytes")
                            return
                        elif task.status == DownloadStatus.COMPLETED:
                            logger.info(f"Download for {media_id} completed after processing chunk at {downloaded_size}/{total_size} bytes")
                            break  # Exit the download loop normally
                            
                except Exception as stream_e:
                    # Handle streaming errors
                    if task.status == DownloadStatus.FAILED:
                        logger.info(f"Download for {media_id} cancelled during streaming")
                        return
                    elif task.status == DownloadStatus.COMPLETED:
                        logger.info(f"Download for {media_id} completed during streaming")
                        return  # Exit the function since download is complete
                    else:
                        raise stream_e
            
            # Enhanced download completion detection
            if task.status == DownloadStatus.FAILED:
                # Download was cancelled or failed
                logger.info(f"Download cancelled for {media_id} after downloading {downloaded_size} bytes")
                return
            elif task.status == DownloadStatus.COMPLETED:
                # Download was already marked as completed by update_progress
                logger.info(f"Download already marked as completed for {media_id}: {downloaded_size} bytes")
                # Verify file integrity and set file_path if not already set
                if os.path.exists(destination) and os.path.getsize(destination) > 0:
                    if not task.file_path:
                        task.file_path = destination
                    elapsed_time = time.time() - start_time
                    final_size = os.path.getsize(destination)
                    avg_speed_mbps = (final_size / (1024 * 1024)) / elapsed_time if elapsed_time > 0 else 0
                    logger.info(f"Download completed for {media_id}: {final_size} bytes in {elapsed_time:.2f}s (avg {avg_speed_mbps:.2f} MB/s)")
                else:
                    task.mark_failed("Download verification failed: File missing or empty after completion")
                    logger.error(f"Download verification failed for {media_id}: File missing or empty")
            else:
                # Download finished but not yet marked as completed - validate and complete
                download_successful = False
                
                if total_size > 0:
                    # Known file size - check if we got the expected amount
                    if downloaded_size >= total_size:
                        download_successful = True
                        logger.info(f"Download completed successfully for {media_id}: {downloaded_size}/{total_size} bytes")
                    else:
                        task.mark_failed(f"Download incomplete: Expected {total_size} bytes, got {downloaded_size} bytes")
                        logger.error(f"Download incomplete for {media_id}: Expected {total_size}, got {downloaded_size}")
                else:
                    # Unknown file size - verify file exists and has content
                    if os.path.exists(destination) and os.path.getsize(destination) > 0:
                        download_successful = True
                        actual_size = os.path.getsize(destination)
                        logger.info(f"Download completed successfully for {media_id}: {actual_size} bytes (size was unknown)")
                    else:
                        task.mark_failed("Download failed: No content received or file is empty")
                        logger.error(f"Download failed for {media_id}: No content received")
                
                # Finalize download status
                if download_successful:
                    # Verify file integrity one more time
                    if os.path.exists(destination) and os.path.getsize(destination) > 0:
                        task.mark_completed(destination)
                        elapsed_time = time.time() - start_time
                        final_size = os.path.getsize(destination)
                        avg_speed_mbps = (final_size / (1024 * 1024)) / elapsed_time if elapsed_time > 0 else 0
                        logger.info(f"Download completed for {media_id}: {final_size} bytes in {elapsed_time:.2f}s (avg {avg_speed_mbps:.2f} MB/s)")
                    else:
                        task.mark_failed("Download verification failed: File missing or empty after completion")
                        logger.error(f"Download verification failed for {media_id}: File missing or empty")
            
        except requests.exceptions.Timeout as timeout_e:
            task.mark_failed(f"Download timeout: {str(timeout_e)}")
            logger.error(f"Download timeout for {media_id}: {str(timeout_e)}")
        except requests.exceptions.ConnectionError as conn_e:
            task.mark_failed(f"Download connection error: {str(conn_e)}")
            logger.error(f"Download connection error for {media_id}: {str(conn_e)}")
        except requests.exceptions.RequestException as req_e:
            task.mark_failed(f"Download network error: {req_e.__class__.__name__} - {str(req_e)}")
            logger.error(f"Download network error for {media_id}: {req_e.__class__.__name__} - {str(req_e)}")
        except IOError as io_e:
            task.mark_failed(f"File I/O error: {str(io_e)}")
            logger.error(f"Download file I/O error for {media_id}: {str(io_e)}")
        except Exception as e:
            task.mark_failed(f"Download error: {e.__class__.__name__} - {str(e)}")
            logger.error(f"Unexpected download error for {media_id}: {e.__class__.__name__} - {str(e)}")
            
        finally:
            # Close response if it exists
            if response:
                try:
                    response.close()
                except:
                    pass
            
            # Clean up partial download on failure/error/cancellation
            if task.status != DownloadStatus.COMPLETED and os.path.exists(destination):
                try:
                    file_size = os.path.getsize(destination)
                    os.remove(destination)
                    logger.debug(f"Cleaned up partial file for failed/cancelled download: {destination} ({file_size} bytes)")
                except OSError as ose:
                    logger.warning(f"Failed to remove partial file {destination} during cleanup: {str(ose)}")
            
            # Clean up thread reference
            if task.task_id in self._download_threads:
                del self._download_threads[task.task_id]
            
            total_time = time.time() - start_time
            logger.debug(f"Download worker finished for media ID: {media_id} after {total_time:.2f}s")
    
    def _download_worker_with_progress(self, task: DownloadTask, media_id: str, destination: str) -> None:
        """
        Wrapper for download worker that integrates with progress tracker.
        
        Args:
            task: DownloadTask to update
            media_id: Jellyfin media item ID
            destination: Local destination path
        """
        try:
            from ..api.download_progress import progress_tracker
            
            # Store original update_progress method
            original_update_progress = task.update_progress
            
            # Create enhanced update_progress that notifies progress tracker
            def enhanced_update_progress(progress: float) -> None:
                original_update_progress(progress)
                try:
                    # Convert to percentage for progress tracker
                    progress_percent = progress * 100
                    
                    # Debug logging to see what's being sent to UI
                    logger.debug(f"Sending progress update to UI: {progress_percent:.1f}% for task {task.task_id}")
                    
                    # Calculate speed and ETA if possible
                    current_time = time.time()
                    if hasattr(task, '_start_time'):
                        elapsed_time = current_time - task._start_time
                        if elapsed_time > 0 and progress > 0:
                            speed_bytes_per_sec = (progress * getattr(task, '_total_size', 0)) / elapsed_time
                            speed_mbps = speed_bytes_per_sec / (1024 * 1024)
                            
                            if progress < 1.0:
                                remaining_progress = 1.0 - progress
                                eta_seconds = (remaining_progress * elapsed_time) / progress
                            else:
                                eta_seconds = 0
                            
                            logger.info(f"Progress tracker update: {progress_percent:.1f}%, {speed_mbps:.2f} MB/s, ETA: {eta_seconds:.0f}s")
                            progress_tracker.update_progress(task.task_id, progress_percent, speed_mbps, eta_seconds)
                        else:
                            logger.info(f"Progress tracker update (no speed): {progress_percent:.1f}%")
                            progress_tracker.update_progress(task.task_id, progress_percent)
                    else:
                        logger.info(f"Progress tracker update (no timing): {progress_percent:.1f}%")
                        progress_tracker.update_progress(task.task_id, progress_percent)
                except Exception as e:
                    logger.warning(f"Failed to update progress tracker: {str(e)}")
            
            # Replace the method temporarily and add timing info
            task.update_progress = enhanced_update_progress
            task._start_time = time.time()
            
            # Run the actual download worker
            self._download_worker(task, media_id, destination)
            
            # Notify progress tracker of final status
            if task.status == DownloadStatus.COMPLETED:
                progress_tracker.complete_download(task.task_id)
            elif task.status == DownloadStatus.FAILED:
                progress_tracker.fail_download(task.task_id, task.error_message)
            elif not task.is_active():
                # Task was cancelled
                progress_tracker.cancel_download(task.task_id)
            
            # Call completion callback if provided
            if hasattr(task, '_completion_callback') and task._completion_callback:
                try:
                    logger.info(f"Calling completion callback for task {task.task_id}")
                    task._completion_callback(task)
                except Exception as callback_error:
                    logger.error(f"Error in completion callback for task {task.task_id}: {callback_error}")
            
            # Save download state after completion
            self._save_download_state()
                
        except ImportError:
            logger.warning("Progress tracker not available, running download without progress notifications")
            # Fall back to regular download worker
            self._download_worker(task, media_id, destination)
            
            # Call completion callback if provided (since we bypassed the progress tracker path)
            if hasattr(task, '_completion_callback') and task._completion_callback:
                try:
                    logger.info(f"Calling completion callback for task {task.task_id} (fallback path)")
                    task._completion_callback(task)
                except Exception as callback_error:
                    logger.error(f"Error in completion callback for task {task.task_id}: {callback_error}")
            
            # Save download state after completion
            self._save_download_state()
        except Exception as e:
            logger.error(f"Error in download worker with progress: {str(e)}")
            # Fall back to regular download worker
            self._download_worker(task, media_id, destination)
            
            # Call completion callback if provided (since we bypassed the progress tracker path)
            if hasattr(task, '_completion_callback') and task._completion_callback:
                try:
                    logger.info(f"Calling completion callback for task {task.task_id} (error fallback path)")
                    task._completion_callback(task)
                except Exception as callback_error:
                    logger.error(f"Error in completion callback for task {task.task_id}: {callback_error}")
            
            # Save download state after completion
            self._save_download_state()
        finally:
            # Clean up temporary attributes
            if hasattr(task, '_start_time'):
                delattr(task, '_start_time')
            if hasattr(task, '_total_size'):
                delattr(task, '_total_size')
    
    def _save_download_state(self) -> None:
        """Save download state to persistent storage."""
        try:
            os.makedirs(os.path.dirname(self._download_state_file), exist_ok=True)
            
            # Only save tasks that are active or recently completed
            state_to_save = {}
            for task_id, task in self._download_tasks.items():
                if task.is_active() or task.status == DownloadStatus.COMPLETED:
                    # Create a serializable copy without callback functions
                    task_copy = DownloadTask(
                        media_id=task.media_id,
                        status=task.status,
                        progress=task.progress,
                        file_path=task.file_path,
                        error_message=task.error_message,
                        task_id=task.task_id
                    )
                    # Preserve custom attributes except callbacks
                    if hasattr(task, 'final_destination'):
                        task_copy.final_destination = task.final_destination
                    state_to_save[task_id] = task_copy
            
            with open(self._download_state_file, 'wb') as f:
                pickle.dump(state_to_save, f)
            logger.debug(f"Saved download state for {len(state_to_save)} tasks")
        except Exception as e:
            logger.warning(f"Failed to save download state: {e}")
    
    def _load_download_state(self) -> None:
        """Load download state from persistent storage."""
        try:
            if os.path.exists(self._download_state_file):
                with open(self._download_state_file, 'rb') as f:
                    saved_state = pickle.load(f)
                
                for task_id, task in saved_state.items():
                    # Only restore active downloads, not completed ones
                    if task.is_active():
                        self._download_tasks[task_id] = task
                        logger.info(f"Restored active download task: {task_id} ({task.progress*100:.1f}%)")
                        
                        # Restart the download from where it left off
                        if hasattr(task, 'file_path') and task.file_path:
                            self._resume_download(task)
                
                logger.info(f"Loaded download state for {len(saved_state)} tasks")
        except Exception as e:
            logger.warning(f"Failed to load download state: {e}")
    
    def _resume_download(self, task: DownloadTask) -> None:
        """Resume a download from where it left off."""
        try:
            # Check if partial file exists
            if task.file_path and os.path.exists(task.file_path):
                current_size = os.path.getsize(task.file_path)
                logger.info(f"Resuming download {task.task_id} from {current_size} bytes")
                
                # For now, restart the download (resume support would require Range requests)
                # This is better than losing the download entirely
                media_id = task.media_id
                destination = task.file_path
                
                # Start download in separate thread
                download_thread = threading.Thread(
                    target=self._download_worker_with_progress,
                    args=(task, media_id, destination),
                    daemon=True
                )
                self._download_threads[task.task_id] = download_thread
                download_thread.start()
                
                logger.info(f"Restarted download thread for task {task.task_id}")
            else:
                # File doesn't exist, mark as failed
                task.mark_failed("Partial download file not found during resume")
                logger.warning(f"Could not resume download {task.task_id}: file not found")
        except Exception as e:
            logger.error(f"Failed to resume download {task.task_id}: {e}")
            task.mark_failed(f"Resume failed: {e}")