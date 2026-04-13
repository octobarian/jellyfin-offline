"""
TV Show hierarchy data models for the RV Media Player application.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set
from enum import Enum
from .enums import MediaAvailability


class ShowAvailability(Enum):
    """Enumeration for show availability status."""
    NONE = "none"                    # No episodes available
    LOCAL_ONLY = "local_only"        # All available episodes are local only
    REMOTE_ONLY = "remote_only"      # All available episodes are remote only
    MIXED = "mixed"                  # Some episodes local, some remote
    COMPLETE_LOCAL = "complete_local"    # All episodes available locally
    COMPLETE_REMOTE = "complete_remote"  # All episodes available remotely
    COMPLETE_BOTH = "complete_both"      # All episodes available both locally and remotely


@dataclass
class Episode:
    """
    Represents a single episode within a season.
    
    Attributes:
        episode_number: Episode number within the season
        title: Episode title
        media_item_id: Reference to the original MediaItem ID
        availability: Where this episode is available
        duration: Episode duration in seconds
        year: Air year (optional)
        thumbnail_url: Episode thumbnail URL (optional)
        local_path: Path to local file if available (optional)
        jellyfin_id: Jellyfin server ID if available (optional)
        metadata: Additional episode metadata
    """
    episode_number: int
    title: str
    media_item_id: str
    availability: MediaAvailability
    duration: Optional[int] = None
    year: Optional[int] = None
    thumbnail_url: Optional[str] = None
    local_path: Optional[str] = None
    jellyfin_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_local_available(self) -> bool:
        """Check if episode is available locally."""
        return self.availability in [MediaAvailability.LOCAL_ONLY, MediaAvailability.BOTH]
    
    def is_remote_available(self) -> bool:
        """Check if episode is available remotely."""
        return self.availability in [MediaAvailability.REMOTE_ONLY, MediaAvailability.BOTH]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert Episode to dictionary for serialization."""
        return {
            'episode_number': self.episode_number,
            'title': self.title,
            'media_item_id': self.media_item_id,
            'availability': self.availability.value,
            'duration': self.duration,
            'year': self.year,
            'thumbnail_url': self.thumbnail_url,
            'local_path': self.local_path,
            'jellyfin_id': self.jellyfin_id,
            'metadata': self.metadata,
            'is_local_available': self.is_local_available(),
            'is_remote_available': self.is_remote_available()
        }


