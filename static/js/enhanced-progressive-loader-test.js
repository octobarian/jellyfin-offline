/**
 * Test script for Enhanced Progressive Media Loader
 * Tests the non-blocking loading functionality
 */

// Test the enhanced progressive media loader
async function testEnhancedProgressiveLoader() {
    console.log('=== Testing Enhanced Progressive Media Loader ===');
    
    // Create a mock status manager for testing
    const mockStatusManager = {
        getStatus: (service) => {
            const mockStatuses = {
                internet: { connected: true, lastCheck: Date.now() },
                jellyfin: { connected: true, lastCheck: Date.now() },
                localMedia: { available: true, count: 10 }
            };
            return service ? mockStatuses[service] : mockStatuses;
        },
        on: (event, callback) => {
            console.log(`Mock StatusManager: Registered listener for ${event}`);
        },
        off: (event, callback) => {
            console.log(`Mock StatusManager: Removed listener for ${event}`);
        }
    };
    
    // Create enhanced loader instance
    const loader = new ProgressiveMediaLoader(mockStatusManager);
    
    // Set up callbacks to monitor the loading process
    loader.setCallbacks({
        onLocalLoaded: (localMedia, unifiedMedia) => {
            console.log(`✓ Local media loaded: ${localMedia.length} items`);
            console.log(`✓ User interaction should be enabled now`);
        },
        
        onUserInteractionEnabled: (data) => {
            console.log(`✓ User interaction enabled after ${data.timeToInteraction}ms`);
            console.log(`✓ Local media count: ${data.localMediaCount}`);
        },
        
        onBackgroundTasksStarted: (options) => {
            console.log(`✓ Background tasks started with options:`, options);
        },
        
        onRemoteLoaded: (remoteMedia, unifiedMedia, integrationEvent) => {
            console.log(`✓ Remote media loaded: ${remoteMedia.length} items`);
            console.log(`✓ Total unified media: ${unifiedMedia.length} items`);
            if (integrationEvent) {
                console.log(`✓ Seamless integration: ${integrationEvent.stats.newItemsAdded} new items added`);
            }
        },
        
        onBackgroundTasksCompleted: (result) => {
            console.log(`✓ Background tasks completed in ${result.mode} mode`);
            console.log(`✓ Final counts - Local: ${result.localCount}, Remote: ${result.remoteCount}, Total: ${result.totalCount}`);
        },
        
        onComplete: (unifiedMedia) => {
            console.log(`✓ Loading complete: ${unifiedMedia.length} total items`);
        },
        
        onLoadingStateChange: (state, message, indicators) => {
            console.log(`📊 Loading state: ${message}`);
            if (indicators) {
                console.log(`📊 Progress: ${indicators.progress.percentage}%`);
            }
        },
        
        onError: (error, errorInfo) => {
            console.error(`❌ Error in ${errorInfo.phase}: ${error.message}`);
        }
    });
    
    // Test the loading process
    console.log('\n--- Starting Non-Blocking Load Test ---');
    
    try {
        // Start the enhanced loading process
        const startTime = Date.now();
        await loader.loadMedia(false);
        
        // Check loading state
        const loadingState = loader.getLoadingState();
        console.log('\n--- Loading State Check ---');
        console.log(`Phase: ${loadingState.phase}`);
        console.log(`User interaction enabled: ${loadingState.userInteractionEnabled}`);
        console.log(`Background tasks active: ${loadingState.backgroundTasksActive}`);
        console.log(`Connectivity mode: ${loadingState.connectivityMode}`);
        console.log(`Loading strategy: ${loadingState.loadingStrategy}`);
        
        // Check performance metrics
        const metrics = loader.getPerformanceMetrics();
        console.log('\n--- Performance Metrics ---');
        console.log(`Time to first interaction: ${metrics.timeToFirstInteraction}ms`);
        console.log(`Time to local complete: ${metrics.timeToLocalComplete}ms`);
        console.log(`Time to remote complete: ${metrics.timeToRemoteComplete}ms`);
        
        // Test status manager integration
        console.log('\n--- Testing Status Manager Integration ---');
        
        // Simulate connectivity changes
        loader.onStatusChange('connectivityModeChange', {
            oldMode: 'online',
            newMode: 'degraded'
        });
        
        loader.onStatusChange('internet:disconnected', {
            service: 'internet',
            connected: false
        });
        
        loader.onStatusChange('internet:connected', {
            service: 'internet', 
            connected: true
        });
        
        // Test loading indicators
        console.log('\n--- Testing Loading Indicators ---');
        const indicator1 = loader.createLoadingIndicators('checking_connectivity', { current: 1, total: 3 });
        console.log(`Indicator 1: ${indicator1.message} (${indicator1.progress.percentage}%)`);
        
        const indicator2 = loader.createLoadingIndicators('loading_remote_data', { current: 2, total: 3 });
        console.log(`Indicator 2: ${indicator2.message} (${indicator2.progress.percentage}%)`);
        
        // Test service unavailability handling
        console.log('\n--- Testing Service Unavailability ---');
        loader.handleServiceUnavailability('jellyfin', new Error('Connection timeout'));
        
        const totalTime = Date.now() - startTime;
        console.log(`\n✅ Enhanced Progressive Loader test completed in ${totalTime}ms`);
        
        return true;
        
    } catch (error) {
        console.error('❌ Enhanced Progressive Loader test failed:', error);
        return false;
    }
}

// Run the test when the page loads
if (typeof window !== 'undefined') {
    window.testEnhancedProgressiveLoader = testEnhancedProgressiveLoader;
    
    // Auto-run test if this script is loaded directly
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            setTimeout(testEnhancedProgressiveLoader, 1000);
        });
    } else {
        setTimeout(testEnhancedProgressiveLoader, 1000);
    }
}

console.log('Enhanced Progressive Media Loader test script loaded');