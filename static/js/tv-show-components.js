/**
 * TV Show UI Components for hierarchical display of Shows/Seasons/Episodes
 */

// Global state for TV show navigation
let currentTVShowView = 'shows'; // 'shows', 'seasons', 'episodes'
let currentShowData = null;
let currentSeasonData = null;

/**
 * Create a TV show card for the main grid
 */
function createTVShowCard(tvShow) {
    const card = document.createElement('div');
    card.className = 'media-card tv-show-card';
    card.dataset.showId = tvShow.id;
    
    const availabilityClass = getAvailabilityClass(tvShow.availability);
    const availabilityIcon = getAvailabilityIcon(tvShow.availability);
    
    const posterUrl = tvShow.thumbnail_url;
    const hasImage = posterUrl && posterUrl.trim().length > 0;
    
    card.innerHTML = `
        <div class="media-poster" onclick="showTVShowSeasons('${tvShow.id}')">
            ${hasImage ?
                `<img src="${posterUrl}" alt="${tvShow.title}" class="poster-image" loading="lazy"
                     onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">` : ''
            }
            <div class="poster-placeholder ${hasImage ? 'hidden' : ''}" style="display: ${hasImage ? 'none' : 'flex'};">
                <span class="placeholder-icon">📺</span>
                <span class="placeholder-text">TV Show</span>
            </div>
            <div class="availability-indicator ${availabilityClass}">
                ${availabilityIcon}
            </div>
        </div>
        <div class="media-info">
            <h3 class="media-title" title="${tvShow.title}">${tvShow.title}</h3>
            <div class="media-details">
                <span class="media-year">${tvShow.year || 'Unknown'}</span>
                <span class="media-stats">
                    ${tvShow.season_count} Season${tvShow.season_count !== 1 ? 's' : ''} • 
                    ${tvShow.total_episode_count} Episode${tvShow.total_episode_count !== 1 ? 's' : ''}
                </span>
            </div>
            <div class="availability-summary">
                ${getAvailabilitySummary(tvShow)}
            </div>
        </div>
    `;
    
    return card;
}

/**
 * Create season list view
 */
function createSeasonListView(tvShow) {
    const container = document.createElement('div');
    container.className = 'tv-show-seasons-view';

    // Header with back button and show poster
    const header = document.createElement('div');
    header.className = 'tv-show-header';

    const posterUrl = tvShow.thumbnail_url;
    const hasImage = posterUrl && posterUrl.trim().length > 0;

    header.innerHTML = `
        <button class="btn btn-back" onclick="backToTVShows()">
            <span class="btn-icon">←</span> Back to Shows
        </button>
        <div class="show-header-content">
            ${hasImage ? `
                <div class="show-poster">
                    <img src="${posterUrl}" alt="${tvShow.title}" class="show-poster-image"
                         onerror="this.style.display='none';">
                </div>
            ` : ''}
            <div class="show-info">
                <h2>${tvShow.title}</h2>
                <div class="show-stats">
                    ${tvShow.season_count} Season${tvShow.season_count !== 1 ? 's' : ''} •
                    ${tvShow.total_episode_count} Episode${tvShow.total_episode_count !== 1 ? 's' : ''}
                </div>
                <div class="show-availability-summary">
                    ${getAvailabilitySummary(tvShow)}
                </div>
            </div>
        </div>
    `;
    
    // Seasons list
    const seasonsList = document.createElement('div');
    seasonsList.className = 'seasons-list';
    
    tvShow.seasons.forEach(season => {
        const seasonCard = createSeasonCard(season, tvShow.id);
        seasonsList.appendChild(seasonCard);
    });
    
    container.appendChild(header);
    container.appendChild(seasonsList);
    
    return container;
}

/**
 * Create a season card
 */
function createSeasonCard(season, showId) {
    const card = document.createElement('div');
    card.className = 'season-card';
    card.dataset.seasonNumber = season.season_number;
    
    const availabilityClass = getAvailabilityClass(season.availability);
    const availabilityIcon = getAvailabilityIcon(season.availability);
    
    card.innerHTML = `
        <div class="season-header" onclick="toggleSeasonEpisodes('${showId}', ${season.season_number})">
            <div class="season-info">
                <h3 class="season-title">${season.title}</h3>
                <div class="season-stats">
                    ${season.episode_count} Episode${season.episode_count !== 1 ? 's' : ''}
                    ${season.year ? ` • ${season.year}` : ''}
                </div>
                <div class="availability-summary">
                    ${getSeasonAvailabilitySummary(season)}
                </div>
            </div>
            <div class="season-controls">
                <div class="availability-indicator ${availabilityClass}">
                    ${availabilityIcon}
                </div>
                <button class="btn btn-small btn-download" onclick="downloadSeason('${showId}', ${season.season_number}); event.stopPropagation();">
                    <span class="btn-icon">⬇️</span> Download Season
                </button>
                <span class="expand-icon">▼</span>
            </div>
        </div>
        <div class="season-episodes" id="episodes-${showId}-${season.season_number}" style="display: none;">
            ${createEpisodesList(season.episodes, showId, season.season_number)}
        </div>
    `;
    
    return card;
}

/**
 * Create episodes list for a season
 */
function createEpisodesList(episodes, showId, seasonNumber) {
    if (!episodes || episodes.length === 0) {
        return '<div class="no-episodes">No episodes available</div>';
    }
    
    let episodesHTML = '<div class="episodes-list">';
    
    episodes.forEach(episode => {
        const availabilityClass = getAvailabilityClass(episode.availability);
        const availabilityIcon = getAvailabilityIcon(episode.availability);
        
        episodesHTML += `
            <div class="episode-item" data-episode-id="${episode.media_item_id}">
                <div class="episode-info">
                    <div class="episode-number">E${episode.episode_number.toString().padStart(2, '0')}</div>
                    <div class="episode-details">
                        <h4 class="episode-title">${episode.title}</h4>
                        <div class="episode-meta">
                            ${episode.duration ? formatDuration(episode.duration) : ''}
                            ${episode.year ? ` • ${episode.year}` : ''}
                        </div>
                    </div>
                </div>
                <div class="episode-controls">
                    <div class="availability-indicator ${availabilityClass}">
                        ${availabilityIcon}
                    </div>
                    ${createEpisodeButtons(episode)}
                </div>
            </div>
        `;
    });
    
    episodesHTML += '</div>';
    return episodesHTML;
}

/**
 * Create action buttons for an episode
 */
function createEpisodeButtons(episode) {
    const buttons = [];
    
    // Local playback button
    if (episode.is_local_available) {
        buttons.push(`
            <button class="btn btn-small btn-play" onclick="playLocal('${episode.media_item_id}')">
                <span class="btn-icon">▶️</span> Play Local
            </button>
        `);
    }
    
    // Remote streaming button
    if (episode.is_remote_available) {
        buttons.push(`
            <button class="btn btn-small btn-stream" onclick="streamMedia('${episode.media_item_id}')">
                <span class="btn-icon">🌐</span> Stream
            </button>
        `);
        
        // Download button (only if not already local)
        if (!episode.is_local_available) {
            buttons.push(`
                <button class="btn btn-small btn-download" onclick="downloadMedia('${episode.media_item_id}')">
                    <span class="btn-icon">⬇️</span> Download
                </button>
            `);
        }
    }
    
    return buttons.join('');
}

/**
 * Get availability CSS class
 */
function getAvailabilityClass(availability) {
    switch (availability) {
        case 'complete_local':
        case 'local_only':
            return 'availability-local';
        case 'complete_remote':
        case 'remote_only':
            return 'availability-remote';
        case 'complete_both':
            return 'availability-both';
        case 'mixed':
            return 'availability-mixed';
        default:
            return 'availability-none';
    }
}

/**
 * Get availability icon
 */
function getAvailabilityIcon(availability) {
    switch (availability) {
        case 'complete_local':
        case 'local_only':
            return '💾';
        case 'complete_remote':
        case 'remote_only':
            return '🌐';
        case 'complete_both':
            return '💾🌐';
        case 'mixed':
            return '⚡';
        default:
            return '❌';
    }
}

/**
 * Get availability summary text for shows
 */
function getAvailabilitySummary(tvShow) {
    const local = tvShow.local_episode_count;
    const remote = tvShow.remote_episode_count;
    const total = tvShow.total_episode_count;
    
    if (local === total && remote === total) {
        return `All ${total} episodes available locally and remotely`;
    } else if (local === total) {
        return `All ${total} episodes available locally`;
    } else if (remote === total) {
        return `All ${total} episodes available remotely`;
    } else if (local > 0 && remote > 0) {
        return `${local} local, ${remote} remote of ${total} episodes`;
    } else if (local > 0) {
        return `${local} of ${total} episodes available locally`;
    } else if (remote > 0) {
        return `${remote} of ${total} episodes available remotely`;
    } else {
        return 'No episodes available';
    }
}

/**
 * Get availability summary text for seasons
 */
function getSeasonAvailabilitySummary(season) {
    const local = season.local_episode_count;
    const remote = season.remote_episode_count;
    const total = season.episode_count;
    
    if (local === total && remote === total) {
        return `All ${total} episodes (local + remote)`;
    } else if (local === total) {
        return `All ${total} episodes (local)`;
    } else if (remote === total) {
        return `All ${total} episodes (remote)`;
    } else if (local > 0 && remote > 0) {
        return `${local} local, ${remote} remote`;
    } else if (local > 0) {
        return `${local} local episodes`;
    } else if (remote > 0) {
        return `${remote} remote episodes`;
    } else {
        return 'No episodes available';
    }
}

/**
 * Format duration in minutes/hours
 */
function formatDuration(seconds) {
    if (!seconds) return '';

    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);

    if (hours > 0) {
        return `${hours}h ${minutes}m`;
    } else {
        return `${minutes}m`;
    }
}

// Navigation functions

/**
 * Show seasons view for a TV show
 */
function showTVShowSeasons(showId) {
    console.log('Showing seasons for show:', showId);

    // Find the show data
    const tvShow = window.tvShowsData?.find(show => show.id === showId);
    if (!tvShow) {
        console.error('TV show not found:', showId);
        showMessage('TV show not found', 'error');
        return;
    }

    currentTVShowView = 'seasons';
    currentShowData = tvShow;

    // Get the media grid container
    const mediaGrid = document.getElementById('mediaGrid');

    // Clear the media grid and remove any grid-specific styling
    mediaGrid.innerHTML = '';
    mediaGrid.style.display = 'block'; // Override grid display
    mediaGrid.style.gridTemplateColumns = 'none'; // Remove grid columns

    const seasonsView = createSeasonListView(tvShow);
    mediaGrid.appendChild(seasonsView);

    // Update the page title/header
    updateTVShowBreadcrumb(tvShow.title);
}

/**
 * Go back to TV shows list
 */
function backToTVShows() {
    console.log('Going back to TV shows list');

    currentTVShowView = 'shows';
    currentShowData = null;
    currentSeasonData = null;

    // Restore grid layout
    const mediaGrid = document.getElementById('mediaGrid');
    mediaGrid.style.display = ''; // Reset to default (should be grid)
    mediaGrid.style.gridTemplateColumns = ''; // Reset to default grid columns

    // Re-render the TV shows grid
    renderTVShowsGrid();

    // Update breadcrumb
    updateTVShowBreadcrumb();
}

/**
 * Toggle season episodes dropdown
 */
function toggleSeasonEpisodes(showId, seasonNumber) {
    console.log('Toggling episodes for season:', showId, seasonNumber);

    const episodesContainer = document.getElementById(`episodes-${showId}-${seasonNumber}`);
    const expandIcon = episodesContainer.parentElement.querySelector('.expand-icon');

    if (episodesContainer.style.display === 'none') {
        episodesContainer.style.display = 'block';
        expandIcon.textContent = '▲';
    } else {
        episodesContainer.style.display = 'none';
        expandIcon.textContent = '▼';
    }
}

/**
 * Download entire season
 */
async function downloadSeason(showId, seasonNumber) {
    console.log('Downloading season:', showId, seasonNumber);

    const tvShow = currentShowData || window.tvShowsData?.find(show => show.id === showId);
    if (!tvShow) {
        showMessage('TV show not found', 'error');
        return;
    }

    const season = tvShow.seasons.find(s => s.season_number === seasonNumber);
    if (!season) {
        showMessage('Season not found', 'error');
        return;
    }

    // Get episodes that are available remotely but not locally
    const episodesToDownload = season.episodes.filter(ep =>
        ep.is_remote_available && !ep.is_local_available
    );

    if (episodesToDownload.length === 0) {
        showMessage('All episodes in this season are already available locally', 'info');
        return;
    }

    // Confirm download
    const confirmMessage = `Download ${episodesToDownload.length} episode${episodesToDownload.length !== 1 ? 's' : ''} from ${season.title}?`;
    if (!confirm(confirmMessage)) {
        return;
    }

    // Start downloads
    let successCount = 0;
    let errorCount = 0;

    showMessage(`Starting download of ${episodesToDownload.length} episodes...`, 'info');

    for (const episode of episodesToDownload) {
        try {
            await downloadMedia(episode.media_item_id);
            successCount++;
        } catch (error) {
            console.error('Error downloading episode:', episode.title, error);
            errorCount++;
        }
    }

    // Show summary
    if (errorCount === 0) {
        showMessage(`Successfully started download of all ${successCount} episodes`, 'success');
    } else {
        showMessage(`Started ${successCount} downloads, ${errorCount} failed`, 'warning');
    }
}

/**
 * Update breadcrumb navigation
 */
function updateTVShowBreadcrumb(showTitle = null) {
    // Update the main section header
    const headerElement = document.getElementById('mainMediaSectionTitle');
    if (headerElement) {
        if (showTitle) {
            headerElement.textContent = showTitle;
        } else {
            headerElement.textContent = 'TV Shows';
        }
    }
}
