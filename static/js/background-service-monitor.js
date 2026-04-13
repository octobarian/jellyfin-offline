/**
 * Background Service Monitor - Continuous status monitoring without blocking UI
 * Implements intelligent polling, connection state transitions, and adaptive frequencies
 */

class BackgroundServiceMonitor {
    constructor(statusManager, options = {}) {
        this.statusManager = statusManager;
        
        // Configuration with intelligent defaults
        this.config = {
            // Polling intervals (milliseconds)
            fastInterval: 5000,      // 5 seconds for unstable services
            normalInterval: 15000,   // 15 seconds for normal monitoring
            slowInterval: 60000,     // 60 seconds for stable services
            idleInterval: 300000,    // 5 minutes when idle
            
            // Adaptive thresholds
            stableThreshold: 5,      // Consecutive successes to consider stable
            unstableThreshold: 3,    // Consecutive failures to consider unstable
            idleTimeout: 600000,     // 10 minutes before considering idle
            
            // Performance limits
            maxConcurrentChecks: 3,
            checkTimeout: 10000,     // 10 seconds max per check
            
            ...options
        };
        
        // Monitoring state
        this.isMonitoring = false;
        this.monitoringIntervals = new Map();
        this.serviceStates = new Map();
        this.lastActivity = Date.now();
        
        // Performance tracking
        this.metrics = {
            checksPerformed: 0,
            averageCheckTime: 0,
            failureRate: 0,
            lastOptimization: Date.now()
        };
        
        // Initialize service states
        this.initializeServiceStates();
        
        console.log('BackgroundServiceMonitor: Initialized with config:', this.config);
    }

    /**
     * Initialize service state tracking
     * @private
     */
    initializeServiceStates() {
        const services = ['internet', 'jellyfin', 'vlc', 'localMedia'];
        
        services.forEach(service => {
            this.serviceStates.set(service, {
                status: 'unknown',
                consecutiveSuccesses: 0,
                consecutiveFailures: 0,
                lastCheck: 0,
                lastSuccess: 0,
                lastFailure: 0,
                pollingStrategy: 'normal',
                currentInterval: this.config.normalInterval,
                enabled: true,
                checkInProgress: false
            });
        });
    }

    /**
     * Start background monitoring for specified services
     * @param {Array<string>} services - Services to monitor
     * @param {Object} options - Monitoring options
     */
    startMonitoring(services = ['internet', 'jellyfin'], options = {}) {
        if (this.isMonitoring) {
            console.log('BackgroundServiceMonitor: Already monitoring, updating services');
            this.updateMonitoredServices(services);
            return;
        }

        console.log('BackgroundServiceMonitor: Starting monitoring for services:', services);
        
        this.isMonitoring = true;
        this.lastActivity = Date.now();
        
        // Start monitoring each service
        services.forEach(service => {
            if (this.serviceStates.has(service)) {
                this.startServiceMonitoring(service);
            }
        });
        
        // Start idle detection
        this.startIdleDetection();
        
        // Emit monitoring started event
        this.statusManager.emit('backgroundMonitoringStarted', {
            services,
            timestamp: Date.now()
        });
    }

    /**
     * Stop background monitoring
     * @param {string|null} service - Specific service to stop, or null for all
     */
    stopMonitoring(service = null) {
        if (service) {
            console.log(`BackgroundServiceMonitor: Stopping monitoring for ${service}`);
            this.stopServiceMonitoring(service);
        } else {
            console.log('BackgroundServiceMonitor: Stopping all monitoring');
            
            // Stop all service monitoring
            this.monitoringIntervals.forEach((intervalId, serviceName) => {
                clearInterval(intervalId);
            });
            this.monitoringIntervals.clear();
            
            // Stop idle detection
            if (this.idleDetectionInterval) {
                clearInterval(this.idleDetectionInterval);
                this.idleDetectionInterval = null;
            }
            
            this.isMonitoring = false;
            
            // Emit monitoring stopped event
            this.statusManager.emit('backgroundMonitoringStopped', {
                timestamp: Date.now()
            });
        }
    }

