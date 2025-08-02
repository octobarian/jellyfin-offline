/**
 * Background Service Monitoring Test Suite
 * Tests the background monitoring system, intelligent polling, and media loading integration
 */

class BackgroundMonitoringTest {
    constructor() {
        this.testResults = [];
        this.statusManager = null;
        this.backgroundMonitor = null;
        this.mediaLoader = null;
    }

    /**
     * Run all background monitoring tests
     */
    async runAllTests() {
        console.log('=== Background Service Monitoring Test Suite ===');
        
        try {
            await this.testBackgroundMonitorInitialization();
            await this.testIntelligentPollingManagement();
            await this.testServiceStateTransitions();
            await this.testMediaLoadingIntegration();
            await this.testAutoRetryLogic();
            await this.testIdleDetection();
            
            this.displayTestResults();
            
        } catch (error) {
            console.error('Background monitoring test suite failed:', error);
        }
    }

    /**
     * Test background monitor initialization
     */
    async testBackgroundMonitorInitialization() {
        console.log('\n--- Testing Background Monitor Initialization ---');
        
        try {
            // Initialize status manager
            this.statusManager = new StatusManager({
                internetCheckTimeout: 2000,
                jellyfinCheckTimeout: 3000
            });
            
            // Initialize and start background monitoring
            await this.statusManager.initialize();
            this.statusManager.startBackgroundMonitoring({
                services: ['internet', 'jellyfin'],
                enableAdaptivePolling: true
            });
            
            // Verify background monitor was created
            this.assert(
                this.statusManager.backgroundMonitor !== null,
                'Background monitor should be created'
            );
            
            this.assert(
                this.statusManager.isMonitoring === true,
                'Status manager should be in monitoring state'
            );
            
            // Get monitoring status
            const monitoringStatus = this.statusManager.backgroundMonitor.getMonitoringStatus();
            
            this.assert(
                monitoringStatus.isMonitoring === true,
                'Background monitor should be active'
            );
            
            this.assert(
                monitoringStatus.monitoredServices.includes('internet'),
                'Internet service should be monitored'
            );
            
            this.assert(
                monitoringStatus.monitoredServices.includes('jellyfin'),
                'Jellyfin service should be monitored'
            );
            
            console.log('✓ Background monitor initialization test passed');
            this.testResults.push({ test: 'Background Monitor Initialization', status: 'PASSED' });
            
        } catch (error) {
            console.error('✗ Background monitor initialization test failed:', error);
            this.testResults.push({ test: 'Background Monitor Initialization', status: 'FAILED', error: error.message });
        }
    }

    /**
     * Test intelligent polling management
     */
    async testIntelligentPollingManagement() {
        console.log('\n--- Testing Intelligent Polling Management ---');
        
        try {
            const backgroundMonitor = this.statusManager.backgroundMonitor;
            
            // Test initial polling strategies
            const initialStatus = backgroundMonitor.getMonitoringStatus();
            
            this.assert(
                initialStatus.serviceStates.internet.pollingStrategy === 'normal',
                'Internet service should start with normal polling strategy'
            );
            
            // Simulate service stability (consecutive successes)
            const internetState = backgroundMonitor.serviceStates.get('internet');
            internetState.consecutiveSuccesses = 6; // Above stable threshold
            internetState.consecutiveFailures = 0;
            
            // Trigger polling strategy adjustment
            backgroundMonitor.adjustPollingStrategy('internet');
            
            const updatedStatus = backgroundMonitor.getMonitoringStatus();
            
            this.assert(
                updatedStatus.serviceStates.internet.pollingStrategy === 'slow',
                'Internet service should switch to slow polling after stability'
            );
            
            // Simulate service instability (consecutive failures)
            internetState.consecutiveSuccesses = 0;
            internetState.consecutiveFailures = 4; // Above unstable threshold
            
            backgroundMonitor.adjustPollingStrategy('internet');
            
            const failureStatus = backgroundMonitor.getMonitoringStatus();
            
            this.assert(
                failureStatus.serviceStates.internet.pollingStrategy === 'fast',
                'Internet service should switch to fast polling after failures'
            );
            
            // Test bandwidth-conscious mode
            this.statusManager.enableBandwidthConsciousMode(true);
            
            console.log('✓ Intelligent polling management test passed');
            this.testResults.push({ test: 'Intelligent Polling Management', status: 'PASSED' });
            
        } catch (error) {
            console.error('✗ Intelligent polling management test failed:', error);
            this.testResults.push({ test: 'Intelligent Polling Management', status: 'FAILED', error: error.message });
        }
    }

