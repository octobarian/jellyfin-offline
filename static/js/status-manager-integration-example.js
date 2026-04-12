/**
 * StatusManager Integration Example
 * Shows how to integrate the new StatusManager with existing code
 */

class StatusManagerIntegration {
    constructor() {
        this.statusManager = null;
        this.isInitialized = false;
    }

    /**
     * Initialize the status manager and set up event listeners
     */
    async initialize() {
        console.log('StatusManagerIntegration: Initializing...');
        
        try {
            // Create StatusManager with optimized settings
            this.statusManager = new StatusManager({
                internetCheckTimeout: 3000,
                jellyfinCheckTimeout: 5000,
                fastCheckInterval: 15000,  // 15 seconds for fast checks
                slowCheckInterval: 60000,  // 60 seconds for slow checks
                cacheExpiration: 30000     // 30 seconds cache
            });
            
            // Set up event listeners
            this._setupEventListeners();
            
            // Initialize status manager
            const initialStatus = await this.statusManager.initialize();
            console.log('StatusManagerIntegration: Initial status:', initialStatus);
            
            // Update UI with initial status
            this._updateStatusDisplay(initialStatus);
            
            // Start adaptive polling
            this.statusManager.startAdaptivePolling({
                initialInterval: 15000,
                services: ['internet', 'jellyfin']
            });
            
            this.isInitialized = true;
            console.log('StatusManagerIntegration: Initialization complete');
            
            return initialStatus;
            
        } catch (error) {
            console.error('StatusManagerIntegration: Initialization failed:', error);
            throw error;
        }
    }

    /**
     * Set up event listeners for status changes
     * @private
     */
    _setupEventListeners() {
        // Listen for connectivity changes
        this.statusManager.on('connectivityChange', (data) => {
            console.log(`StatusManagerIntegration: ${data.service} connectivity changed to ${data.connected}`);
            this._handleConnectivityChange(data);
        });
        
        // Listen for connectivity mode changes
        this.statusManager.on('connectivityModeChange', (data) => {
            console.log(`StatusManagerIntegration: Connectivity mode changed from ${data.oldMode} to ${data.newMode}`);
            this._handleConnectivityModeChange(data);
        });
        
        // Listen for Jellyfin specific events
        this.statusManager.on('jellyfin:connected', (data) => {
            console.log('StatusManagerIntegration: Jellyfin connected');
            this._handleJellyfinConnected(data);
        });
        
        this.statusManager.on('jellyfin:disconnected', (data) => {
            console.log('StatusManagerIntegration: Jellyfin disconnected');
            this._handleJellyfinDisconnected(data);
        });
        
        // Listen for local media changes
        this.statusManager.on('localMedia:countChange', (data) => {
            console.log(`StatusManagerIntegration: Local media count changed from ${data.oldCount} to ${data.newCount}`);
            this._handleLocalMediaCountChange(data);
        });
        
        // Listen for adaptive polling events
        this.statusManager.on('adaptiveCheckComplete', (data) => {
            console.log('StatusManagerIntegration: Adaptive check completed');
            this._updateStatusDisplay(data.status);
        });
        
        // Listen for errors
        this.statusManager.on('serviceCheckError', (data) => {
            console.warn(`StatusManagerIntegration: ${data.service} check error:`, data.error);
            this._handleServiceError(data);
        });
    }

    /**
     * Handle connectivity changes
     * @private
     */
    _handleConnectivityChange(data) {
        const { service, connected } = data;
        
        // Update status indicators
        const statusElement = document.getElementById(`${service}Status`);
        const textElement = document.getElementById(`${service}Text`);
        
        if (statusElement && textElement) {
            statusElement.className = `status-indicator ${connected ? 'status-online' : 'status-offline'}`;
            
            let statusText = '';
            switch (service) {
                case 'internet':
                    statusText = `Internet: ${connected ? 'Connected' : 'Offline'}`;
                    break;
                case 'jellyfin':
                    statusText = `Jellyfin: ${connected ? 'Connected' : 'Offline'}`;
                    break;
            }
            textElement.textContent = statusText;
        }
    }

