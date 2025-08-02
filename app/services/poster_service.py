"""
Poster Service for RV Media Player

Handles fetching, caching, and serving movie posters from Jellyfin API
and MoviePosterDB API with local storage for offline access.
"""
import os
import logging
import hashlib
import requests
from typing import Optional, Dict, Any
from urllib.parse import urljoin
import time

logger = logging.getLogger(__name__)


class PosterService:
    """
    Service for managing movie poster fetching and caching.
    """
    
    def __init__(self, cache_directory: str = "static/posters", 
                 movieposterdb_api_key: Optional[str] = None):
        """
        Initialize the poster service.
        
        Args:
            cache_directory: Directory to store cached posters
            movieposterdb_api_key: API key for MoviePosterDB (optional)
        """
        self.cache_directory = cache_directory
        self.movieposterdb_api_key = movieposterdb_api_key
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'RV-Media-Player/1.0'
        })
        
        # Create cache directory if it doesn't exist
        os.makedirs(cache_directory, exist_ok=True)
        
        # Cache for poster URLs to avoid repeated API calls
        self._url_cache = {}
        
    def get_poster_url(self, media_item: Dict[str, Any], 
                      jellyfin_service=None) -> Optional[str]:
        """
        Get poster URL for a media item, trying multiple sources.
        
        Args:
            media_item: Media item dictionary with metadata
            jellyfin_service: Jellyfin service instance (optional)
            
        Returns:
            URL to poster image or None if not found
        """
        media_id = media_item.get('id')
        title = media_item.get('title', '')
        year = media_item.get('year')
        media_type = media_item.get('type', 'MOVIE')
        
        # Check cache first
        cache_key = self._get_cache_key(media_id, title, year)
        if cache_key in self._url_cache:
            return self._url_cache[cache_key]
        
        poster_url = None
        
        # Try Jellyfin first if available
        if jellyfin_service and media_item.get('jellyfin_id'):
            poster_url = self._get_jellyfin_poster(
                media_item['jellyfin_id'], jellyfin_service
            )
        
        # Try MoviePosterDB if Jellyfin failed and we have API key
        if not poster_url and self.movieposterdb_api_key and media_type == 'MOVIE':
            poster_url = self._get_movieposterdb_poster(title, year)
        
        # Cache the result (even if None to avoid repeated failures)
        self._url_cache[cache_key] = poster_url
        
        return poster_url
    
    def get_cached_poster_path(self, media_item: Dict[str, Any]) -> Optional[str]:
        """
        Get path to locally cached poster if it exists.
        
        Args:
            media_item: Media item dictionary
            
        Returns:
            Relative path to cached poster or None
        """
        cache_key = self._get_cache_key(
            media_item.get('id'),
            media_item.get('title', ''),
            media_item.get('year')
        )
        
        # Check for common image extensions
        for ext in ['.jpg', '.jpeg', '.png', '.webp']:
            poster_path = os.path.join(self.cache_directory, f"{cache_key}{ext}")
            if os.path.exists(poster_path):
                return poster_path.replace('\\', '/')  # Ensure forward slashes for URLs
        
        return None
    
    def download_and_cache_poster(self, poster_url: str, 
                                 media_item: Dict[str, Any]) -> Optional[str]:
        """
        Download poster from URL and cache it locally.
        
        Args:
            poster_url: URL to download poster from
            media_item: Media item dictionary
            
        Returns:
            Path to cached poster or None if failed
        """
        if not poster_url:
            return None
        
        cache_key = self._get_cache_key(
            media_item.get('id'),
            media_item.get('title', ''),
            media_item.get('year')
        )
        
        try:
            response = self.session.get(poster_url, timeout=10, stream=True)
            response.raise_for_status()
            
            # Determine file extension from content type or URL
            content_type = response.headers.get('content-type', '')
            if 'jpeg' in content_type or 'jpg' in content_type:
                ext = '.jpg'
            elif 'png' in content_type:
                ext = '.png'
            elif 'webp' in content_type:
                ext = '.webp'
            else:
                # Fallback to URL extension or default to jpg
                ext = os.path.splitext(poster_url)[1] or '.jpg'
            
            poster_path = os.path.join(self.cache_directory, f"{cache_key}{ext}")
            
            # Download and save the poster
            with open(poster_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"Cached poster for '{media_item.get('title')}' at {poster_path}")
            return poster_path.replace('\\', '/')
            
        except Exception as e:
            logger.error(f"Failed to download poster from {poster_url}: {e}")
            return None
    
    def _get_jellyfin_poster(self, jellyfin_id: str, 
                           jellyfin_service) -> Optional[str]:
        """
        Get poster URL from Jellyfin API.
        
        Args:
            jellyfin_id: Jellyfin item ID
            jellyfin_service: Jellyfin service instance
            
        Returns:
            Poster URL or None
        """
        try:
            # Use Jellyfin's image API to get poster
            if hasattr(jellyfin_service, 'get_item_image_url'):
                return jellyfin_service.get_item_image_url(jellyfin_id, 'Primary')
            else:
                # Fallback: construct URL manually
                base_url = getattr(jellyfin_service, 'server_url', '')
                if base_url:
                    return f"{base_url}/Items/{jellyfin_id}/Images/Primary"
        except Exception as e:
            logger.error(f"Failed to get Jellyfin poster for {jellyfin_id}: {e}")
        
        return None
    
    def _get_movieposterdb_poster(self, title: str, year: Optional[int]) -> Optional[str]:
        """
        Get poster URL from MoviePosterDB API.
        
        Args:
            title: Movie title
            year: Release year (optional)
            
        Returns:
            Poster URL or None
        """
        if not self.movieposterdb_api_key:
            return None
        
        try:
            # Search for movie
            search_url = "https://api.movieposterdb.com/v1/search"
            params = {
                'api_key': self.movieposterdb_api_key,
                'title': title
            }
            if year:
                params['year'] = year
            
            response = self.session.get(search_url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            results = data.get('results', [])
            
            if results:
                # Get the first result's poster
                movie = results[0]
                poster_url = movie.get('poster_url')
                if poster_url:
                    logger.info(f"Found MoviePosterDB poster for '{title}' ({year})")
                    return poster_url
            
        except Exception as e:
            logger.error(f"Failed to get MoviePosterDB poster for '{title}': {e}")
        
        return None
    
    def _get_cache_key(self, media_id: str, title: str, year: Optional[int]) -> str:
        """
        Generate cache key for a media item.
        
        Args:
            media_id: Media item ID
            title: Media title
            year: Release year
            
        Returns:
            Cache key string
        """
        # Create a unique key based on ID, title, and year
        key_data = f"{media_id}_{title}_{year or 'unknown'}"
        return hashlib.md5(key_data.encode('utf-8')).hexdigest()
    
    def cleanup_cache(self, max_age_days: int = 30):
        """
        Clean up old cached posters.
        
        Args:
            max_age_days: Maximum age in days before deletion
        """
        try:
            current_time = time.time()
            max_age_seconds = max_age_days * 24 * 60 * 60
            
            for filename in os.listdir(self.cache_directory):
                file_path = os.path.join(self.cache_directory, filename)
                
                if os.path.isfile(file_path):
                    file_age = current_time - os.path.getmtime(file_path)
                    
                    if file_age > max_age_seconds:
                        os.remove(file_path)
                        logger.info(f"Removed old cached poster: {filename}")
                        
        except Exception as e:
            logger.error(f"Failed to cleanup poster cache: {e}")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the poster cache.
        
        Returns:
            Dictionary with cache statistics
        """
        try:
            cache_files = [f for f in os.listdir(self.cache_directory) 
                          if os.path.isfile(os.path.join(self.cache_directory, f))]
            
            total_size = sum(
                os.path.getsize(os.path.join(self.cache_directory, f))
                for f in cache_files
            )
            
            return {
                'cached_posters': len(cache_files),
                'total_size_bytes': total_size,
                'total_size_mb': round(total_size / (1024 * 1024), 2),
                'cache_directory': self.cache_directory
            }
        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {
                'cached_posters': 0,
                'total_size_bytes': 0,
                'total_size_mb': 0,
                'cache_directory': self.cache_directory
            }
