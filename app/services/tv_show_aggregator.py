"""
TV Show aggregation service for grouping episodes into show/season/episode hierarchy.
"""
import re
import logging
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

from app.models.media_item import MediaItem
from app.models.enums import MediaType
from app.models.tv_show_models import TVShow, Season, Episode


class TVShowAggregator:
    """
    Service for aggregating episode MediaItems into TV show hierarchy.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def aggregate_episodes_to_shows(self, media_items: List[MediaItem]) -> List[TVShow]:
        """
        Aggregate episode MediaItems into TVShow objects.
        
        Args:
            media_items: List of MediaItem objects (episodes and shows)
            
        Returns:
            List of TVShow objects with proper hierarchy
        """
        self.logger.info(f"Aggregating {len(media_items)} media items into TV shows")
        
        # Filter for episodes and TV shows
        episodes = [item for item in media_items if item.type == MediaType.EPISODE]
        tv_shows = [item for item in media_items if item.type == MediaType.TV_SHOW]
        
        self.logger.info(f"Found {len(episodes)} episodes and {len(tv_shows)} TV shows")
        
        # Group episodes by show
        shows_dict = self._group_episodes_by_show(episodes)

        # Add standalone TV show items (without episodes) but avoid duplicates
        for tv_show_item in tv_shows:
            show_key = self._normalize_show_title(tv_show_item.title)

            # Check if this TV show matches any existing show (including similar titles)
            matching_key = None
            for existing_key, existing_data in shows_dict.items():
                if self._is_same_show(tv_show_item.title, existing_data['title']):
                    matching_key = existing_key
                    break

            if matching_key:
                # Show already exists from episodes, enhance with TV show metadata
                existing_show = shows_dict[matching_key]

                # Use TV show metadata if it's more complete
                if not existing_show['thumbnail_url'] and tv_show_item.thumbnail_url:
                    existing_show['thumbnail_url'] = tv_show_item.thumbnail_url
                    self.logger.debug(f"{existing_show['title']} with TV show thumbnail from {tv_show_item.title}")

                if not existing_show['year'] and tv_show_item.year:
                    existing_show['year'] = tv_show_item.year
                    self.logger.debug(f"{existing_show['title']} with TV show year from {tv_show_item.title}")

                # Merge metadata, preferring TV show metadata for certain fields
                if tv_show_item.metadata:
                    for key, value in tv_show_item.metadata.items():
                        if key not in existing_show['metadata'] or not existing_show['metadata'][key]:
                            existing_show['metadata'][key] = value

                self.logger.debug(f"existing show {existing_show['title']} with TV show metadata from {tv_show_item.title}")

            elif show_key not in shows_dict:
                # Create new entry for standalone TV show
                shows_dict[show_key] = {
                    'title': tv_show_item.title,
                    'year': tv_show_item.year,
                    'thumbnail_url': tv_show_item.thumbnail_url,
                    'metadata': tv_show_item.metadata,
                    'episodes': []
                }
                self.logger.debug(f"Added standalone TV show: {tv_show_item.title}")
            else:
                # Exact key match, enhance existing
                existing_show = shows_dict[show_key]

                if not existing_show['thumbnail_url'] and tv_show_item.thumbnail_url:
                    existing_show['thumbnail_url'] = tv_show_item.thumbnail_url

                if not existing_show['year'] and tv_show_item.year:
                    existing_show['year'] = tv_show_item.year

                if tv_show_item.metadata:
                    for key, value in tv_show_item.metadata.items():
                        if key not in existing_show['metadata'] or not existing_show['metadata'][key]:
                            existing_show['metadata'][key] = value

                self.logger.debug(f"existing show {tv_show_item.title} with exact key match")
        
        # Convert to TVShow objects
        tv_show_objects = []
        for show_key, show_data in shows_dict.items():
            tv_show = self._create_tv_show_from_data(show_key, show_data)
            if tv_show:
                tv_show_objects.append(tv_show)
        
        self.logger.info(f"Created {len(tv_show_objects)} TV show objects")
        return tv_show_objects
    
    def _group_episodes_by_show(self, episodes: List[MediaItem]) -> Dict[str, Dict]:
        """Group episodes by show title."""
        shows_dict = defaultdict(lambda: {
            'title': '',
            'year': None,
            'thumbnail_url': None,
            'metadata': {},
            'episodes': []
        })
        
        for episode in episodes:
            # Extract show information from episode
            show_title, season_num, episode_num = self._parse_episode_info(episode)
            
            if not show_title:
                self.logger.warning(f"Could not extract show title from episode: {episode.title}")
                continue
            
            show_key = self._normalize_show_title(show_title)
            
            # Update show info (use first episode's info as base)
            if not shows_dict[show_key]['title']:
                shows_dict[show_key]['title'] = show_title
                shows_dict[show_key]['year'] = episode.year
                shows_dict[show_key]['thumbnail_url'] = episode.thumbnail_url
                shows_dict[show_key]['metadata'] = episode.metadata.copy()
            
            # Add episode info
            shows_dict[show_key]['episodes'].append({
                'episode': episode,
                'season_number': season_num,
                'episode_number': episode_num
            })
        
        return dict(shows_dict)
    
    def _parse_episode_info(self, episode: MediaItem) -> Tuple[str, int, int]:
        """
        Parse episode information from MediaItem.

        Returns:
            Tuple of (show_title, season_number, episode_number)
        """
        title = episode.title

        # Try to extract from Jellyfin metadata first
        if episode.metadata:
            series_name = episode.metadata.get('SeriesName')
            season_num = episode.metadata.get('ParentIndexNumber')
            episode_num = episode.metadata.get('IndexNumber')

            if series_name and season_num is not None and episode_num is not None:
                return series_name, int(season_num), int(episode_num)

        # Try to extract from Jellyfin path metadata
        if episode.metadata and episode.metadata.get('path'):
            path_info = self._parse_episode_from_path(episode.metadata['path'])
            if path_info[0]:  # If we found a show title from path
                return path_info

        # Try to extract from local path if available
        if hasattr(episode, 'local_path') and episode.local_path:
            path_info = self._parse_episode_from_path(episode.local_path)
            if path_info[0]:  # If we found a show title from path
                return path_info

        # Fallback to parsing from title
        return self._parse_episode_from_title(title, None)
    
    def _parse_episode_from_title(self, title: str, file_path: Optional[str] = None) -> Tuple[str, int, int]:
        """
        Parse episode information from title and file path.
        
        Returns:
            Tuple of (show_title, season_number, episode_number)
        """
        # Common patterns for TV show episodes
        patterns = [
            # "Show Name S01E01 Episode Title"
            r'^(.+?)\s+S(\d+)E(\d+)',
            # "Show Name - S01E01 - Episode Title"
            r'^(.+?)\s*-\s*S(\d+)E(\d+)',
            # "Show Name 1x01 Episode Title"
            r'^(.+?)\s+(\d+)x(\d+)',
            # "Show Name - 1x01 - Episode Title"
            r'^(.+?)\s*-\s*(\d+)x(\d+)',
            # "Show Name Season 1 Episode 1"
            r'^(.+?)\s+Season\s+(\d+)\s+Episode\s+(\d+)',
            # Extract from file path if available
        ]
        
        for pattern in patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                show_title = match.group(1).strip()
                season_num = int(match.group(2))
                episode_num = int(match.group(3))
                return show_title, season_num, episode_num
        
        # Try to extract from file path
        if file_path:
            path_info = self._parse_episode_from_path(file_path)
            if path_info[0]:  # If we found a show title
                return path_info
        
        # Fallback: treat as Season 1, Episode 1 and use full title as show
        self.logger.warning(f"Could not parse episode info from: {title}")
        return title, 1, 1
    
    def _parse_episode_from_path(self, file_path: str) -> Tuple[str, int, int]:
        """Parse episode information from file path."""
        import os

        # Handle both Windows and Unix path separators
        # Normalize path separators for consistent parsing
        normalized_path = file_path.replace('\\', '/').replace('//', '/')

        # Get directory and filename
        dir_path = os.path.dirname(normalized_path)
        filename = os.path.basename(normalized_path)

        # Split path into parts
        path_parts = [part for part in normalized_path.split('/') if part]

        show_title = ""
        season_num = 1
        episode_num = 1

        self.logger.debug(f"Parsing path: {file_path}")
        self.logger.debug(f"Path parts: {path_parts}")

        # Look for show name and season in path
        # Common patterns:
        # /tvshows/The Sandman/Season 2/episode.mkv
        # /media/tv/Show Name/S01/episode.mp4
        # /shows/Show Name/Season 1/S01E01.mp4

        for i, part in enumerate(path_parts):
            # Check if this part contains season information
            season_match = re.search(r'season\s*(\d+)', part, re.IGNORECASE)
            if season_match:
                season_num = int(season_match.group(1))
                # Show name should be the previous part
                if i > 0:
                    show_title = path_parts[i - 1]
                self.logger.debug(f"Found season {season_num} in part: {part}, show: {show_title}")
                break

            # Check for S## pattern (like S01, S02)
            s_pattern_match = re.search(r'^S(\d+)$', part, re.IGNORECASE)
            if s_pattern_match:
                season_num = int(s_pattern_match.group(1))
                # Show name should be the previous part
                if i > 0:
                    show_title = path_parts[i - 1]
                self.logger.debug(f"Found S{season_num} pattern, show: {show_title}")
                break

        # If we haven't found a show title yet, look for it in the path
        if not show_title:
            # Look for the part that's most likely the show name
            # Usually it's after 'tvshows', 'tv', 'shows', 'series', etc.
            for i, part in enumerate(path_parts):
                if re.search(r'(tv|shows?|series)', part, re.IGNORECASE):
                    # Show name should be the next part
                    if i + 1 < len(path_parts):
                        show_title = path_parts[i + 1]
                        self.logger.debug(f"Found show after TV directory: {show_title}")
                    break

            # If still no show title, use the first non-generic directory name
            if not show_title:
                for part in path_parts:
                    if not re.search(r'(tv|shows?|series|media|movies)', part, re.IGNORECASE) and part:
                        show_title = part
                        self.logger.debug(f"Using first non-generic part as show: {show_title}")
                        break

        # Extract episode info from filename
        episode_patterns = [
            r'[sS](\d+)[eE](\d+)',  # S01E01, s01e01
            r'(\d+)x(\d+)',         # 1x01
            r'Season\s*(\d+).*Episode\s*(\d+)',  # Season 1 Episode 1
            r'[sS](\d+)\.?[eE](\d+)',  # S01.E01
        ]

        for pattern in episode_patterns:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                # Update season and episode from filename if found
                filename_season = int(match.group(1))
                filename_episode = int(match.group(2))

                # Use filename info if it seems more reliable
                if filename_season > 0:
                    season_num = filename_season
                episode_num = filename_episode
                self.logger.debug(f"Extracted from filename - S{season_num}E{episode_num}")
                break

        # Clean up show title
        if show_title:
            # Remove common artifacts
            show_title = re.sub(r'\[.*?\]', '', show_title)  # Remove [tags]
            show_title = re.sub(r'\(.*?\)', '', show_title)  # Remove (year) etc
            show_title = show_title.strip()

        self.logger.debug(f"Final parsing result: show='{show_title}', season={season_num}, episode={episode_num}")

        return show_title, season_num, episode_num
    
    def _normalize_show_title(self, title: str) -> str:
        """Normalize show title for grouping."""
        if not title:
            return ""

        # Remove common variations and normalize
        normalized = title.lower().strip()

        # Remove common artifacts
        normalized = re.sub(r'\s*\(.*?\)\s*', '', normalized)  # Remove parentheses
        normalized = re.sub(r'\s*\[.*?\]\s*', '', normalized)  # Remove brackets

        # Normalize punctuation that might vary between sources
        normalized = re.sub(r'[:\-–—]', ' ', normalized)  # Replace colons, dashes with spaces
        normalized = re.sub(r'[^\w\s]', '', normalized)  # Remove other punctuation
        normalized = re.sub(r'\s+', ' ', normalized)  # Normalize whitespace
        normalized = normalized.strip()

        self.logger.debug(f"Normalized '{title}' to '{normalized}'")
        return normalized

    def _is_same_show(self, title1: str, title2: str) -> bool:
        """Check if two titles refer to the same show."""
        if not title1 or not title2:
            return False

        # Normalize both titles
        norm1 = self._normalize_show_title(title1)
        norm2 = self._normalize_show_title(title2)

        # Direct match
        if norm1 == norm2:
            return True

        # Check if one is a substring of the other (for cases like "Daredevil" vs "Daredevil Born Again")
        if norm1 in norm2 or norm2 in norm1:
            # Make sure it's not just a single word match
            words1 = set(norm1.split())
            words2 = set(norm2.split())
            common_words = words1.intersection(words2)

            # If they share most words, consider them the same show
            if len(common_words) >= min(len(words1), len(words2)) * 0.8:
                self.logger.debug(f"Detected same show: '{title1}' and '{title2}' (common words: {common_words})")
                return True

        return False
    
    def _create_tv_show_from_data(self, show_key: str, show_data: Dict) -> Optional[TVShow]:
        """Create TVShow object from aggregated data."""
        try:
            # Create TV show
            tv_show = TVShow(
                id=f"show_{show_key.replace(' ', '_')}",
                title=show_data['title'],
                year=show_data['year'],
                thumbnail_url=show_data['thumbnail_url'],
                metadata=show_data['metadata']
            )
            
            # Group episodes by season
            seasons_dict = defaultdict(list)
            for ep_data in show_data['episodes']:
                season_num = ep_data['season_number']
                seasons_dict[season_num].append(ep_data)
            
            # Create seasons
            for season_num, episodes_data in seasons_dict.items():
                season = Season(
                    season_number=season_num,
                    title=f"Season {season_num}",
                    year=show_data['year']
                )
                
                # Add episodes to season
                for ep_data in episodes_data:
                    episode_item = ep_data['episode']
                    episode = Episode(
                        episode_number=ep_data['episode_number'],
                        title=episode_item.title,
                        media_item_id=episode_item.id,
                        availability=episode_item.availability,
                        duration=episode_item.duration,
                        year=episode_item.year,
                        thumbnail_url=episode_item.thumbnail_url,
                        local_path=episode_item.local_path,
                        jellyfin_id=episode_item.jellyfin_id,
                        metadata=episode_item.metadata
                    )
                    season.add_episode(episode)
                
                tv_show.add_season(season)
            
            return tv_show
            
        except Exception as e:
            self.logger.error(f"Error creating TV show from data: {e}")
            return None
