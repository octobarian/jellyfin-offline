/**
 * Progressive Loading Test Module
 * 
 * Development utility for testing progressive loading functionality
 * and debugging media loading phases.
 */

(function() {
    'use strict';

    // Test configuration
    const TEST_CONFIG = {
        enabled: false, // Set to true to enable testing
        logLevel: 'info', // 'debug', 'info', 'warn', 'error'
        testInterval: 30000, // 30 seconds between tests
        maxRetries: 3
    };

    // Test state
    let testState = {
        running: false,
        currentTest: null,
        results: [],
        retryCount: 0
    };

    /**
     * Log test messages with appropriate level
     */
    function testLog(level, message, data = null) {
        const levels = ['debug', 'info', 'warn', 'error'];
        const configLevel = levels.indexOf(TEST_CONFIG.logLevel);
        const messageLevel = levels.indexOf(level);
        
        if (messageLevel >= configLevel) {
            const prefix = `[ProgressiveLoadingTest]`;
            if (data) {
                console[level](`${prefix} ${message}`, data);
            } else {
                console[level](`${prefix} ${message}`);
            }
        }
    }

    /**
     * Test media loading performance
     */
    async function testMediaLoading() {
        testLog('info', 'Starting media loading test...');
        const startTime = performance.now();
        
        try {
            const response = await fetch('/api/media?mode=unified&force_refresh=true');
            const data = await response.json();
            const endTime = performance.now();
            const duration = endTime - startTime;
            
            const result = {
                timestamp: new Date().toISOString(),
                duration: Math.round(duration),
                success: response.ok,
                mediaCount: data.count || 0,
                loadingPhase: data.loading_phase,
                errors: data.loading_metadata?.errors || []
            };
            
            testState.results.push(result);
            testLog('info', `Media loading test completed in ${duration}ms`, result);
            
            return result;
        } catch (error) {
            const endTime = performance.now();
            const duration = endTime - startTime;
            
            const result = {
                timestamp: new Date().toISOString(),
                duration: Math.round(duration),
                success: false,
                error: error.message,
                mediaCount: 0
            };
            
            testState.results.push(result);
            testLog('error', `Media loading test failed after ${duration}ms`, result);
            
            return result;
        }
    }

    /**
     * Test system status endpoint
     */
    async function testSystemStatus() {
        testLog('info', 'Testing system status...');
        
        try {
            const response = await fetch('/api/status');
            const data = await response.json();
            
            const result = {
                timestamp: new Date().toISOString(),
                success: response.ok,
                servicesReady: data.services_ready,
                overallStatus: data.system_health?.overall_status,
                jellyfinConnected: data.services?.jellyfin?.connected,
                vlcInstalled: data.services?.vlc?.installed,
                localMediaAvailable: data.services?.local_media?.available
            };
            
            testLog('info', 'System status test completed', result);
            return result;
        } catch (error) {
            testLog('error', 'System status test failed', { error: error.message });
            return { success: false, error: error.message };
        }
    }

    /**
     * Run comprehensive test suite
     */
    async function runTestSuite() {
        if (testState.running) {
            testLog('warn', 'Test suite already running, skipping...');
            return;
        }
        
        testState.running = true;
        testLog('info', 'Starting progressive loading test suite...');
        
        try {
            // Test system status first
            const statusResult = await testSystemStatus();
            
            // Test media loading
            const mediaResult = await testMediaLoading();
            
            // Analyze results
            const analysis = {
                timestamp: new Date().toISOString(),
                systemHealthy: statusResult.success && statusResult.servicesReady,
                mediaLoadingWorking: mediaResult.success && mediaResult.mediaCount > 0,
                recommendations: []
            };
            
            if (!statusResult.servicesReady) {
                analysis.recommendations.push('Services not ready - check system status');
            }
            
            if (!statusResult.jellyfinConnected) {
                analysis.recommendations.push('Jellyfin not connected - check configuration');
            }
            
            if (mediaResult.mediaCount === 0) {
                analysis.recommendations.push('No media found - check media paths and Jellyfin connection');
            }
            
            if (mediaResult.duration > 10000) {
                analysis.recommendations.push('Media loading is slow - consider optimizing');
            }
            
            testLog('info', 'Test suite completed', analysis);
            
            // Reset retry count on successful test
            testState.retryCount = 0;
            
        } catch (error) {
            testLog('error', 'Test suite failed', { error: error.message });
            
            // Implement retry logic
            testState.retryCount++;
            if (testState.retryCount < TEST_CONFIG.maxRetries) {
                testLog('info', `Retrying test suite (attempt ${testState.retryCount + 1}/${TEST_CONFIG.maxRetries})`);
                setTimeout(runTestSuite, 5000); // Retry after 5 seconds
            } else {
                testLog('error', 'Max retries reached, stopping test suite');
                testState.retryCount = 0;
            }
        } finally {
            testState.running = false;
        }
    }

    /**
     * Initialize progressive loading tests
     */
    function initializeTests() {
        if (!TEST_CONFIG.enabled) {
            testLog('debug', 'Progressive loading tests disabled');
            return;
        }
        
        testLog('info', 'Initializing progressive loading tests...');
        
        // Run initial test after page load
        setTimeout(runTestSuite, 2000);
        
        // Schedule periodic tests
        setInterval(runTestSuite, TEST_CONFIG.testInterval);
        
        // Expose test functions to global scope for manual testing
        window.progressiveLoadingTest = {
            runTestSuite,
            testMediaLoading,
            testSystemStatus,
            getResults: () => testState.results,
            enable: () => { TEST_CONFIG.enabled = true; initializeTests(); },
            disable: () => { TEST_CONFIG.enabled = false; }
        };
        
        testLog('info', 'Progressive loading tests initialized');
        testLog('info', 'Use window.progressiveLoadingTest.runTestSuite() to run tests manually');
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initializeTests);
    } else {
        initializeTests();
    }

})();