    /**
     * Start monitoring for a specific service
     * @private
     * @param {string} service - Service name
     */
    startServiceMonitoring(service) {
        const serviceState = this.serviceStates.get(service);
        if (!serviceState || !serviceState.enabled) {
            return;
        }

        // Clear existing interval if any
        this.stopServiceMonitoring(service);

        console.log(`BackgroundServiceMonitor: Starting monitoring for ${service} with ${serviceState.currentInterval}ms interval`);

        // Schedule first check immediately
        this.performServiceCheck(service);

        // Set up recurring checks
        const intervalId = setInterval(() => {
            this.performServiceCheck(service);
        }, serviceState.currentInterval);

        this.monitoringIntervals.set(service, intervalId);
    }

    /**
     * Stop monitoring for a specific service
     * @private
     * @param {string} service - Service name
     */
    stopServiceMonitoring(service) {
        const intervalId = this.monitoringIntervals.get(service);
        if (intervalId) {
            clearInterval(intervalId);
            this.monitoringIntervals.delete(service);
        }
    }

    /**
     * Perform status check for a specific service
     * @private
     * @param {string} service - Service name
     */
    async performServiceCheck(service) {
        const serviceState = this.serviceStates.get(service);
        if (!serviceState || serviceState.checkInProgress) {
            return;
        }

        serviceState.checkInProgress = true;
        const startTime = Date.now();

        try {
            console.log(`BackgroundServiceMonitor: Checking ${service} status`);
            
            let result;
            const oldStatus = this.statusManager.getStatus(service);

            // Perform appropriate check based on service type
            switch (service) {
                case 'internet':
                    result = await this.statusManager.checkInternetConnectivity();
                    break;
                case 'jellyfin':
                    // Only check Jellyfin if internet is available
                    if (this.statusManager.getStatus('internet')?.connected) {
                        result = await this.statusManager.checkJellyfinConnectivity();
                    } else {
                        result = { connected: false, lastCheck: Date.now(), error: 'No internet connection' };
                    }
                    break;
                case 'vlc':
                    result = await this.statusManager.checkVLCAvailability();
                    break;
                case 'localMedia':
                    result = await this.statusManager.checkLocalMediaAvailability();
                    break;
                default:
                    console.warn(`BackgroundServiceMonitor: Unknown service ${service}`);
                    return;
            }

            const checkDuration = Date.now() - startTime;
            this.updateMetrics(true, checkDuration);

            // Update service state
            this.updateServiceState(service, result, true);

            // Update status manager
            this.statusManager.setStatus(service, result);

            // Detect and handle state transitions
            this.handleStateTransition(service, oldStatus, result);

            console.log(`BackgroundServiceMonitor: ${service} check completed in ${checkDuration}ms`);

        } catch (error) {
            const checkDuration = Date.now() - startTime;
            this.updateMetrics(false, checkDuration);

            console.error(`BackgroundServiceMonitor: ${service} check failed:`, error);

            // Update service state for failure
            this.updateServiceState(service, null, false, error);

            // Emit error event
            this.statusManager.emit('backgroundCheckError', {
                service,
                error: error.message,
                timestamp: Date.now()
            });

        } finally {
            serviceState.checkInProgress = false;
            serviceState.lastCheck = Date.now();
        }
    }

