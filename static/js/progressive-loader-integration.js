/**
 * Integration example for ProgressiveMediaLoader
 * Shows how to integrate with existing media loading functionality
 */

// Example integration with existing loadMediaLibrary function
function integrateProgressiveLoader() {
    // Create progressive loader instance
    const progressiveLoader = new ProgressiveMediaLoader();
    
    // Set up callbacks to handle loading events
    progressiveLoader.setCallbacks({
        onLocalLoaded: (localMedia, unifiedMedia) => {
            console.log('Local media loaded:', localMedia.length, 'items');
            
            // Update UI with local media immediately
            if (typeof mediaData !== 'undefined') {
                mediaData = unifiedMedia;
                if (typeof filterMedia === 'function') {
                    filterMedia(); // Trigger existing filter/render logic
                }
            }
            
            // Update loading indicator
            const loadingIndicator = document.getElementById('loadingIndicator');
            if (loadingIndicator) {
                loadingIndicator.innerHTML = '<p>Loading remote media...</p>';
            }
        },
        
        onRemoteLoaded: (remoteMedia, unifiedMedia) => {
            console.log('Remote media loaded:', remoteMedia.length, 'items');
            
            // Update UI with complete media list
            if (typeof mediaData !== 'undefined') {
                mediaData = unifiedMedia;
                if (typeof filterMedia === 'function') {
                    filterMedia(); // Trigger existing filter/render logic
                }
            }
        },
        
        onComplete: (unifiedMedia) => {
            console.log('Progressive loading complete:', unifiedMedia.length, 'total items');
            
            // Hide loading indicator
            const loadingIndicator = document.getElementById('loadingIndicator');
            if (loadingIndicator) {
                loadingIndicator.style.display = 'none';
            }
            
            // Cache the unified data for offline use
            try {
                localStorage.setItem('mediaCache', JSON.stringify({
                    media: unifiedMedia,
                    timestamp: Date.now()
                }));
            } catch (error) {
                console.warn('Failed to cache unified media data:', error);
            }
        },
        
        onError: (error) => {
            console.error('Progressive loading error:', error);
            
            // Show error message to user
            if (typeof showMessage === 'function') {
                if (error.message.includes('local-only mode')) {
                    showMessage('Remote media unavailable - showing local content only', 'warning');
                } else {
                    showMessage('Error loading media: ' + error.message, 'error');
                }
            }
        },
        
        onLoadingStateChange: (states, message) => {
            console.log('Loading state changed:', message, states);
            
            // Update loading indicator with current state
            const loadingIndicator = document.getElementById('loadingIndicator');
            if (loadingIndicator && (states.local || states.remote)) {
                loadingIndicator.innerHTML = `<p>${message}</p>`;
                loadingIndicator.style.display = 'block';
            }
        }
    });
    
    return progressiveLoader;
}

// Enhanced loadMediaLibrary function using progressive loading
async function loadMediaLibraryProgressive(forceRefresh = false) {
    const mediaGrid = document.getElementById('mediaGrid');
    const noMedia = document.getElementById('noMedia');
    
    // Clear previous content
    if (mediaGrid) mediaGrid.innerHTML = '';
    if (noMedia) noMedia.style.display = 'none';
    
    console.log('Starting progressive media loading...');
    
    try {
        // Create and configure progressive loader
        const progressiveLoader = integrateProgressiveLoader();
        
        // Start progressive loading
        await progressiveLoader.loadMedia(forceRefresh);
        
        console.log('Progressive media loading completed successfully');
        
    } catch (error) {
        console.error('Progressive media loading failed:', error);
        
        // Fallback to cache if available
        if (typeof tryLoadFromCache === 'function') {
            const cacheLoaded = tryLoadFromCache();
            if (!cacheLoaded) {
                // Show no media message if cache also fails
                if (noMedia) noMedia.style.display = 'block';
            }
        }
    }
}

// Example of how to replace existing loadMediaLibrary calls
function replaceExistingLoader() {
    // Store reference to original function if needed
    if (typeof loadMediaLibrary !== 'undefined') {
        window.originalLoadMediaLibrary = loadMediaLibrary;
    }
    
    // Replace with progressive version
    window.loadMediaLibrary = loadMediaLibraryProgressive;
    
    console.log('Progressive media loader integrated successfully');
}

// Auto-integration when script loads (optional)
document.addEventListener('DOMContentLoaded', function() {
    // Only integrate if ProgressiveMediaLoader is available
    if (typeof ProgressiveMediaLoader !== 'undefined') {
        console.log('ProgressiveMediaLoader available - integration ready');
        
        // Uncomment the line below to automatically replace the existing loader
        // replaceExistingLoader();
    }
});

// Export functions for manual integration
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        integrateProgressiveLoader,
        loadMediaLibraryProgressive,
        replaceExistingLoader
    };
}