/**
 * Enhanced Status Manager - Fast, parallel status checking with intelligent caching
 * Implements non-blocking status monitoring with event-driven updates
 */

class StatusManager {
    constructor(options = {}) {
        // Status cache with timestamp-based expiration
        this.statusCache = new Map();
        
        // Active check intervals
        this.checkIntervals = new Map();
        
        // Event callbacks
        this.callbacks = new Map();
        
        // Configuration with performance-focused defaults
        this.config = {
            internetCheckTimeout: 3000,      // 3 seconds max for internet check
            jellyfinCheckTimeout: 5000,      // 5 seconds max for Jellyfin check
            fastCheckInterval: 10000,        // 10 seconds for fast checks
            slowCheckInterval: 60000,        // 60 seconds for slow checks
            cacheExpiration: 30000,          // 30 seconds cache expiration
            maxRetries: 3,                   // Maximum retry attempts
            retryDelay: 1000,               // Initial retry delay (exponential backoff)
            ...options
        };
        
        // Current status state
        this.currentStatus = {
            internet: { connected: false, lastCheck: 0, checkDuration: 0, method: null },
            jellyfin: { connected: false, lastCheck: 0, checkDuration: 0, serverUrl: null, skipNextCheck: false, confirmedAt: 0 },
            vlc: { available: false, lastCheck: 0, path: null },
            localMedia: { available: false, count: 0, lastScan: 0 }
        };
        
        // Performance tracking
        this.performance = {
            averageCheckTime: 0,
            failedChecks: 0,
            successfulChecks: 0,
            totalChecks: 0
        };
        
        // Background monitoring state
        this.isMonitoring = false;
        this.monitoringWorker = null;
        this.backgroundMonitor = null;
        
        // Connectivity mode tracking
        this._lastConnectivityMode = 'unknown';
        
        console.log('StatusManager: Initialized with config:', this.config);
    }

    /**
     * Initialize the status manager and perform initial status checks
     * @returns {Promise<Object>} Initial status data
     */
    async initialize() {
        console.log('StatusManager: Starting initialization');
        
        try {
            // Load any cached status data
            this._loadCachedStatus();
            
            // Perform initial fast status checks in parallel
            const startTime = Date.now();
            
            // Start all checks in parallel for maximum speed
            const internetPromise = this.checkInternetConnectivity();
            const vlcPromise = this.checkVLCAvailability();
            const localMediaPromise = this.checkLocalMediaAvailability();
            
            // Wait for internet check first (needed for Jellyfin)
            const internetResult = await internetPromise;
            
            // Start Jellyfin check only if internet is available
            let jellyfinPromise = Promise.resolve({ connected: false, error: 'No internet connection' });
            if (internetResult.connected) {
                jellyfinPromise = this.checkJellyfinConnectivity();
            }
            
            // Wait for all remaining checks
            const [jellyfinResult, vlcResult, localMediaResult] = await Promise.all([
                jellyfinPromise,
                vlcPromise,
                localMediaPromise
            ]);
            
            // Update current status
            this.currentStatus.internet = internetResult;
            this.currentStatus.jellyfin = jellyfinResult;
            this.currentStatus.vlc = vlcResult;
            this.currentStatus.localMedia = localMediaResult;
            
            const initializationTime = Date.now() - startTime;
            console.log(`StatusManager: Initialization completed in ${initializationTime}ms`);
            
            // Cache the results
            this._cacheStatus();
            
            // Emit initialization complete event
            this.emit('initialized', this.currentStatus);
            
            return this.currentStatus;
            
        } catch (error) {
            console.error('StatusManager: Initialization failed:', error);
            this.emit('error', { type: 'initialization', error });
            throw error;
        }
    }

