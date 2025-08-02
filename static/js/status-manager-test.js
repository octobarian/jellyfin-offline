/**
 * Simple test script for StatusManager
 * This can be run in the browser console to verify functionality
 */

async function testStatusManager() {
    console.log('=== StatusManager Test ===');
    
    try {
        // Create a new StatusManager instance
        const statusManager = new StatusManager({
            internetCheckTimeout: 2000,
            jellyfinCheckTimeout: 3000,
            cacheExpiration: 10000
        });
        
        console.log('✓ StatusManager created successfully');
        
        // Test event registration
        let eventsFired = [];
        
        statusManager.on('initialized', (data) => {
            eventsFired.push('initialized');
            console.log('✓ Initialized event fired:', data);
        });
        
        statusManager.on('statusChange', (data) => {
            eventsFired.push(`statusChange:${data.service}`);
            console.log('✓ Status change event fired:', data);
        });
        
        statusManager.on('connectivityChange', (data) => {
            eventsFired.push(`connectivityChange:${data.service}`);
            console.log('✓ Connectivity change event fired:', data);
        });
        
        console.log('✓ Event listeners registered');
        
        // Test initialization
        console.log('Starting initialization...');
        const initialStatus = await statusManager.initialize();
        
        console.log('✓ Initialization completed:', initialStatus);
        
        // Test individual status checks
        console.log('Testing individual status checks...');
        
        const internetStatus = await statusManager.checkInternetConnectivity();
        console.log('✓ Internet check:', internetStatus);
        
        const jellyfinStatus = await statusManager.checkJellyfinConnectivity();
        console.log('✓ Jellyfin check:', jellyfinStatus);
        
        const vlcStatus = await statusManager.checkVLCAvailability();
        console.log('✓ VLC check:', vlcStatus);
        
        const localMediaStatus = await statusManager.checkLocalMediaAvailability();
        console.log('✓ Local media check:', localMediaStatus);
        
        // Test cache functionality
        console.log('Testing cache functionality...');
        statusManager.clearCache('internet');
        console.log('✓ Cache cleared for internet');
        
        // Test status retrieval
        const currentStatus = statusManager.getStatus();
        console.log('✓ Current status retrieved:', currentStatus);
        
        const internetStatusOnly = statusManager.getStatus('internet');
        console.log('✓ Internet status only:', internetStatusOnly);
        
        // Test adaptive polling (brief test)
        console.log('Testing adaptive polling...');
        statusManager.startAdaptivePolling({
            initialInterval: 5000,
            services: ['internet', 'jellyfin']
        });
        console.log('✓ Adaptive polling started');
        
        // Wait a moment then stop
        setTimeout(() => {
            statusManager.stopAdaptivePolling();
            console.log('✓ Adaptive polling stopped');
            
            // Test Jellyfin skip optimization
            statusManager.enableJellyfinSkipOptimization(true);
            console.log('✓ Jellyfin skip optimization enabled');
            
            statusManager.enableJellyfinSkipOptimization(false);
            console.log('✓ Jellyfin skip optimization disabled');
            
            // Get adaptive polling state
            const pollingState = statusManager.getAdaptivePollingState();
            console.log('✓ Adaptive polling state:', pollingState);
            
            console.log('=== Test Summary ===');
            console.log(`Events fired: ${eventsFired.length}`);
            console.log('Event types:', [...new Set(eventsFired)]);
            console.log('✅ All tests completed successfully!');
            
        }, 2000);
        
    } catch (error) {
        console.error('❌ Test failed:', error);
        throw error;
    }
}

// Export test function
window.testStatusManager = testStatusManager;

console.log('StatusManager test loaded. Run testStatusManager() to execute tests.');