    /**
     * Handle connectivity mode changes
     * @private
     */
    _handleConnectivityModeChange(data) {
        const { newMode, internet, jellyfin } = data;
        
        // Update system status container
        const systemStatus = document.getElementById('systemStatus');
        if (systemStatus) {
            systemStatus.className = `system-status ${newMode}`;
        }
        
        // Show/hide offline mode indicator
        const offlineMode = document.getElementById('offlineMode');
        if (offlineMode) {
            offlineMode.style.display = newMode === 'offline' ? 'block' : 'none';
        }
        
        // Update services ready indicator
        const servicesStatus = document.getElementById('servicesStatus');
        const servicesText = document.getElementById('servicesText');
        
        if (servicesStatus && servicesText) {
            const servicesReady = internet && jellyfin;
            servicesStatus.className = `status-indicator ${servicesReady ? 'status-online' : 'status-offline'}`;
            servicesText.textContent = `Services: ${servicesReady ? 'Ready' : 'Not Ready'}`;
        }
    }

    /**
     * Handle Jellyfin connection
     * @private
     */
    _handleJellyfinConnected(data) {
        // Enable Jellyfin skip optimization for future checks
        this.statusManager.enableJellyfinSkipOptimization(true);
        
        // Update global connectivity status
        if (window.connectivityStatus) {
            window.connectivityStatus.jellyfin = true;
            window.connectivityStatus.jellyfinConfirmed = true;
            
            // Save to localStorage for persistence
            localStorage.setItem('jellyfinConfirmed', 'true');
            localStorage.setItem('jellyfinConfirmedTimestamp', Date.now().toString());
        }
    }

    /**
     * Handle Jellyfin disconnection
     * @private
     */
    _handleJellyfinDisconnected(data) {
        // Disable skip optimization when disconnected
        this.statusManager.enableJellyfinSkipOptimization(false);
        
        // Update global connectivity status
        if (window.connectivityStatus) {
            window.connectivityStatus.jellyfin = false;
            window.connectivityStatus.jellyfinConfirmed = false;
            
            // Clear localStorage
            localStorage.removeItem('jellyfinConfirmed');
            localStorage.removeItem('jellyfinConfirmedTimestamp');
        }
    }

    /**
     * Handle local media count changes
     * @private
     */
    _handleLocalMediaCountChange(data) {
        // Update media count displays if they exist
        const countElements = document.querySelectorAll('.section-count, #mainMediaSectionCount');
        countElements.forEach(element => {
            if (element.textContent.includes('local') || element.id === 'mainMediaSectionCount') {
                // This would need to be integrated with the actual media loading system
                console.log('StatusManagerIntegration: Would update media count display');
            }
        });
    }

    /**
     * Handle service errors
     * @private
     */
    _handleServiceError(data) {
        const { service, error, failures } = data;
        
        // Show error indicators for repeated failures
        if (failures >= 3) {
            console.warn(`StatusManagerIntegration: ${service} has failed ${failures} times consecutively`);
            
            // Could show user notification here
            this._showServiceErrorNotification(service, error);
        }
    }

    /**
     * Update status display with current status
     * @private
     */
    _updateStatusDisplay(status) {
        // Update internet status
        if (status.internet) {
            this._handleConnectivityChange({
                service: 'internet',
                connected: status.internet.connected
            });
        }
        
        // Update Jellyfin status
        if (status.jellyfin) {
            this._handleConnectivityChange({
                service: 'jellyfin',
                connected: status.jellyfin.connected
            });
        }
        
        // Update VLC status
        if (status.vlc) {
            const vlcStatus = document.getElementById('vlcStatus');
            const vlcText = document.getElementById('vlcText');
            
            if (vlcStatus && vlcText) {
                vlcStatus.className = `status-indicator ${status.vlc.available ? 'status-online' : 'status-offline'}`;
                vlcText.textContent = `VLC: ${status.vlc.available ? 'Available' : 'Not Found'}`;
            }
        }
    }

    /**
     * Show service error notification
     * @private
     */
    _showServiceErrorNotification(service, error) {
        // This could integrate with existing notification system
        console.log(`StatusManagerIntegration: Service error notification for ${service}:`, error);
    }

    /**
     * Get current status
     */
    getCurrentStatus() {
        return this.statusManager ? this.statusManager.getStatus() : null;
    }

    /**
     * Force a full status refresh
     */
    async refreshStatus() {
        if (this.statusManager) {
            return await this.statusManager.forceFullRefresh();
        }
        return null;
    }

    /**
     * Cleanup when page unloads
     */
    cleanup() {
        if (this.statusManager) {
            this.statusManager.stopAdaptivePolling();
            this.statusManager.removeAllListeners();
        }
    }
}

// Create global instance
window.statusManagerIntegration = new StatusManagerIntegration();

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.statusManagerIntegration.initialize().catch(console.error);
    });
} else {
    window.statusManagerIntegration.initialize().catch(console.error);
}

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    window.statusManagerIntegration.cleanup();
});

console.log('StatusManager integration example loaded');