    /**
     * Update service state based on check result
     * @private
     * @param {string} service - Service name
     * @param {Object|null} result - Check result
     * @param {boolean} success - Whether check was successful
     * @param {Error} error - Error if check failed
     */
    updateServiceState(service, result, success, error = null) {
        const serviceState = this.serviceStates.get(service);
        if (!serviceState) return;

        const wasConnected = serviceState.status === 'connected' || serviceState.status === 'available';
        let isConnected = false;

        if (success && result) {
            // Determine connection status based on service type
            if (service === 'internet' || service === 'jellyfin') {
                isConnected = result.connected === true;
            } else if (service === 'vlc' || service === 'localMedia') {
                isConnected = result.available === true;
            }

            serviceState.status = isConnected ? (service === 'vlc' || service === 'localMedia' ? 'available' : 'connected') : 'disconnected';
        } else {
            serviceState.status = 'error';
            isConnected = false;
        }

        // Update consecutive counters
        if (success && isConnected) {
            serviceState.consecutiveSuccesses++;
            serviceState.consecutiveFailures = 0;
            serviceState.lastSuccess = Date.now();
        } else {
            serviceState.consecutiveFailures++;
            serviceState.consecutiveSuccesses = 0;
            serviceState.lastFailure = Date.now();
        }

        // Adjust polling strategy based on stability
        this.adjustPollingStrategy(service);

        // Log state transitions
        if (wasConnected !== isConnected) {
            const transition = isConnected ? 'connected' : 'disconnected';
            console.log(`BackgroundServiceMonitor: ${service} transitioned to ${transition}`);
            
            this.statusManager.emit('serviceStateTransition', {
                service,
                oldState: wasConnected ? 'connected' : 'disconnected',
                newState: transition,
                timestamp: Date.now()
            });
        }
    }

    /**
     * Adjust polling strategy based on service stability
     * @private
     * @param {string} service - Service name
     */
    adjustPollingStrategy(service) {
        const serviceState = this.serviceStates.get(service);
        if (!serviceState) return;

        const oldStrategy = serviceState.pollingStrategy;
        const oldInterval = serviceState.currentInterval;

        // Determine new strategy based on consecutive results
        if (serviceState.consecutiveSuccesses >= this.config.stableThreshold) {
            serviceState.pollingStrategy = 'slow';
            serviceState.currentInterval = this.config.slowInterval;
        } else if (serviceState.consecutiveFailures >= this.config.unstableThreshold) {
            serviceState.pollingStrategy = 'fast';
            serviceState.currentInterval = this.config.fastInterval;
        } else {
            serviceState.pollingStrategy = 'normal';
            serviceState.currentInterval = this.config.normalInterval;
        }

        // Apply idle adjustment if system is idle
        if (this.isSystemIdle()) {
            serviceState.currentInterval = Math.max(serviceState.currentInterval, this.config.idleInterval);
        }

        // Restart monitoring if interval changed
        if (oldInterval !== serviceState.currentInterval) {
            console.log(`BackgroundServiceMonitor: ${service} polling strategy changed from ${oldStrategy} (${oldInterval}ms) to ${serviceState.pollingStrategy} (${serviceState.currentInterval}ms)`);
            
            if (this.monitoringIntervals.has(service)) {
                this.startServiceMonitoring(service);
            }

            this.statusManager.emit('pollingStrategyChanged', {
                service,
                oldStrategy,
                newStrategy: serviceState.pollingStrategy,
                oldInterval,
                newInterval: serviceState.currentInterval,
                timestamp: Date.now()
            });
        }
    }

    /**
     * Handle connection state transitions
     * @private
     * @param {string} service - Service name
     * @param {Object} oldStatus - Previous status
     * @param {Object} newStatus - New status
     */
    handleStateTransition(service, oldStatus, newStatus) {
        if (!oldStatus || !newStatus) return;

        // Check for connection state changes
        const wasConnected = this.getConnectionState(service, oldStatus);
        const isConnected = this.getConnectionState(service, newStatus);

        if (wasConnected !== isConnected) {
            const transitionType = isConnected ? 'recovery' : 'failure';
            
            console.log(`BackgroundServiceMonitor: ${service} ${transitionType} detected`);

            // Handle specific transition types
            if (transitionType === 'recovery') {
                this.handleServiceRecovery(service, newStatus);
            } else {
                this.handleServiceFailure(service, newStatus);
            }

            // Emit transition event
            this.statusManager.emit('connectionStateTransition', {
                service,
                transitionType,
                oldStatus,
                newStatus,
                timestamp: Date.now()
            });
        }
    }