    /**
     * Test service state transitions
     */
    async testServiceStateTransitions() {
        console.log('\n--- Testing Service State Transitions ---');
        
        try {
            const backgroundMonitor = this.statusManager.backgroundMonitor;
            let transitionEventReceived = false;
            let recoveryEventReceived = false;
            
            // Listen for state transition events
            this.statusManager.on('serviceStateTransition', (data) => {
                transitionEventReceived = true;
                console.log('State transition event received:', data);
            });
            
            this.statusManager.on('serviceRecovered', (data) => {
                recoveryEventReceived = true;
                console.log('Service recovery event received:', data);
            });
            
            // Simulate service state change from connected to disconnected
            const oldStatus = { connected: true, lastCheck: Date.now() };
            const newStatus = { connected: false, lastCheck: Date.now(), error: 'Connection failed' };
            
            backgroundMonitor.updateServiceState('internet', newStatus, false);
            
            // Wait for events to be processed
            await new Promise(resolve => setTimeout(resolve, 100));
            
            this.assert(
                transitionEventReceived === true,
                'Service state transition event should be emitted'
            );
            
            // Simulate service recovery
            const recoveryStatus = { connected: true, lastCheck: Date.now() };
            backgroundMonitor.updateServiceState('internet', recoveryStatus, true);
            backgroundMonitor.handleServiceRecovery('internet', recoveryStatus);
            
            // Wait for events to be processed
            await new Promise(resolve => setTimeout(resolve, 100));
            
            this.assert(
                recoveryEventReceived === true,
                'Service recovery event should be emitted'
            );
            
            console.log('✓ Service state transitions test passed');
            this.testResults.push({ test: 'Service State Transitions', status: 'PASSED' });
            
        } catch (error) {
            console.error('✗ Service state transitions test failed:', error);
            this.testResults.push({ test: 'Service State Transitions', status: 'FAILED', error: error.message });
        }
    }

    /**
     * Test media loading integration
     */
    async testMediaLoadingIntegration() {
        console.log('\n--- Testing Media Loading Integration ---');
        
        try {
            // Initialize media loader with status manager
            this.mediaLoader = new ProgressiveMediaLoader(this.statusManager);
            
            this.assert(
                this.mediaLoader.statusManager === this.statusManager,
                'Media loader should be integrated with status manager'
            );
            
            this.assert(
                this.mediaLoader.statusEventListeners.size > 0,
                'Media loader should have status event listeners'
            );
            
            // Test seamless service recovery configuration
            this.mediaLoader.enableSeamlessServiceRecovery(true);
            
            this.assert(
                this.mediaLoader.retryConfig.retryOnServiceRecovery === true,
                'Seamless service recovery should be enabled'
            );
            
            // Test auto-retry configuration
            this.mediaLoader.configureAutoRetry({
                maxRetries: 5,
                retryDelay: 1000,
                exponentialBackoff: true
            });
            
            this.assert(
                this.mediaLoader.retryConfig.maxRetries === 5,
                'Auto-retry configuration should be applied'
            );
            
            // Test connectivity mode updates
            this.mediaLoader._updateConnectivityMode();
            
            this.assert(
                ['online', 'offline', 'degraded'].includes(this.mediaLoader.connectivityMode),
                'Connectivity mode should be valid'
            );
            
            // Test loading status with service integration
            const loadingStatus = this.mediaLoader.getLoadingStatus();
            
            this.assert(
                loadingStatus.serviceStatus !== undefined,
                'Loading status should include service status'
            );
            
            this.assert(
                loadingStatus.retryInfo !== undefined,
                'Loading status should include retry information'
            );
            
            console.log('✓ Media loading integration test passed');
            this.testResults.push({ test: 'Media Loading Integration', status: 'PASSED' });
            
        } catch (error) {
            console.error('✗ Media loading integration test failed:', error);
            this.testResults.push({ test: 'Media Loading Integration', status: 'FAILED', error: error.message });
        }
    }

    /**
     * Test automatic retry logic
     */
    async testAutoRetryLogic() {
        console.log('\n--- Testing Automatic Retry Logic ---');
        
        try {
            // Simulate Jellyfin failure
            this.mediaLoader.loadingStates.remote.status = 'error';
            this.mediaLoader.retryAttempts.set('jellyfin', 0);
            
            // Test retry attempt tracking
            const initialAttempts = this.mediaLoader.retryAttempts.get('jellyfin');
            
            this.assert(
                initialAttempts === 0,
                'Initial retry attempts should be 0'
            );
            
            // Simulate service recovery triggering retry
            let retryTriggered = false;
            
            // Mock the retry method to avoid actual network calls
            const originalRetry = this.mediaLoader._retryRemoteMediaLoading;
            this.mediaLoader._retryRemoteMediaLoading = async (reason) => {
                retryTriggered = true;
                console.log(`Retry triggered with reason: ${reason}`);
                return Promise.resolve();
            };
            
            // Trigger service recovery
            await this.mediaLoader._handleServiceRecovery({ service: 'jellyfin' });
            
            this.assert(
                retryTriggered === true,
                'Retry should be triggered on service recovery'
            );
            
            // Restore original method
            this.mediaLoader._retryRemoteMediaLoading = originalRetry;
            
            console.log('✓ Automatic retry logic test passed');
            this.testResults.push({ test: 'Automatic Retry Logic', status: 'PASSED' });
            
        } catch (error) {
            console.error('✗ Automatic retry logic test failed:', error);
            this.testResults.push({ test: 'Automatic Retry Logic', status: 'FAILED', error: error.message });
        }
    }