@dataclass
class Season:
    """
    Represents a season containing multiple episodes.
    
    Attributes:
        season_number: Season number
        title: Season title (e.g., "Season 1", "Specials")
        episodes: List of episodes in this season
        year: Season year (optional)
        thumbnail_url: Season thumbnail URL (optional)
        metadata: Additional season metadata
    """
    season_number: int
    title: str
    episodes: List[Episode] = field(default_factory=list)
    year: Optional[int] = None
    thumbnail_url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def get_availability(self) -> ShowAvailability:
        """Calculate season availability based on episodes."""
        if not self.episodes:
            return ShowAvailability.NONE
        
        local_count = sum(1 for ep in self.episodes if ep.is_local_available())
        remote_count = sum(1 for ep in self.episodes if ep.is_remote_available())
        total_count = len(self.episodes)
        
        if local_count == 0 and remote_count == 0:
            return ShowAvailability.NONE
        elif local_count == total_count and remote_count == 0:
            return ShowAvailability.COMPLETE_LOCAL
        elif remote_count == total_count and local_count == 0:
            return ShowAvailability.COMPLETE_REMOTE
        elif local_count == total_count and remote_count == total_count:
            return ShowAvailability.COMPLETE_BOTH
        elif local_count > 0 and remote_count > 0:
            return ShowAvailability.MIXED
        elif local_count > 0:
            return ShowAvailability.LOCAL_ONLY
        else:
            return ShowAvailability.REMOTE_ONLY
    
    def get_episode_count(self) -> int:
        """Get total number of episodes in this season."""
        return len(self.episodes)
    
    def get_local_episode_count(self) -> int:
        """Get number of locally available episodes."""
        return sum(1 for ep in self.episodes if ep.is_local_available())
    
    def get_remote_episode_count(self) -> int:
        """Get number of remotely available episodes."""
        return sum(1 for ep in self.episodes if ep.is_remote_available())
    
    def add_episode(self, episode: Episode):
        """Add an episode to this season."""
        self.episodes.append(episode)
        # Sort episodes by episode number
        self.episodes.sort(key=lambda ep: ep.episode_number)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert Season to dictionary for serialization."""
        return {
            'season_number': self.season_number,
            'title': self.title,
            'episodes': [ep.to_dict() for ep in self.episodes],
            'year': self.year,
            'thumbnail_url': self.thumbnail_url,
            'metadata': self.metadata,
            'availability': self.get_availability().value,
            'episode_count': self.get_episode_count(),
            'local_episode_count': self.get_local_episode_count(),
            'remote_episode_count': self.get_remote_episode_count()
        }


@dataclass
class TVShow:
    """
    Represents a complete TV show with multiple seasons.
    
    Attributes:
        id: Unique identifier for the TV show
        title: Show title
        seasons: List of seasons in this show
        year: Show start year (optional)
        thumbnail_url: Show poster/thumbnail URL (optional)
        metadata: Additional show metadata
    """
    id: str
    title: str
    seasons: List[Season] = field(default_factory=list)
    year: Optional[int] = None
    thumbnail_url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def get_availability(self) -> ShowAvailability:
        """Calculate show availability based on all episodes."""
        all_episodes = []
        for season in self.seasons:
            all_episodes.extend(season.episodes)
        
        if not all_episodes:
            return ShowAvailability.NONE
        
        local_count = sum(1 for ep in all_episodes if ep.is_local_available())
        remote_count = sum(1 for ep in all_episodes if ep.is_remote_available())
        total_count = len(all_episodes)
        
        if local_count == 0 and remote_count == 0:
            return ShowAvailability.NONE
        elif local_count == total_count and remote_count == 0:
            return ShowAvailability.COMPLETE_LOCAL
        elif remote_count == total_count and local_count == 0:
            return ShowAvailability.COMPLETE_REMOTE
        elif local_count == total_count and remote_count == total_count:
            return ShowAvailability.COMPLETE_BOTH
        elif local_count > 0 and remote_count > 0:
            return ShowAvailability.MIXED
        elif local_count > 0:
            return ShowAvailability.LOCAL_ONLY
        else:
            return ShowAvailability.REMOTE_ONLY
    
    def get_season_count(self) -> int:
        """Get total number of seasons."""
        return len(self.seasons)
    
    def get_total_episode_count(self) -> int:
        """Get total number of episodes across all seasons."""
        return sum(season.get_episode_count() for season in self.seasons)
    
    def get_local_episode_count(self) -> int:
        """Get total number of locally available episodes."""
        return sum(season.get_local_episode_count() for season in self.seasons)
    
    def get_remote_episode_count(self) -> int:
        """Get total number of remotely available episodes."""
        return sum(season.get_remote_episode_count() for season in self.seasons)
    
    def add_season(self, season: Season):
        """Add a season to this show."""
        self.seasons.append(season)
        # Sort seasons by season number
        self.seasons.sort(key=lambda s: s.season_number)
    
    def get_season(self, season_number: int) -> Optional[Season]:
        """Get a specific season by number."""
        for season in self.seasons:
            if season.season_number == season_number:
                return season
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert TVShow to dictionary for serialization."""
        return {
            'id': self.id,
            'title': self.title,
            'seasons': [season.to_dict() for season in self.seasons],
            'year': self.year,
            'thumbnail_url': self.thumbnail_url,
            'metadata': self.metadata,
            'availability': self.get_availability().value,
            'season_count': self.get_season_count(),
            'total_episode_count': self.get_total_episode_count(),
            'local_episode_count': self.get_local_episode_count(),
            'remote_episode_count': self.get_remote_episode_count()
        }