    /**
     * Check internet connectivity with multiple fallback methods
     * @returns {Promise<Object>} Internet connectivity status
     */
    async checkInternetConnectivity() {
        const startTime = Date.now();
        console.log('StatusManager: Checking internet connectivity');
        
        // Check cache first
        const cached = this._getCachedStatus('internet');
        if (cached && this._isCacheValid(cached)) {
            console.log('StatusManager: Using cached internet status');
            return cached.data;
        }
        
        const methods = [
            { name: 'fetch', url: 'https://www.google.com/favicon.ico' },
            { name: 'fetch', url: 'https://cloudflare.com/favicon.ico' },
            { name: 'fetch', url: 'https://httpbin.org/status/200' }
        ];
        
        for (const method of methods) {
            try {
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), this.config.internetCheckTimeout);
                
                const response = await fetch(method.url, {
                    method: 'HEAD',
                    mode: 'no-cors',
                    signal: controller.signal,
                    cache: 'no-cache'
                });
                
                clearTimeout(timeoutId);
                
                const checkDuration = Date.now() - startTime;
                const result = {
                    connected: true,
                    lastCheck: Date.now(),
                    checkDuration,
                    method: method.name
                };
                
                console.log(`StatusManager: Internet connectivity confirmed via ${method.name} in ${checkDuration}ms`);
                this._setCachedStatus('internet', result);
                this._updatePerformance(true, checkDuration);
                
                return result;
                
            } catch (error) {
                console.warn(`StatusManager: Internet check failed with ${method.name}:`, error.message);
                continue;
            }
        }
        
        // All methods failed
        const checkDuration = Date.now() - startTime;
        const result = {
            connected: false,
            lastCheck: Date.now(),
            checkDuration,
            method: 'failed',
            error: 'All connectivity checks failed'
        };
        
        console.log(`StatusManager: Internet connectivity failed after ${checkDuration}ms`);
        this._setCachedStatus('internet', result);
        this._updatePerformance(false, checkDuration);
        
        return result;
    }

    /**
     * Check Jellyfin connectivity with timeout handling
     * @returns {Promise<Object>} Jellyfin connectivity status
     */
    async checkJellyfinConnectivity() {
        const startTime = Date.now();
        console.log('StatusManager: Checking Jellyfin connectivity');
        
        // Check if we should skip this check (optimization)
        if (this.currentStatus.jellyfin.skipNextCheck) {
            console.log('StatusManager: Skipping Jellyfin check as requested');
            return {
                ...this.currentStatus.jellyfin,
                lastCheck: Date.now(),
                skipped: true
            };
        }
        
        // Check cache first
        const cached = this._getCachedStatus('jellyfin');
        if (cached && this._isCacheValid(cached)) {
            console.log('StatusManager: Using cached Jellyfin status');
            return cached.data;
        }
        
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), this.config.jellyfinCheckTimeout);
            
            // Use the existing status endpoint with skip_jellyfin=false
            const response = await fetch('/api/status?skip_jellyfin=false', {
                signal: controller.signal,
                cache: 'no-cache'
            });
            
            clearTimeout(timeoutId);
            
            if (!response.ok) {
                throw new Error(`Status API returned ${response.status}`);
            }
            
            const data = await response.json();
            const checkDuration = Date.now() - startTime;
            
            const result = {
                connected: data.services?.jellyfin?.connected || false,
                lastCheck: Date.now(),
                checkDuration,
                serverUrl: data.services?.jellyfin?.server_url || null,
                skipNextCheck: false,
                confirmedAt: data.services?.jellyfin?.connected ? Date.now() : this.currentStatus.jellyfin.confirmedAt
            };
            
            console.log(`StatusManager: Jellyfin connectivity check completed in ${checkDuration}ms, connected: ${result.connected}`);
            this._setCachedStatus('jellyfin', result);
            this._updatePerformance(true, checkDuration);
            
            // If Jellyfin is confirmed working, we can optimize future checks
            if (result.connected) {
                result.skipNextCheck = true;
                console.log('StatusManager: Jellyfin confirmed working, enabling skip optimization');
            }
            
            return result;
            
        } catch (error) {
            const checkDuration = Date.now() - startTime;
            const result = {
                connected: false,
                lastCheck: Date.now(),
                checkDuration,
                serverUrl: null,
                skipNextCheck: false,
                confirmedAt: this.currentStatus.jellyfin.confirmedAt,
                error: error.message
            };
            
            console.log(`StatusManager: Jellyfin connectivity failed after ${checkDuration}ms:`, error.message);
            this._setCachedStatus('jellyfin', result);
            this._updatePerformance(false, checkDuration);
            
            return result;
        }
    }

    /**
     * Check VLC availability
     * @returns {Promise<Object>} VLC availability status
     */
    async checkVLCAvailability() {
        const startTime = Date.now();
        console.log('StatusManager: Checking VLC availability');
        
        // Check cache first
        const cached = this._getCachedStatus('vlc');
        if (cached && this._isCacheValid(cached)) {
            console.log('StatusManager: Using cached VLC status');
            return cached.data;
        }
        
        try {
            const response = await fetch('/api/status', { cache: 'no-cache' });
            
            if (!response.ok) {
                throw new Error(`Status API returned ${response.status}`);
            }
            
            const data = await response.json();
            const checkDuration = Date.now() - startTime;
            
            const result = {
                available: data.services?.vlc?.installed || false,
                lastCheck: Date.now(),
                path: data.services?.vlc?.path || null
            };
            
            console.log(`StatusManager: VLC availability check completed in ${checkDuration}ms, available: ${result.available}`);
            this._setCachedStatus('vlc', result);
            this._updatePerformance(true, checkDuration);
            
            return result;
            
        } catch (error) {
            const checkDuration = Date.now() - startTime;
            const result = {
                available: false,
                lastCheck: Date.now(),
                path: null,
                error: error.message
            };
            
            console.log(`StatusManager: VLC availability failed after ${checkDuration}ms:`, error.message);
            this._setCachedStatus('vlc', result);
            this._updatePerformance(false, checkDuration);
            
            return result;
        }
    }

    /**
     * Check local media availability
     * @returns {Promise<Object>} Local media availability status
     */
    async checkLocalMediaAvailability() {
        const startTime = Date.now();
        console.log('StatusManager: Checking local media availability');
        
        // Check cache first
        const cached = this._getCachedStatus('localMedia');
        if (cached && this._isCacheValid(cached)) {
            console.log('StatusManager: Using cached local media status');
            return cached.data;
        }
        
        try {
            const response = await fetch('/api/media?mode=local', { cache: 'no-cache' });
            
            if (!response.ok) {
                throw new Error(`Media API returned ${response.status}`);
            }
            
            const data = await response.json();
            const checkDuration = Date.now() - startTime;
            
            const result = {
                available: true,
                count: data.count || 0,
                lastScan: Date.now()
            };
            
            console.log(`StatusManager: Local media check completed in ${checkDuration}ms, count: ${result.count}`);
            this._setCachedStatus('localMedia', result);
            this._updatePerformance(true, checkDuration);
            
            return result;
            
        } catch (error) {
            const checkDuration = Date.now() - startTime;
            const result = {
                available: false,
                count: 0,
                lastScan: Date.now(),
                error: error.message
            };
            
            console.log(`StatusManager: Local media check failed after ${checkDuration}ms:`, error.message);
            this._setCachedStatus('localMedia', result);
            this._updatePerformance(false, checkDuration);
            
            return result;
        }
    }

    /**
     * Get current status for a specific service
     * @param {string} service - Service name (internet, jellyfin, vlc, localMedia)
     * @returns {Object} Service status
     */
    getStatus(service) {
        if (service) {
            return this.currentStatus[service] || null;
        }
        return { ...this.currentStatus };
    }

    /**
     * Set status for a specific service
     * @param {string} service - Service name
     * @param {Object} status - Status data
     */
    setStatus(service, status) {
        if (this.currentStatus[service]) {
            const oldStatus = { ...this.currentStatus[service] };
            this.currentStatus[service] = { ...this.currentStatus[service], ...status };
            
            // Detect and emit status change events
            this._detectAndEmitStatusChanges(service, oldStatus, this.currentStatus[service]);
            
            // Cache the updated status
            this._setCachedStatus(service, this.currentStatus[service]);
        }
    }

    /**
     * Clear cache for specific service or all services
     * @param {string|null} service - Service name or null for all
     */
    clearCache(service = null) {
        if (service) {
            this.statusCache.delete(service);
            console.log(`StatusManager: Cleared cache for ${service}`);
        } else {
            this.statusCache.clear();
            console.log('StatusManager: Cleared all cache');
        }
    }

    // Event handling methods

    /**
     * Register event callback
     * @param {string} event - Event name
     * @param {Function} callback - Callback function
     * @returns {Function} Unsubscribe function
     */
    on(event, callback) {
        if (!this.callbacks.has(event)) {
            this.callbacks.set(event, []);
        }
        this.callbacks.get(event).push(callback);
        
        // Return unsubscribe function
        return () => {
            const callbacks = this.callbacks.get(event);
            if (callbacks) {
                const index = callbacks.indexOf(callback);
                if (index > -1) {
                    callbacks.splice(index, 1);
                }
            }
        };
    }

    /**
     * Remove event callback
     * @param {string} event - Event name
     * @param {Function} callback - Callback function to remove
     */
    off(event, callback) {
        const callbacks = this.callbacks.get(event);
        if (callbacks) {
            const index = callbacks.indexOf(callback);
            if (index > -1) {
                callbacks.splice(index, 1);
            }
        }
    }

    /**
     * Remove all callbacks for an event
     * @param {string} event - Event name
     */
    removeAllListeners(event) {
        if (event) {
            this.callbacks.delete(event);
        } else {
            this.callbacks.clear();
        }
    }

    /**
     * Emit event to registered callbacks
     * @param {string} event - Event name
     * @param {*} data - Event data
     */
    emit(event, data) {
        const callbacks = this.callbacks.get(event);
        if (callbacks && callbacks.length > 0) {
            console.log(`StatusManager: Emitting ${event} event to ${callbacks.length} listeners`);
            callbacks.forEach(callback => {
                try {
                    callback(data);
                } catch (error) {
                    console.error(`StatusManager: Error in ${event} callback:`, error);
                }
            });
        }
    }

    /**
     * Get user-friendly error message for service unavailability
     * @param {string} service - Service name
     * @param {Object} error - Error information
     * @returns {Object} User-friendly error information
     */
    getUserFriendlyError(service, error) {
        const errorMessages = {
            internet: {
                title: 'Internet Connection Unavailable',
                message: 'Unable to connect to the internet. You can still access your local media library.',
                suggestions: [
                    'Check your network connection',
                    'Try refreshing the page',
                    'Continue using local media only'
                ],
                icon: '🌐',
                severity: 'warning',
                recoverable: true
            },
            jellyfin: {
                title: 'Jellyfin Server Unavailable',
                message: 'Cannot connect to your Jellyfin media server. Remote media is temporarily unavailable.',
                suggestions: [
                    'Check if Jellyfin server is running',
                    'Verify server URL in settings',
                    'Continue with local media only'
                ],
                icon: '📺',
                severity: 'warning',
                recoverable: true
            },
            vlc: {
                title: 'VLC Player Not Found',
                message: 'VLC media player is not installed or not found. Local playback may be limited.',
                suggestions: [
                    'Install VLC media player',
                    'Check VLC installation path',
                    'Use browser-based playback instead'
                ],
                icon: '🎬',
                severity: 'info',
                recoverable: true
            },
            localMedia: {
                title: 'Local Media Unavailable',
                message: 'Unable to access local media files. This may indicate a storage issue.',
                suggestions: [
                    'Check media directory permissions',
                    'Verify storage is accessible',
                    'Try refreshing the library'
                ],
                icon: '💾',
                severity: 'error',
                recoverable: false
            }
        };

        const baseError = errorMessages[service] || {
            title: 'Service Unavailable',
            message: `${service} is currently unavailable.`,
            suggestions: ['Try refreshing the page', 'Check your connection'],
            icon: '⚠️',
            severity: 'warning',
            recoverable: true
        };

        return {
            ...baseError,
            service,
            timestamp: Date.now(),
            technicalDetails: error?.message || 'Unknown error',
            errorCode: error?.code || 'UNKNOWN_ERROR'
        };
    }

    /**
     * Display user-friendly error notification
     * @param {string} service - Service name
     * @param {Object} error - Error information
     */
    displayServiceError(service, error) {
        const errorInfo = this.getUserFriendlyError(service, error);
        
        // Emit error event for UI components to handle
        this.emit('serviceError', errorInfo);
        
        // Also emit specific service error event
        this.emit(`${service}:error`, errorInfo);
        
        console.log(`StatusManager: Displaying error for ${service}:`, errorInfo);
    }

    /**
     * Get current connectivity mode with user-friendly description
     * @returns {Object} Connectivity mode information
     */
    getConnectivityModeInfo() {
        const internetConnected = this.currentStatus.internet.connected;
        const jellyfinConnected = this.currentStatus.jellyfin.connected;
        const vlcAvailable = this.currentStatus.vlc.available;
        const localMediaAvailable = this.currentStatus.localMedia.available;

        let mode = 'offline';
        let description = '';
        let capabilities = [];
        let limitations = [];

        if (internetConnected && jellyfinConnected) {
            mode = 'online';
            description = 'All services are available';
            capabilities = ['Local media playback', 'Remote media streaming', 'Full functionality'];
        } else if (internetConnected && !jellyfinConnected) {
            mode = 'degraded';
            description = 'Internet available but Jellyfin server is unreachable';
            capabilities = ['Local media playback', 'Internet-based features'];
            limitations = ['Remote media streaming unavailable'];
        } else if (!internetConnected) {
            mode = 'offline';
            description = 'No internet connection - local-only mode';
            capabilities = localMediaAvailable ? ['Local media playback'] : [];
            limitations = ['Remote media streaming unavailable', 'Online features disabled'];
        }

        return {
            mode,
            description,
            capabilities,
            limitations,
            services: {
                internet: internetConnected,
                jellyfin: jellyfinConnected,
                vlc: vlcAvailable,
                localMedia: localMediaAvailable
            },
            timestamp: Date.now()
        };
    }

    /**
     * Check for status changes and emit appropriate events
     * @param {string} service - Service name
     * @param {Object} oldStatus - Previous status
     * @param {Object} newStatus - New status
     * @private
     */
    _detectAndEmitStatusChanges(service, oldStatus, newStatus) {
        // Check for connectivity changes
        if (service === 'internet' || service === 'jellyfin') {
            const wasConnected = oldStatus.connected;
            const isConnected = newStatus.connected;
            
            if (wasConnected !== isConnected) {
                const changeType = isConnected ? 'connected' : 'disconnected';
                console.log(`StatusManager: ${service} ${changeType}`);
                
                this.emit(`${service}:${changeType}`, { service, oldStatus, newStatus });
                this.emit('connectivityChange', { service, connected: isConnected, oldStatus, newStatus });
                
                // Emit overall connectivity change
                this._checkOverallConnectivity();
            }
        }
        
        // Check for availability changes
        if (service === 'vlc' || service === 'localMedia') {
            const wasAvailable = oldStatus.available;
            const isAvailable = newStatus.available;
            
            if (wasAvailable !== isAvailable) {
                const changeType = isAvailable ? 'available' : 'unavailable';
                console.log(`StatusManager: ${service} ${changeType}`);
                
                this.emit(`${service}:${changeType}`, { service, oldStatus, newStatus });
                this.emit('availabilityChange', { service, available: isAvailable, oldStatus, newStatus });
            }
        }
        
        // Check for local media count changes
        if (service === 'localMedia' && oldStatus.count !== newStatus.count) {
            console.log(`StatusManager: Local media count changed from ${oldStatus.count} to ${newStatus.count}`);
            this.emit('localMedia:countChange', { 
                service, 
                oldCount: oldStatus.count, 
                newCount: newStatus.count, 
                oldStatus, 
                newStatus 
            });
        }
        
        // Always emit the general status change event
        this.emit('statusChange', { service, oldStatus, newStatus });
    }

    /**
     * Check overall connectivity status and emit events
     * @private
     */
    _checkOverallConnectivity() {
        const internetConnected = this.currentStatus.internet.connected;
        const jellyfinConnected = this.currentStatus.jellyfin.connected;
        
        let connectivityMode = 'offline';
        if (internetConnected && jellyfinConnected) {
            connectivityMode = 'online';
        } else if (internetConnected && !jellyfinConnected) {
            connectivityMode = 'degraded';
        }
        
        // Check if mode changed
        const previousMode = this._lastConnectivityMode || 'unknown';
        if (previousMode !== connectivityMode) {
            console.log(`StatusManager: Connectivity mode changed from ${previousMode} to ${connectivityMode}`);
            this.emit('connectivityModeChange', { 
                oldMode: previousMode, 
                newMode: connectivityMode,
                internet: internetConnected,
                jellyfin: jellyfinConnected
            });
            this._lastConnectivityMode = connectivityMode;
        }
    }

    /**
     * Start intelligent background monitoring with adaptive polling
     * @param {Object} options - Monitoring options
     */
    startBackgroundMonitoring(options = {}) {
        if (this.isMonitoring) {
            console.log('StatusManager: Background monitoring already active');
            return;
        }
        
        const {
            services = ['internet', 'jellyfin'],
            enableAdaptivePolling = true,
            ...monitorOptions
        } = options;
        
        console.log('StatusManager: Starting intelligent background monitoring for services:', services);
        
        // Initialize background monitor if not already created
        if (!this.backgroundMonitor) {
            this.backgroundMonitor = new BackgroundServiceMonitor(this, monitorOptions);
        }
        
        // Start background monitoring
        this.backgroundMonitor.startMonitoring(services, options);
        this.isMonitoring = true;
        
        // Set up event listeners for background monitor
        this._setupBackgroundMonitorListeners();
        
        this.emit('backgroundMonitoringStarted', {
            services,
            enableAdaptivePolling,
            timestamp: Date.now()
        });
    }

    /**
     * Stop background monitoring
     * @param {string|null} service - Specific service to stop, or null for all
     */
    stopBackgroundMonitoring(service = null) {
        if (!this.isMonitoring || !this.backgroundMonitor) {
            console.log('StatusManager: Background monitoring not active');
            return;
        }
        
        this.backgroundMonitor.stopMonitoring(service);
        
        if (!service) {
            this.isMonitoring = false;
            this.emit('backgroundMonitoringStopped', { timestamp: Date.now() });
        }
    }

    /**
     * Set up event listeners for background monitor
     * @private
     */
    _setupBackgroundMonitorListeners() {
        if (!this.backgroundMonitor) return;
        
        // Listen for service state transitions
        this.on('serviceStateTransition', (data) => {
            console.log(`StatusManager: Service ${data.service} transitioned to ${data.newState}`);
            this._handleServiceStateTransition(data);
        });
        
        // Listen for polling strategy changes
        this.on('pollingStrategyChanged', (data) => {
            console.log(`StatusManager: Polling strategy for ${data.service} changed to ${data.newStrategy}`);
        });
        
        // Listen for service recovery
        this.on('serviceRecovered', (data) => {
            console.log(`StatusManager: Service ${data.service} recovered`);
            this._handleServiceRecovery(data);
        });
        
        // Listen for service failures
        this.on('serviceFailed', (data) => {
            console.log(`StatusManager: Service ${data.service} failed`);
            this._handleServiceFailure(data);
        });
    }

    /**
     * Handle service state transitions
     * @private
     * @param {Object} data - Transition data
     */
    _handleServiceStateTransition(data) {
        const { service, newState, oldState } = data;
        
        // Update connectivity mode if needed
        if (service === 'internet' || service === 'jellyfin') {
            this._checkOverallConnectivity();
        }
        
        // Emit user-friendly events
        if (newState === 'connected' && oldState === 'disconnected') {
            this.emit(`${service}:connected`, data);
        } else if (newState === 'disconnected' && oldState === 'connected') {
            this.emit(`${service}:disconnected`, data);
        }
    }

    /**
     * Handle service recovery
     * @private
     * @param {Object} data - Recovery data
     */
    _handleServiceRecovery(data) {
        const { service } = data;
        
        // Service-specific recovery actions
        if (service === 'jellyfin') {
            // Trigger media loading refresh
            this.emit('jellyfinRecovered', data);
        }
        
        // Clear any cached errors for this service
        this.clearCache(service);
    }

    /**
     * Handle service failure
     * @private
     * @param {Object} data - Failure data
     */
    _handleServiceFailure(data) {
        const { service } = data;
        
        // Display user-friendly error
        this.displayServiceError(service, data.status?.error);
        
        // Service-specific failure actions
        if (service === 'internet') {
            // Switch to offline mode
            this.emit('offlineModeActivated', data);
        } else if (service === 'jellyfin') {
            // Switch to local-only mode
            this.emit('localOnlyModeActivated', data);
        }
    }

    /**
     * Start periodic status monitoring with event emission (legacy method)
     * @param {Object} options - Monitoring options
     * @deprecated Use startBackgroundMonitoring instead
     */
    startPeriodicMonitoring(options = {}) {
        console.warn('StatusManager: startPeriodicMonitoring is deprecated, use startBackgroundMonitoring instead');
        return this.startBackgroundMonitoring(options);
    }

    /**
     * Legacy periodic monitoring implementation (kept for compatibility)
     * @private
     */
    _startLegacyPeriodicMonitoring(options = {}) {
        if (this.isMonitoring) {
            console.log('StatusManager: Periodic monitoring already active');
            return;
        }
        
        const {
            interval = this.config.fastCheckInterval,
            services = ['internet', 'jellyfin', 'vlc', 'localMedia']
        } = options;
        
        console.log(`StatusManager: Starting periodic monitoring every ${interval}ms for services:`, services);
        this.isMonitoring = true;
        
        const monitoringInterval = setInterval(async () => {
            try {
                console.log('StatusManager: Performing periodic status check');
                
                // Check each service and emit events for changes
                for (const service of services) {
                    const oldStatus = { ...this.currentStatus[service] };
                    let newStatus;
                    
                    switch (service) {
                        case 'internet':
                            newStatus = await this.checkInternetConnectivity();
                            break;
                        case 'jellyfin':
                            // Only check Jellyfin if internet is available
                            if (this.currentStatus.internet.connected) {
                                newStatus = await this.checkJellyfinConnectivity();
                            } else {
                                newStatus = { ...oldStatus, connected: false, lastCheck: Date.now() };
                            }
                            break;
                        case 'vlc':
                            newStatus = await this.checkVLCAvailability();
                            break;
                        case 'localMedia':
                            newStatus = await this.checkLocalMediaAvailability();
                            break;
                        default:
                            continue;
                    }
                    
                    // Update status and detect changes
                    this.currentStatus[service] = newStatus;
                    this._detectAndEmitStatusChanges(service, oldStatus, newStatus);
                }
                
                // Emit periodic check complete event
                this.emit('periodicCheckComplete', { 
                    timestamp: Date.now(), 
                    status: this.currentStatus 
                });
                
            } catch (error) {
                console.error('StatusManager: Error during periodic monitoring:', error);
                this.emit('monitoringError', { error, timestamp: Date.now() });
            }
        }, interval);
        
        // Store interval ID for cleanup
        this.checkIntervals.set('periodic', monitoringInterval);
        
        this.emit('monitoringStarted', { interval, services });
    }

    /**
     * Stop periodic status monitoring
     */
    stopPeriodicMonitoring() {
        if (!this.isMonitoring) {
            console.log('StatusManager: Periodic monitoring not active');
            return;
        }
        
        const intervalId = this.checkIntervals.get('periodic');
        if (intervalId) {
            clearInterval(intervalId);
            this.checkIntervals.delete('periodic');
        }
        
        this.isMonitoring = false;
        console.log('StatusManager: Stopped periodic monitoring');
        
        this.emit('monitoringStopped', { timestamp: Date.now() });
    }

    // Adaptive polling strategies

    /**
     * Start adaptive background polling with frequency adjustment
     * @param {Object} options - Polling options
     */
    startAdaptivePolling(options = {}) {
        if (this.isMonitoring) {
            console.log('StatusManager: Adaptive polling already active');
            return;
        }
        
        const {
            initialInterval = this.config.fastCheckInterval,
            maxInterval = this.config.slowCheckInterval,
            minInterval = 5000, // 5 seconds minimum
            backoffMultiplier = 1.5,
            services = ['internet', 'jellyfin']
        } = options;
        
        console.log('StatusManager: Starting adaptive polling with options:', { initialInterval, maxInterval, minInterval, backoffMultiplier, services });
        
        this.isMonitoring = true;
        this._adaptivePollingState = {
            currentInterval: initialInterval,
            maxInterval,
            minInterval,
            backoffMultiplier,
            services,
            consecutiveFailures: new Map(),
            lastSuccessTime: new Map(),
            pollingStrategy: new Map()
        };
        
        // Initialize polling strategies for each service
        services.forEach(service => {
            this._adaptivePollingState.consecutiveFailures.set(service, 0);
            this._adaptivePollingState.lastSuccessTime.set(service, Date.now());
            this._adaptivePollingState.pollingStrategy.set(service, 'normal');
        });
        
        this._scheduleNextAdaptiveCheck();
        this.emit('adaptivePollingStarted', this._adaptivePollingState);
    }

    /**
     * Stop adaptive polling
     */
    stopAdaptivePolling() {
        if (!this.isMonitoring) {
            console.log('StatusManager: Adaptive polling not active');
            return;
        }
        
        // Clear any scheduled checks
        this.checkIntervals.forEach((intervalId, key) => {
            if (key.startsWith('adaptive_')) {
                clearTimeout(intervalId);
                this.checkIntervals.delete(key);
            }
        });
        
        this.isMonitoring = false;
        this._adaptivePollingState = null;
        
        console.log('StatusManager: Stopped adaptive polling');
        this.emit('adaptivePollingStopped', { timestamp: Date.now() });
    }

    /**
     * Schedule the next adaptive check based on current connectivity state
     * @private
     */
    _scheduleNextAdaptiveCheck() {
        if (!this.isMonitoring || !this._adaptivePollingState) {
            return;
        }
        
        const state = this._adaptivePollingState;
        const nextInterval = this._calculateNextInterval();
        
        console.log(`StatusManager: Scheduling next adaptive check in ${nextInterval}ms`);
        
        const timeoutId = setTimeout(async () => {
            await this._performAdaptiveCheck();
            this._scheduleNextAdaptiveCheck();
        }, nextInterval);
        
        this.checkIntervals.set('adaptive_main', timeoutId);
    }

    /**
     * Calculate the next polling interval based on connectivity state
     * @private
     * @returns {number} Next interval in milliseconds
     */
    _calculateNextInterval() {
        const state = this._adaptivePollingState;
        const internetConnected = this.currentStatus.internet.connected;
        const jellyfinConnected = this.currentStatus.jellyfin.connected;
        
        // If both services are working well, use slower polling
        if (internetConnected && jellyfinConnected) {
            // Check if Jellyfin was recently confirmed - if so, enable skip optimization
            const jellyfinConfirmedRecently = (Date.now() - this.currentStatus.jellyfin.confirmedAt) < 300000; // 5 minutes
            if (jellyfinConfirmedRecently) {
                this.currentStatus.jellyfin.skipNextCheck = true;
                return state.maxInterval; // Use slowest interval when confirmed working
            }
            return Math.min(state.currentInterval * 1.2, state.maxInterval);
        }
        
        // If there are connectivity issues, use faster polling with exponential backoff
        const maxFailures = Math.max(
            state.consecutiveFailures.get('internet') || 0,
            state.consecutiveFailures.get('jellyfin') || 0
        );
        
        if (maxFailures > 0) {
            // Exponential backoff for failed services
            const backoffInterval = state.minInterval * Math.pow(state.backoffMultiplier, Math.min(maxFailures, 5));
            return Math.min(backoffInterval, state.maxInterval);
        }
        
        return state.currentInterval;
    }

    /**
     * Perform adaptive status check with intelligent service selection
     * @private
     */
    async _performAdaptiveCheck() {
        if (!this._adaptivePollingState) {
            return;
        }
        
        const state = this._adaptivePollingState;
        console.log('StatusManager: Performing adaptive status check');
        
        try {
            // Always check internet first as it's required for other services
            await this._adaptiveCheckService('internet');
            
            // Only check Jellyfin if internet is available and not skipped
            if (this.currentStatus.internet.connected) {
                await this._adaptiveCheckService('jellyfin');
            } else {
                // Mark Jellyfin as disconnected if no internet
                const oldStatus = { ...this.currentStatus.jellyfin };
                this.currentStatus.jellyfin.connected = false;
                this.currentStatus.jellyfin.lastCheck = Date.now();
                this._detectAndEmitStatusChanges('jellyfin', oldStatus, this.currentStatus.jellyfin);
            }
            
            // Emit adaptive check complete event
            this.emit('adaptiveCheckComplete', {
                timestamp: Date.now(),
                status: this.currentStatus,
                nextInterval: this._calculateNextInterval()
            });
            
        } catch (error) {
            console.error('StatusManager: Error during adaptive check:', error);
            this.emit('adaptiveCheckError', { error, timestamp: Date.now() });
        }
    }

    /**
     * Perform adaptive check for a specific service
     * @private
     * @param {string} service - Service to check
     */
    async _adaptiveCheckService(service) {
        const state = this._adaptivePollingState;
        const oldStatus = { ...this.currentStatus[service] };
        
        try {
            let newStatus;
            
            switch (service) {
                case 'internet':
                    newStatus = await this.checkInternetConnectivity();
                    break;
                case 'jellyfin':
                    newStatus = await this.checkJellyfinConnectivity();
                    break;
                default:
                    return;
            }
            
            // Update status
            this.currentStatus[service] = newStatus;
            
            // Check for success/failure
            const isSuccess = (service === 'internet' || service === 'jellyfin') ? 
                newStatus.connected : newStatus.available;
            
            if (isSuccess) {
                // Reset failure count on success
                state.consecutiveFailures.set(service, 0);
                state.lastSuccessTime.set(service, Date.now());
                state.pollingStrategy.set(service, 'normal');
                
                console.log(`StatusManager: ${service} check succeeded, resetting failure count`);
            } else {
                // Increment failure count
                const failures = state.consecutiveFailures.get(service) + 1;
                state.consecutiveFailures.set(service, failures);
                state.pollingStrategy.set(service, 'backoff');
                
                console.log(`StatusManager: ${service} check failed, failure count: ${failures}`);
            }
            
            // Detect and emit changes
            this._detectAndEmitStatusChanges(service, oldStatus, newStatus);
            
        } catch (error) {
            // Handle check error
            const failures = state.consecutiveFailures.get(service) + 1;
            state.consecutiveFailures.set(service, failures);
            state.pollingStrategy.set(service, 'backoff');
            
            console.error(`StatusManager: ${service} check error (failure count: ${failures}):`, error);
            
            this.emit('serviceCheckError', { service, error, failures, timestamp: Date.now() });
        }
    }

    /**
     * Adjust polling frequency for a specific service
     * @param {string} service - Service name
     * @param {string} strategy - Polling strategy ('fast', 'normal', 'slow', 'backoff')
     */
    adjustPollingFrequency(service, strategy) {
        if (!this._adaptivePollingState) {
            console.warn('StatusManager: Cannot adjust polling frequency - adaptive polling not active');
            return;
        }
        
        this._adaptivePollingState.pollingStrategy.set(service, strategy);
        console.log(`StatusManager: Adjusted polling strategy for ${service} to ${strategy}`);
        
        this.emit('pollingFrequencyAdjusted', { service, strategy, timestamp: Date.now() });
    }

    /**
     * Enable jellyfin_skip optimization for confirmed connections
     * @param {boolean} enable - Whether to enable skip optimization
     */
    enableJellyfinSkipOptimization(enable = true) {
        if (enable && this.currentStatus.jellyfin.connected) {
            this.currentStatus.jellyfin.skipNextCheck = true;
            this.currentStatus.jellyfin.confirmedAt = Date.now();
            
            console.log('StatusManager: Enabled Jellyfin skip optimization');
            this.emit('jellyfinSkipEnabled', { timestamp: Date.now() });
        } else {
            this.currentStatus.jellyfin.skipNextCheck = false;
            
            console.log('StatusManager: Disabled Jellyfin skip optimization');
            this.emit('jellyfinSkipDisabled', { timestamp: Date.now() });
        }
    }

    /**
     * Force a full status refresh (disables skip optimizations temporarily)
     * @returns {Promise<Object>} Updated status
     */
    async forceFullRefresh() {
        console.log('StatusManager: Forcing full status refresh');
        
        // Temporarily disable skip optimizations
        const originalSkipSetting = this.currentStatus.jellyfin.skipNextCheck;
        this.currentStatus.jellyfin.skipNextCheck = false;
        
        try {
            // Clear cache to force fresh checks
            this.clearCache();
            
            // Perform full initialization
            const status = await this.initialize();
            
            this.emit('fullRefreshComplete', { status, timestamp: Date.now() });
            return status;
            
        } finally {
            // Restore skip setting if it was enabled and Jellyfin is still connected
            if (originalSkipSetting && this.currentStatus.jellyfin.connected) {
                this.currentStatus.jellyfin.skipNextCheck = true;
            }
        }
    }

    /**
     * Get current adaptive polling state
     * @returns {Object|null} Adaptive polling state or null if not active
     */
    getAdaptivePollingState() {
        if (this.backgroundMonitor) {
            return this.backgroundMonitor.getMonitoringStatus();
        }
        
        if (!this._adaptivePollingState) {
            return null;
        }
        
        return {
            isActive: this.isMonitoring,
            currentInterval: this._adaptivePollingState.currentInterval,
            nextInterval: this._calculateNextInterval(),
            services: Array.from(this._adaptivePollingState.services),
            consecutiveFailures: Object.fromEntries(this._adaptivePollingState.consecutiveFailures),
            pollingStrategies: Object.fromEntries(this._adaptivePollingState.pollingStrategy),
            lastSuccessTimes: Object.fromEntries(this._adaptivePollingState.lastSuccessTime)
        };
    }

    /**
     * Adjust polling frequency for a specific service
     * @param {string} service - Service name
     * @param {string} strategy - Polling strategy ('fast', 'normal', 'slow')
     */
    adjustPollingFrequency(service, strategy) {
        if (this.backgroundMonitor) {
            // Map strategy to background monitor method
            const strategyMap = {
                'fast': 'fast',
                'normal': 'normal', 
                'slow': 'slow'
            };
            
            const mappedStrategy = strategyMap[strategy] || 'normal';
            console.log(`StatusManager: Adjusting polling frequency for ${service} to ${mappedStrategy}`);
            
            // The background monitor handles this internally through its adaptive logic
            this.emit('pollingFrequencyAdjustmentRequested', {
                service,
                strategy: mappedStrategy,
                timestamp: Date.now()
            });
            
            return;
        }
        
        // Legacy adaptive polling adjustment
        if (!this._adaptivePollingState) {
            console.warn('StatusManager: Cannot adjust polling frequency - adaptive polling not active');
            return;
        }
        
        this._adaptivePollingState.pollingStrategy.set(service, strategy);
        console.log(`StatusManager: Adjusted polling strategy for ${service} to ${strategy}`);
        
        this.emit('pollingFrequencyAdjusted', { service, strategy, timestamp: Date.now() });
    }

    /**
     * Enable bandwidth-conscious monitoring
     * @param {boolean} enabled - Whether to enable bandwidth-conscious mode
     */
    enableBandwidthConsciousMode(enabled = true) {
        console.log(`StatusManager: ${enabled ? 'Enabling' : 'Disabling'} bandwidth-conscious monitoring`);
        
        if (this.backgroundMonitor) {
            // Adjust all services to slower polling when bandwidth-conscious
            const services = ['internet', 'jellyfin', 'vlc', 'localMedia'];
            services.forEach(service => {
                if (enabled) {
                    this.backgroundMonitor.setServiceEnabled(service, service === 'internet' || service === 'jellyfin');
                } else {
                    this.backgroundMonitor.setServiceEnabled(service, true);
                }
            });
        }
        
        this.emit('bandwidthConsciousModeChanged', {
            enabled,
            timestamp: Date.now()
        });
    }

    /**
     * Set polling strategy for idle periods
     * @param {number} idleThreshold - Time in ms before considering system idle
     * @param {number} idleInterval - Polling interval during idle periods
     */
    setIdlePollingStrategy(idleThreshold = 600000, idleInterval = 300000) {
        console.log(`StatusManager: Setting idle polling strategy - threshold: ${idleThreshold}ms, interval: ${idleInterval}ms`);
        
        if (this.backgroundMonitor) {
            this.backgroundMonitor.config.idleTimeout = idleThreshold;
            this.backgroundMonitor.config.idleInterval = idleInterval;
        }
        
        this.emit('idlePollingStrategySet', {
            idleThreshold,
            idleInterval,
            timestamp: Date.now()
        });
    }

    /**
     * Force immediate status refresh for all services
     * @returns {Promise<Object>} Updated status
     */
    async forceImmediateRefresh() {
        console.log('StatusManager: Forcing immediate status refresh');
        
        if (this.backgroundMonitor) {
            return await this.backgroundMonitor.forceImmediateCheck();
        }
        
        // Fallback to legacy force refresh
        return await this.forceFullRefresh();
    }

    // Private helper methods

    /**
     * Get cached status for a service
     * @private
     * @param {string} service - Service name
     * @returns {Object|null} Cached status or null
     */
    _getCachedStatus(service) {
        return this.statusCache.get(service) || null;
    }

    /**
     * Set cached status for a service
     * @private
     * @param {string} service - Service name
     * @param {Object} status - Status data
     */
    _setCachedStatus(service, status) {
        this.statusCache.set(service, {
            data: status,
            timestamp: Date.now()
        });
    }

    /**
     * Check if cached status is still valid
     * @private
     * @param {Object} cached - Cached status object
     * @returns {boolean} True if cache is valid
     */
    _isCacheValid(cached) {
        const age = Date.now() - cached.timestamp;
        return age < this.config.cacheExpiration;
    }

    /**
     * Update performance metrics
     * @private
     * @param {boolean} success - Whether the check was successful
     * @param {number} duration - Check duration in milliseconds
     */
    _updatePerformance(success, duration) {
        this.performance.totalChecks++;
        
        if (success) {
            this.performance.successfulChecks++;
        } else {
            this.performance.failedChecks++;
        }
        
        // Update average check time
        const totalTime = this.performance.averageCheckTime * (this.performance.totalChecks - 1) + duration;
        this.performance.averageCheckTime = totalTime / this.performance.totalChecks;
    }

    /**
     * Load cached status from localStorage
     * @private
     */
    _loadCachedStatus() {
        try {
            const cached = localStorage.getItem('statusManager_cache');
            if (cached) {
                const data = JSON.parse(cached);
                const age = Date.now() - (data.timestamp || 0);
                
                // Only use cache if less than cache expiration time
                if (age < this.config.cacheExpiration) {
                    this.statusCache = new Map(data.cache || []);
                    console.log('StatusManager: Loaded cached status from localStorage');
                }
            }
        } catch (error) {
            console.warn('StatusManager: Error loading cached status:', error);
        }
    }

    /**
     * Cache current status to localStorage
     * @private
     */
    _cacheStatus() {
        try {
            const cacheData = {
                cache: Array.from(this.statusCache.entries()),
                timestamp: Date.now()
            };
            localStorage.setItem('statusManager_cache', JSON.stringify(cacheData));
        } catch (error) {
            console.warn('StatusManager: Error caching status:', error);
        }
    }
}

// Export for module use
if (typeof module !== 'undefined' && module.exports) {
    module.exports = StatusManager;
}

// Make available globally
window.StatusManager = StatusManager;