    /**
     * Test idle detection and polling adjustment
     */
    async testIdleDetection() {
        console.log('\n--- Testing Idle Detection ---');
        
        try {
            const backgroundMonitor = this.statusManager.backgroundMonitor;
            
            // Test initial idle state
            const initialIdleState = backgroundMonitor.isSystemIdle();
            
            this.assert(
                typeof initialIdleState === 'boolean',
                'Idle state should be a boolean'
            );
            
            // Simulate system becoming idle
            backgroundMonitor.lastActivity = Date.now() - (backgroundMonitor.config.idleTimeout + 1000);
            
            const idleState = backgroundMonitor.isSystemIdle();
            
            this.assert(
                idleState === true,
                'System should be detected as idle after timeout'
            );
            
            // Test idle polling strategy adjustment
            backgroundMonitor.adjustPollingStrategy('internet');
            
            const monitoringStatus = backgroundMonitor.getMonitoringStatus();
            
            this.assert(
                monitoringStatus.serviceStates.internet.currentInterval >= backgroundMonitor.config.idleInterval,
                'Polling interval should be adjusted for idle state'
            );
            
            console.log('✓ Idle detection test passed');
            this.testResults.push({ test: 'Idle Detection', status: 'PASSED' });
            
        } catch (error) {
            console.error('✗ Idle detection test failed:', error);
            this.testResults.push({ test: 'Idle Detection', status: 'FAILED', error: error.message });
        }
    }

    /**
     * Test immediate check functionality
     */
    async testImmediateCheck() {
        console.log('\n--- Testing Immediate Check ---');
        
        try {
            // Force immediate check
            const results = await this.statusManager.forceImmediateRefresh();
            
            this.assert(
                typeof results === 'object',
                'Immediate check should return results object'
            );
            
            console.log('✓ Immediate check test passed');
            this.testResults.push({ test: 'Immediate Check', status: 'PASSED' });
            
        } catch (error) {
            console.error('✗ Immediate check test failed:', error);
            this.testResults.push({ test: 'Immediate Check', status: 'FAILED', error: error.message });
        }
    }

    /**
     * Cleanup test resources
     */
    cleanup() {
        console.log('\n--- Cleaning Up Test Resources ---');
        
        try {
            if (this.statusManager) {
                this.statusManager.stopBackgroundMonitoring();
            }
            
            if (this.mediaLoader) {
                this.mediaLoader.destroy();
            }
            
            console.log('✓ Test cleanup completed');
            
        } catch (error) {
            console.error('✗ Test cleanup failed:', error);
        }
    }

    /**
     * Assert helper function
     */
    assert(condition, message) {
        if (!condition) {
            throw new Error(`Assertion failed: ${message}`);
        }
    }

    /**
     * Display test results summary
     */
    displayTestResults() {
        console.log('\n=== Test Results Summary ===');
        
        const passed = this.testResults.filter(r => r.status === 'PASSED').length;
        const failed = this.testResults.filter(r => r.status === 'FAILED').length;
        
        console.log(`Total Tests: ${this.testResults.length}`);
        console.log(`Passed: ${passed}`);
        console.log(`Failed: ${failed}`);
        
        if (failed > 0) {
            console.log('\nFailed Tests:');
            this.testResults
                .filter(r => r.status === 'FAILED')
                .forEach(r => {
                    console.log(`- ${r.test}: ${r.error}`);
                });
        }
        
        console.log(`\nOverall Status: ${failed === 0 ? 'PASSED' : 'FAILED'}`);
        
        // Cleanup after displaying results
        this.cleanup();
    }
}

// Export for module use
if (typeof module !== 'undefined' && module.exports) {
    module.exports = BackgroundMonitoringTest;
}

// Make available globally
window.BackgroundMonitoringTest = BackgroundMonitoringTest;

// Auto-run tests if this script is loaded directly
if (typeof window !== 'undefined' && window.StatusManager && window.BackgroundServiceMonitor) {
    console.log('Background monitoring components detected, running tests...');
    
    const testSuite = new BackgroundMonitoringTest();
    testSuite.runAllTests().catch(error => {
        console.error('Test suite execution failed:', error);
    });
}