    /**
     * Get connection state for a service
     * @private
     * @param {string} service - Service name
     * @param {Object} status - Status object
     * @returns {boolean} Connection state
     */
    getConnectionState(service, status) {
        if (service === 'internet' || service === 'jellyfin') {
            return status.connected === true;
        } else if (service === 'vlc' || service === 'localMedia') {
            return status.available === true;
        }
        return false;
    }

    /**
     * Handle service recovery
     * @private
     * @param {string} service - Service name
     * @param {Object} status - New status
     */
    handleServiceRecovery(service, status) {
        console.log(`BackgroundServiceMonitor: Handling ${service} recovery`);

        // Reset failure counters
        const serviceState = this.serviceStates.get(service);
        if (serviceState) {
            serviceState.consecutiveFailures = 0;
        }

        // Service-specific recovery actions
        if (service === 'jellyfin') {
            // Enable skip optimization for confirmed Jellyfin connection
            this.statusManager.enableJellyfinSkipOptimization(true);
            
            // Trigger remote media loading if needed
            this.statusManager.emit('jellyfinRecovered', { status, timestamp: Date.now() });
        }

        // Emit recovery event
        this.statusManager.emit('serviceRecovered', {
            service,
            status,
            timestamp: Date.now()
        });
    }

    /**
     * Handle service failure
     * @private
     * @param {string} service - Service name
     * @param {Object} status - New status
     */
    handleServiceFailure(service, status) {
        console.log(`BackgroundServiceMonitor: Handling ${service} failure`);

        // Service-specific failure actions
        if (service === 'jellyfin') {
            // Disable skip optimization when Jellyfin fails
            this.statusManager.enableJellyfinSkipOptimization(false);
            
            // Switch to local-only mode
            this.statusManager.emit('jellyfinFailed', { status, timestamp: Date.now() });
        }

        // Emit failure event
        this.statusManager.emit('serviceFailed', {
            service,
            status,
            timestamp: Date.now()
        });
    }

    /**
     * Start idle detection to optimize polling during inactivity
     * @private
     */
    startIdleDetection() {
        // Track user activity
        const activityEvents = ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart'];
        
        const updateActivity = () => {
            this.lastActivity = Date.now();
        };

        activityEvents.forEach(event => {
            document.addEventListener(event, updateActivity, { passive: true });
        });

        // Check for idle state periodically
        this.idleDetectionInterval = setInterval(() => {
            const timeSinceActivity = Date.now() - this.lastActivity;
            const wasIdle = this.isSystemIdle();
            const isIdle = timeSinceActivity > this.config.idleTimeout;

            if (wasIdle !== isIdle) {
                console.log(`BackgroundServiceMonitor: System idle state changed to ${isIdle}`);
                
                // Adjust all service polling strategies
                this.serviceStates.forEach((state, service) => {
                    this.adjustPollingStrategy(service);
                });

                this.statusManager.emit('idleStateChanged', {
                    idle: isIdle,
                    timeSinceActivity,
                    timestamp: Date.now()
                });
            }
        }, 30000); // Check every 30 seconds
    }

    /**
     * Check if system is currently idle
     * @private
     * @returns {boolean} True if system is idle
     */
    isSystemIdle() {
        const timeSinceActivity = Date.now() - this.lastActivity;
        return timeSinceActivity > this.config.idleTimeout;
    }

    /**
     * Update monitoring metrics
     * @private
     * @param {boolean} success - Whether check was successful
     * @param {number} duration - Check duration in milliseconds
     */
    updateMetrics(success, duration) {
        this.metrics.checksPerformed++;
        
        // Update average check time
        const totalTime = this.metrics.averageCheckTime * (this.metrics.checksPerformed - 1) + duration;
        this.metrics.averageCheckTime = totalTime / this.metrics.checksPerformed;
        
        // Update failure rate
        if (!success) {
            this.metrics.failureRate = (this.metrics.failureRate * (this.metrics.checksPerformed - 1) + 1) / this.metrics.checksPerformed;
        } else {
            this.metrics.failureRate = (this.metrics.failureRate * (this.metrics.checksPerformed - 1)) / this.metrics.checksPerformed;
        }
    }

    /**
     * Update monitored services
     * @param {Array<string>} services - New list of services to monitor
     */
    updateMonitoredServices(services) {
        const currentServices = Array.from(this.monitoringIntervals.keys());
        
        // Stop monitoring services not in new list
        currentServices.forEach(service => {
            if (!services.includes(service)) {
                this.stopServiceMonitoring(service);
            }
        });
        
        // Start monitoring new services
        services.forEach(service => {
            if (!currentServices.includes(service) && this.serviceStates.has(service)) {
                this.startServiceMonitoring(service);
            }
        });
    }

    /**
     * Enable or disable monitoring for a specific service
     * @param {string} service - Service name
     * @param {boolean} enabled - Whether to enable monitoring
     */
    setServiceEnabled(service, enabled) {
        const serviceState = this.serviceStates.get(service);
        if (!serviceState) return;

        serviceState.enabled = enabled;
        
        if (enabled && this.isMonitoring) {
            this.startServiceMonitoring(service);
        } else {
            this.stopServiceMonitoring(service);
        }

        console.log(`BackgroundServiceMonitor: ${service} monitoring ${enabled ? 'enabled' : 'disabled'}`);
    }

    /**
     * Get current monitoring status
     * @returns {Object} Monitoring status information
     */
    getMonitoringStatus() {
        return {
            isMonitoring: this.isMonitoring,
            monitoredServices: Array.from(this.monitoringIntervals.keys()),
            serviceStates: Object.fromEntries(
                Array.from(this.serviceStates.entries()).map(([service, state]) => [
                    service,
                    {
                        status: state.status,
                        pollingStrategy: state.pollingStrategy,
                        currentInterval: state.currentInterval,
                        consecutiveSuccesses: state.consecutiveSuccesses,
                        consecutiveFailures: state.consecutiveFailures,
                        lastCheck: state.lastCheck,
                        enabled: state.enabled
                    }
                ])
            ),
            metrics: { ...this.metrics },
            isIdle: this.isSystemIdle(),
            lastActivity: this.lastActivity
        };
    }

    /**
     * Force immediate check of all monitored services
     * @returns {Promise<Object>} Check results
     */
    async forceImmediateCheck() {
        console.log('BackgroundServiceMonitor: Forcing immediate check of all services');
        
        const results = {};
        const services = Array.from(this.monitoringIntervals.keys());
        
        // Perform checks in parallel
        const checkPromises = services.map(async service => {
            try {
                await this.performServiceCheck(service);
                results[service] = this.statusManager.getStatus(service);
            } catch (error) {
                results[service] = { error: error.message };
            }
        });
        
        await Promise.all(checkPromises);
        
        this.statusManager.emit('immediateCheckComplete', {
            results,
            timestamp: Date.now()
        });
        
        return results;
    }

    /**
     * Cleanup and destroy the monitor
     */
    destroy() {
        console.log('BackgroundServiceMonitor: Destroying monitor');
        
        this.stopMonitoring();
        this.serviceStates.clear();
        this.monitoringIntervals.clear();
        
        // Remove event listeners
        if (this.idleDetectionInterval) {
            clearInterval(this.idleDetectionInterval);
        }
    }
}

// Export for module use
if (typeof module !== 'undefined' && module.exports) {
    module.exports = BackgroundServiceMonitor;
}

// Make available globally
window.BackgroundServiceMonitor = BackgroundServiceMonitor;