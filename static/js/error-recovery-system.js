/**
 * Error Recovery System - Comprehensive error handling and recovery mechanisms
 * Provides fallback mechanisms, retry logic with exponential backoff, and service-specific recovery
 */

class ErrorRecoverySystem {
  constructor(options = {}) {
    this.options = {
      maxRetries: options.maxRetries || 3,
      baseRetryDelay: options.baseRetryDelay || 1000,
      maxRetryDelay: options.maxRetryDelay || 30000,
      exponentialBackoffMultiplier: options.exponentialBackoffMultiplier || 2,
      enableLogging: options.enableLogging !== false,
      enableFallbacks: options.enableFallbacks !== false,
      enableServiceRecovery: options.enableServiceRecovery !== false,
      cacheTimeout: options.cacheTimeout || 300000, // 5 minutes
      ...options
    };

    // Track retry attempts for different operations
    this.retryAttempts = new Map();
    
    // Cache for fallback data
    this.fallbackCache = new Map();
    
    // Service recovery tracking
    this.serviceStates = new Map();
    
    // Error statistics
    this.errorStats = {
      totalErrors: 0,
      recoveredErrors: 0,
      fallbacksUsed: 0,
      retriesAttempted: 0,
      serviceFailures: new Map()
    };

    // Error type classifications
    this.errorTypes = {
      NETWORK: 'network',
      TIMEOUT: 'timeout',
      SERVICE_UNAVAILABLE: 'service_unavailable',
      VALIDATION: 'validation',
      PERMISSION: 'permission',
      UNKNOWN: 'unknown'
    };

    // Recovery strategies for different error types
    this.recoveryStrategies = new Map([
      [this.errorTypes.NETWORK, this._handleNetworkError.bind(this)],
      [this.errorTypes.TIMEOUT, this._handleTimeoutError.bind(this)],
      [this.errorTypes.SERVICE_UNAVAILABLE, this._handleServiceUnavailableError.bind(this)],
      [this.errorTypes.VALIDATION, this._handleValidationError.bind(this)],
      [this.errorTypes.PERMISSION, this._handlePermissionError.bind(this)],
      [this.errorTypes.UNKNOWN, this._handleUnknownError.bind(this)]
    ]);

    this._log('ErrorRecoverySystem initialized with options:', this.options);
  }

  /**
   * Handle loading error with comprehensive recovery mechanisms
   * @param {Error} error - The error that occurred
   * @param {Object} context - Context information about where the error occurred
   * @returns {Promise<Object>} Recovery result
   */
  async handleLoadingError(error, context = {}) {
    this.errorStats.totalErrors++;
    
    const errorInfo = {
      error,
      context,
      timestamp: Date.now(),
      errorType: this._classifyError(error),
      operationId: context.operationId || this._generateOperationId(),
      phase: context.phase || 'unknown',
      service: context.service || 'unknown'
    };

    this._log('Handling loading error:', errorInfo);

    try {
      // Attempt recovery based on error type
      const recoveryResult = await this.attemptRecovery(errorInfo);
      
      if (recoveryResult.success) {
        this.errorStats.recoveredErrors++;
        this._log('Error recovery successful:', recoveryResult);
        return recoveryResult;
      }

      // If recovery failed, try fallback mechanisms
      const fallbackResult = await this.provideFallback(errorInfo);
      
      if (fallbackResult.success) {
        this.errorStats.fallbacksUsed++;
        this._log('Fallback mechanism successful:', fallbackResult);
        return fallbackResult;
      }

      // If both recovery and fallback failed, schedule retry if appropriate
      if (this._shouldRetry(errorInfo)) {
        const retryResult = await this.scheduleRetry(errorInfo);
        this._log('Retry scheduled:', retryResult);
        return retryResult;
      }

      // All recovery mechanisms failed
      this._log('All recovery mechanisms failed for error:', errorInfo);
      return {
        success: false,
        error: errorInfo,
        recoveryAttempted: true,
        fallbackAttempted: true,
        retryScheduled: false,
        finalError: error
      };

    } catch (recoveryError) {
      this._log('Error during recovery process:', recoveryError);
      return {
        success: false,
        error: errorInfo,
        recoveryError,
        recoveryAttempted: false,
        fallbackAttempted: false,
        retryScheduled: false,
        finalError: error
      };
    }
  }

  /**
   * Attempt recovery for different error types
   * @param {Object} errorInfo - Error information object
   * @returns {Promise<Object>} Recovery result
   */
  async attemptRecovery(errorInfo) {
    const { errorType, operationId } = errorInfo;
    
    this._log(`Attempting recovery for ${errorType} error:`, errorInfo);

    try {
      // Get recovery strategy for this error type
      const recoveryStrategy = this.recoveryStrategies.get(errorType);
      
      if (!recoveryStrategy) {
        this._log(`No recovery strategy found for error type: ${errorType}`);
        return { success: false, reason: 'no_strategy', errorInfo };
      }

      // Execute recovery strategy
      const recoveryResult = await recoveryStrategy(errorInfo);
      
      return {
        success: recoveryResult.success || false,
        data: recoveryResult.data,
        method: recoveryResult.method || 'unknown',
        errorInfo,
        recoveryDetails: recoveryResult
      };

    } catch (recoveryError) {
      this._log('Recovery attempt failed:', recoveryError);
      return {
        success: false,
        error: recoveryError,
        errorInfo,
        reason: 'recovery_failed'
      };
    }
  }

  /**
   * Provide fallback mechanism with cache-based fallbacks
   * @param {Object} errorInfo - Error information object
   * @returns {Promise<Object>} Fallback result
   */
  async provideFallback(errorInfo) {
    const { operationId, context, phase, service } = errorInfo;
    
    this._log('Providing fallback for error:', errorInfo);

    try {
      // Try cache-based fallback first
      const cachedFallback = await this._getCachedFallback(operationId, context);
      if (cachedFallback.success) {
        return {
          success: true,
          data: cachedFallback.data,
          method: 'cache',
          source: 'fallback_cache',
          errorInfo,
          cacheAge: cachedFallback.age
        };
      }

      // Try service-specific fallbacks
      const serviceFallback = await this._getServiceFallback(service, context);
      if (serviceFallback.success) {
        return {
          success: true,
          data: serviceFallback.data,
          method: 'service_fallback',
          source: service,
          errorInfo,
          fallbackDetails: serviceFallback
        };
      }

      // Try phase-specific fallbacks
      const phaseFallback = await this._getPhaseFallback(phase, context);
      if (phaseFallback.success) {
        return {
          success: true,
          data: phaseFallback.data,
          method: 'phase_fallback',
          source: phase,
          errorInfo,
          fallbackDetails: phaseFallback
        };
      }

      // Default fallback - empty result with error indication
      return {
        success: true,
        data: this._getDefaultFallback(context),
        method: 'default',
        source: 'system_default',
        errorInfo,
        isDefault: true
      };

    } catch (fallbackError) {
      this._log('Fallback mechanism failed:', fallbackError);
      return {
        success: false,
        error: fallbackError,
        errorInfo,
        reason: 'fallback_failed'
      };
    }
  }

  /**
   * Schedule retry with exponential backoff logic
   * @param {Object} errorInfo - Error information object
   * @returns {Promise<Object>} Retry scheduling result
   */
  async scheduleRetry(errorInfo) {
    const { operationId, context } = errorInfo;
    
    // Get current retry count
    const currentRetries = this.retryAttempts.get(operationId) || 0;
    
    if (currentRetries >= this.options.maxRetries) {
      this._log(`Max retries (${this.options.maxRetries}) exceeded for operation: ${operationId}`);
      return {
        success: false,
        reason: 'max_retries_exceeded',
        currentRetries,
        maxRetries: this.options.maxRetries,
        errorInfo
      };
    }

    // Calculate delay with exponential backoff
    const delay = this._calculateRetryDelay(currentRetries);
    
    // Update retry count
    this.retryAttempts.set(operationId, currentRetries + 1);
    this.errorStats.retriesAttempted++;

    this._log(`Scheduling retry ${currentRetries + 1}/${this.options.maxRetries} for operation ${operationId} with delay ${delay}ms`);

    // Schedule the retry
    return new Promise((resolve) => {
      setTimeout(async () => {
        try {
          // Execute the retry operation
          const retryResult = await this._executeRetry(errorInfo, currentRetries + 1);
          
          if (retryResult.success) {
            // Clear retry attempts on success
            this.retryAttempts.delete(operationId);
          }
          
          resolve({
            success: retryResult.success,
            data: retryResult.data,
            retryAttempt: currentRetries + 1,
            delay,
            errorInfo,
            retryResult
          });
          
        } catch (retryError) {
          this._log('Retry execution failed:', retryError);
          resolve({
            success: false,
            error: retryError,
            retryAttempt: currentRetries + 1,
            delay,
            errorInfo,
            reason: 'retry_execution_failed'
          });
        }
      }, delay);
    });
  }

  /**
   * Cache fallback data for future use
   * @param {string} operationId - Operation identifier
   * @param {*} data - Data to cache
   * @param {Object} context - Context information
   */
  cacheFallbackData(operationId, data, context = {}) {
    const cacheEntry = {
      data,
      context,
      timestamp: Date.now(),
      expiresAt: Date.now() + this.options.cacheTimeout
    };

    this.fallbackCache.set(operationId, cacheEntry);
    this._log(`Cached fallback data for operation: ${operationId}`);
  }

  /**
   * Get error statistics
   * @returns {Object} Error statistics
   */
  getErrorStats() {
    return {
      ...this.errorStats,
      retryAttemptsActive: this.retryAttempts.size,
      cachedFallbacks: this.fallbackCache.size,
      serviceStates: Object.fromEntries(this.serviceStates)
    };
  }

  /**
   * Clear retry attempts for a specific operation
   * @param {string} operationId - Operation identifier
   */
  clearRetryAttempts(operationId) {
    this.retryAttempts.delete(operationId);
    this._log(`Cleared retry attempts for operation: ${operationId}`);
  }

  /**
   * Reset error recovery system state
   */
  reset() {
    this.retryAttempts.clear();
    this.fallbackCache.clear();
    this.serviceStates.clear();
    this.errorStats = {
      totalErrors: 0,
      recoveredErrors: 0,
      fallbacksUsed: 0,
      retriesAttempted: 0,
      serviceFailures: new Map()
    };
    this._log('ErrorRecoverySystem reset');
  }

  // Private methods

  /**
   * Classify error type based on error message and properties
   * @private
   * @param {Error} error - Error to classify
   * @returns {string} Error type
   */
  _classifyError(error) {
    const message = error.message.toLowerCase();
    
    if (message.includes('network') || message.includes('fetch') || message.includes('connection')) {
      return this.errorTypes.NETWORK;
    }
    
    if (message.includes('timeout') || message.includes('timed out')) {
      return this.errorTypes.TIMEOUT;
    }
    
    if (message.includes('unavailable') || message.includes('service') || message.includes('server')) {
      return this.errorTypes.SERVICE_UNAVAILABLE;
    }
    
    if (message.includes('validation') || message.includes('invalid') || message.includes('format')) {
      return this.errorTypes.VALIDATION;
    }
    
    if (message.includes('permission') || message.includes('unauthorized') || message.includes('forbidden')) {
      return this.errorTypes.PERMISSION;
    }
    
    return this.errorTypes.UNKNOWN;
  }

  /**
   * Generate unique operation ID
   * @private
   * @returns {string} Operation ID
   */
  _generateOperationId() {
    return `op_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Calculate retry delay with exponential backoff
   * @private
   * @param {number} retryCount - Current retry count
   * @returns {number} Delay in milliseconds
   */
  _calculateRetryDelay(retryCount) {
    const delay = this.options.baseRetryDelay * Math.pow(this.options.exponentialBackoffMultiplier, retryCount);
    return Math.min(delay, this.options.maxRetryDelay);
  }

  /**
   * Determine if operation should be retried
   * @private
   * @param {Object} errorInfo - Error information
   * @returns {boolean} True if should retry
   */
  _shouldRetry(errorInfo) {
    const { errorType, operationId } = errorInfo;
    const currentRetries = this.retryAttempts.get(operationId) || 0;
    
    // Don't retry if max retries exceeded
    if (currentRetries >= this.options.maxRetries) {
      return false;
    }
    
    // Don't retry validation or permission errors
    if (errorType === this.errorTypes.VALIDATION || errorType === this.errorTypes.PERMISSION) {
      return false;
    }
    
    return true;
  }

  /**
   * Log message if logging is enabled
   * @private
   * @param {string} message - Log message
   * @param {...*} args - Additional arguments
   */
  _log(message, ...args) {
    if (this.options.enableLogging) {
      console.log(`[ErrorRecoverySystem] ${message}`, ...args);
    }
  }
}  /**

   * Handle network errors
   * @private
   * @param {Object} errorInfo - Error information
   * @returns {Promise<Object>} Recovery result
   */
  async _handleNetworkError(errorInfo) {
    this._log('Handling network error:', errorInfo);
    
    try {
      // Try to detect if it's a connectivity issue
      const connectivityCheck = await this._checkConnectivity();
      
      if (!connectivityCheck.online) {
        return {
          success: false,
          reason: 'offline',
          method: 'connectivity_check',
          recommendation: 'switch_to_local_only'
        };
      }
      
      // If online, try alternative endpoints or methods
      const alternativeResult = await this._tryAlternativeEndpoint(errorInfo);
      
      return {
        success: alternativeResult.success,
        data: alternativeResult.data,
        method: 'alternative_endpoint',
        details: alternativeResult
      };
      
    } catch (error) {
      return {
        success: false,
        error,
        method: 'network_recovery',
        reason: 'recovery_failed'
      };
    }
  }

  /**
   * Handle timeout errors
   * @private
   * @param {Object} errorInfo - Error information
   * @returns {Promise<Object>} Recovery result
   */
  async _handleTimeoutError(errorInfo) {
    this._log('Handling timeout error:', errorInfo);
    
    try {
      // For timeout errors, try with increased timeout or cached data
      const cachedResult = await this._getCachedFallback(errorInfo.operationId, errorInfo.context);
      
      if (cachedResult.success) {
        return {
          success: true,
          data: cachedResult.data,
          method: 'cached_recovery',
          cacheAge: cachedResult.age
        };
      }
      
      // If no cache, recommend retry with longer timeout
      return {
        success: false,
        method: 'timeout_recovery',
        recommendation: 'retry_with_longer_timeout',
        suggestedTimeout: (errorInfo.context.timeout || 5000) * 2
      };
      
    } catch (error) {
      return {
        success: false,
        error,
        method: 'timeout_recovery',
        reason: 'recovery_failed'
      };
    }
  }

  /**
   * Handle service unavailable errors
   * @private
   * @param {Object} errorInfo - Error information
   * @returns {Promise<Object>} Recovery result
   */
  async _handleServiceUnavailableError(errorInfo) {
    this._log('Handling service unavailable error:', errorInfo);
    
    const { service } = errorInfo;
    
    try {
      // Update service state
      this.serviceStates.set(service, {
        status: 'unavailable',
        lastError: errorInfo.timestamp,
        errorCount: (this.serviceStates.get(service)?.errorCount || 0) + 1
      });
      
      // Track service failure statistics
      const currentFailures = this.errorStats.serviceFailures.get(service) || 0;
      this.errorStats.serviceFailures.set(service, currentFailures + 1);
      
      // Try service-specific recovery
      if (service === 'jellyfin') {
        return await this._handleJellyfinUnavailable(errorInfo);
      }
      
      // Generic service unavailable handling
      return {
        success: false,
        method: 'service_unavailable_recovery',
        recommendation: 'fallback_to_local',
        serviceState: this.serviceStates.get(service)
      };
      
    } catch (error) {
      return {
        success: false,
        error,
        method: 'service_unavailable_recovery',
        reason: 'recovery_failed'
      };
    }
  }

  /**
   * Handle validation errors
   * @private
   * @param {Object} errorInfo - Error information
   * @returns {Promise<Object>} Recovery result
   */
  async _handleValidationError(errorInfo) {
    this._log('Handling validation error:', errorInfo);
    
    try {
      // For validation errors, try to clean/filter the data
      const cleanedData = await this._cleanValidationData(errorInfo);
      
      if (cleanedData.success) {
        return {
          success: true,
          data: cleanedData.data,
          method: 'data_cleaning',
          itemsRemoved: cleanedData.itemsRemoved,
          originalCount: cleanedData.originalCount
        };
      }
      
      // If cleaning failed, return empty valid result
      return {
        success: true,
        data: this._getEmptyValidResult(errorInfo.context),
        method: 'empty_fallback',
        reason: 'validation_cleaning_failed'
      };
      
    } catch (error) {
      return {
        success: false,
        error,
        method: 'validation_recovery',
        reason: 'recovery_failed'
      };
    }
  }

  /**
   * Handle permission errors
   * @private
   * @param {Object} errorInfo - Error information
   * @returns {Promise<Object>} Recovery result
   */
  async _handlePermissionError(errorInfo) {
    this._log('Handling permission error:', errorInfo);
    
    try {
      // For permission errors, try alternative access methods
      const alternativeAccess = await this._tryAlternativeAccess(errorInfo);
      
      if (alternativeAccess.success) {
        return {
          success: true,
          data: alternativeAccess.data,
          method: 'alternative_access',
          accessMethod: alternativeAccess.method
        };
      }
      
      // If no alternative access, return limited/public data only
      return {
        success: true,
        data: this._getPublicDataOnly(errorInfo.context),
        method: 'public_data_fallback',
        reason: 'permission_denied'
      };
      
    } catch (error) {
      return {
        success: false,
        error,
        method: 'permission_recovery',
        reason: 'recovery_failed'
      };
    }
  }

  /**
   * Handle unknown errors
   * @private
   * @param {Object} errorInfo - Error information
   * @returns {Promise<Object>} Recovery result
   */
  async _handleUnknownError(errorInfo) {
    this._log('Handling unknown error:', errorInfo);
    
    try {
      // For unknown errors, try generic recovery approaches
      
      // First try cached data
      const cachedResult = await this._getCachedFallback(errorInfo.operationId, errorInfo.context);
      if (cachedResult.success) {
        return {
          success: true,
          data: cachedResult.data,
          method: 'cached_fallback',
          cacheAge: cachedResult.age
        };
      }
      
      // Try to continue with partial data
      const partialResult = await this._getPartialData(errorInfo.context);
      if (partialResult.success) {
        return {
          success: true,
          data: partialResult.data,
          method: 'partial_data',
          isPartial: true
        };
      }
      
      // Last resort - return safe default
      return {
        success: true,
        data: this._getDefaultFallback(errorInfo.context),
        method: 'default_fallback',
        reason: 'unknown_error'
      };
      
    } catch (error) {
      return {
        success: false,
        error,
        method: 'unknown_error_recovery',
        reason: 'recovery_failed'
      };
    }
  }

  /**
   * Get cached fallback data
   * @private
   * @param {string} operationId - Operation identifier
   * @param {Object} context - Context information
   * @returns {Promise<Object>} Cached data result
   */
  async _getCachedFallback(operationId, context) {
    const cacheEntry = this.fallbackCache.get(operationId);
    
    if (!cacheEntry) {
      return { success: false, reason: 'no_cache' };
    }
    
    // Check if cache is expired
    if (Date.now() > cacheEntry.expiresAt) {
      this.fallbackCache.delete(operationId);
      return { success: false, reason: 'cache_expired' };
    }
    
    const age = Date.now() - cacheEntry.timestamp;
    
    return {
      success: true,
      data: cacheEntry.data,
      age,
      context: cacheEntry.context
    };
  }

  /**
   * Get service-specific fallback
   * @private
   * @param {string} service - Service name
   * @param {Object} context - Context information
   * @returns {Promise<Object>} Service fallback result
   */
  async _getServiceFallback(service, context) {
    switch (service) {
      case 'jellyfin':
        return await this._getJellyfinFallback(context);
      case 'local':
        return await this._getLocalFallback(context);
      default:
        return { success: false, reason: 'no_service_fallback' };
    }
  }

  /**
   * Get phase-specific fallback
   * @private
   * @param {string} phase - Loading phase
   * @param {Object} context - Context information
   * @returns {Promise<Object>} Phase fallback result
   */
  async _getPhaseFallback(phase, context) {
    switch (phase) {
      case 'loading_local':
        return { success: true, data: [], method: 'empty_local' };
      case 'loading_remote_data':
        return { success: true, data: [], method: 'empty_remote' };
      case 'unified_complete':
        return { success: true, data: context.localMedia || [], method: 'local_only' };
      default:
        return { success: false, reason: 'no_phase_fallback' };
    }
  }

  /**
   * Get default fallback data
   * @private
   * @param {Object} context - Context information
   * @returns {*} Default fallback data
   */
  _getDefaultFallback(context) {
    return {
      items: [],
      count: 0,
      source: 'error_fallback',
      timestamp: Date.now(),
      error: true,
      message: 'Data unavailable due to error'
    };
  }

  /**
   * Execute retry operation
   * @private
   * @param {Object} errorInfo - Error information
   * @param {number} retryAttempt - Retry attempt number
   * @returns {Promise<Object>} Retry result
   */
  async _executeRetry(errorInfo, retryAttempt) {
    this._log(`Executing retry attempt ${retryAttempt} for operation:`, errorInfo.operationId);
    
    try {
      // If context has a retry function, use it
      if (errorInfo.context.retryFunction && typeof errorInfo.context.retryFunction === 'function') {
        const result = await errorInfo.context.retryFunction(retryAttempt);
        return {
          success: true,
          data: result,
          retryAttempt
        };
      }
      
      // Otherwise, indicate that retry needs to be handled externally
      return {
        success: false,
        reason: 'no_retry_function',
        retryAttempt,
        requiresExternalRetry: true
      };
      
    } catch (error) {
      return {
        success: false,
        error,
        retryAttempt,
        reason: 'retry_execution_failed'
      };
    }
  }

  /**
   * Check connectivity status
   * @private
   * @returns {Promise<Object>} Connectivity status
   */
  async _checkConnectivity() {
    try {
      // Use navigator.onLine as primary check
      if (!navigator.onLine) {
        return { online: false, method: 'navigator' };
      }
      
      // Try a simple fetch to verify actual connectivity
      const response = await fetch('/api/health', { 
        method: 'HEAD',
        timeout: 3000 
      });
      
      return { 
        online: response.ok, 
        method: 'fetch',
        status: response.status 
      };
      
    } catch (error) {
      return { 
        online: false, 
        method: 'fetch_failed',
        error: error.message 
      };
    }
  }

  /**
   * Try alternative endpoint
   * @private
   * @param {Object} errorInfo - Error information
   * @returns {Promise<Object>} Alternative endpoint result
   */
  async _tryAlternativeEndpoint(errorInfo) {
    // This would be implemented based on specific API endpoints available
    // For now, return failure to indicate no alternative available
    return {
      success: false,
      reason: 'no_alternative_endpoint'
    };
  }

  /**
   * Handle Jellyfin service unavailable
   * @private
   * @param {Object} errorInfo - Error information
   * @returns {Promise<Object>} Jellyfin recovery result
   */
  async _handleJellyfinUnavailable(errorInfo) {
    this._log('Handling Jellyfin unavailable error');
    
    // Try to get cached Jellyfin data
    const cachedJellyfin = await this._getCachedFallback(`jellyfin_${errorInfo.context.endpoint || 'default'}`, errorInfo.context);
    
    if (cachedJellyfin.success) {
      return {
        success: true,
        data: cachedJellyfin.data,
        method: 'jellyfin_cache',
        cacheAge: cachedJellyfin.age
      };
    }
    
    // Recommend switching to local-only mode
    return {
      success: false,
      method: 'jellyfin_unavailable',
      recommendation: 'switch_to_local_only',
      fallbackMode: 'local'
    };
  }

  /**
   * Get Jellyfin-specific fallback
   * @private
   * @param {Object} context - Context information
   * @returns {Promise<Object>} Jellyfin fallback result
   */
  async _getJellyfinFallback(context) {
    // Try to get any cached Jellyfin data
    const jellyfinCacheKeys = Array.from(this.fallbackCache.keys()).filter(key => key.startsWith('jellyfin_'));
    
    for (const key of jellyfinCacheKeys) {
      const cached = await this._getCachedFallback(key, context);
      if (cached.success) {
        return {
          success: true,
          data: cached.data,
          method: 'jellyfin_cache_fallback',
          cacheKey: key,
          cacheAge: cached.age
        };
      }
    }
    
    return { success: false, reason: 'no_jellyfin_cache' };
  }

  /**
   * Get local service fallback
   * @private
   * @param {Object} context - Context information
   * @returns {Promise<Object>} Local fallback result
   */
  async _getLocalFallback(context) {
    // For local service, return empty array as safe fallback
    return {
      success: true,
      data: [],
      method: 'local_empty_fallback'
    };
  }

  /**
   * Clean validation data by removing invalid items
   * @private
   * @param {Object} errorInfo - Error information
   * @returns {Promise<Object>} Cleaned data result
   */
  async _cleanValidationData(errorInfo) {
    const { context } = errorInfo;
    
    if (!context.data || !Array.isArray(context.data)) {
      return { success: false, reason: 'no_data_to_clean' };
    }
    
    const originalCount = context.data.length;
    const cleanedData = context.data.filter(item => {
      // Basic validation - item should be an object with some required properties
      return item && 
             typeof item === 'object' && 
             (item.id || item.Id || item.ID) &&
             (item.name || item.Name || item.title || item.Title);
    });
    
    const itemsRemoved = originalCount - cleanedData.length;
    
    return {
      success: true,
      data: cleanedData,
      originalCount,
      itemsRemoved,
      method: 'basic_validation_filter'
    };
  }

  /**
   * Get empty valid result for validation errors
   * @private
   * @param {Object} context - Context information
   * @returns {Object} Empty valid result
   */
  _getEmptyValidResult(context) {
    return {
      items: [],
      count: 0,
      source: 'validation_fallback',
      timestamp: Date.now(),
      validationError: true
    };
  }

  /**
   * Try alternative access methods for permission errors
   * @private
   * @param {Object} errorInfo - Error information
   * @returns {Promise<Object>} Alternative access result
   */
  async _tryAlternativeAccess(errorInfo) {
    // This would implement alternative access methods
    // For now, return failure
    return {
      success: false,
      reason: 'no_alternative_access'
    };
  }

  /**
   * Get public data only for permission errors
   * @private
   * @param {Object} context - Context information
   * @returns {Object} Public data
   */
  _getPublicDataOnly(context) {
    return {
      items: [],
      count: 0,
      source: 'public_only',
      timestamp: Date.now(),
      permissionRestricted: true
    };
  }

  /**
   * Get partial data for unknown errors
   * @private
   * @param {Object} context - Context information
   * @returns {Promise<Object>} Partial data result
   */
  async _getPartialData(context) {
    // Try to extract any partial data from context
    if (context.partialData && Array.isArray(context.partialData)) {
      return {
        success: true,
        data: context.partialData,
        method: 'context_partial'
      };
    }
    
    return { success: false, reason: 'no_partial_data' };
  }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
  module.exports = ErrorRecoverySystem;
}
/**

 * Service-Specific Recovery Extensions
 * Provides specialized recovery mechanisms for different services
 */

// Extend ErrorRecoverySystem with service-specific recovery methods
ErrorRecoverySystem.prototype.initializeServiceRecovery = function(options = {}) {
  this.serviceRecoveryOptions = {
    jellyfinRetryInterval: options.jellyfinRetryInterval || 30000, // 30 seconds
    connectivityCheckInterval: options.connectivityCheckInterval || 10000, // 10 seconds
    localOnlyFallbackEnabled: options.localOnlyFallbackEnabled !== false,
    serviceRecoveryDetection: options.serviceRecoveryDetection !== false,
    maxServiceRetries: options.maxServiceRetries || 5,
    ...options
  };

  // Service recovery timers
  this.serviceRecoveryTimers = new Map();
  
  // Service recovery callbacks
  this.serviceRecoveryCallbacks = new Map();
  
  // Connectivity monitoring
  this.connectivityMonitor = null;
  
  this._log('Service recovery initialized with options:', this.serviceRecoveryOptions);
};

/**
 * Handle Jellyfin service failure with specific recovery mechanisms
 * @param {Object} errorInfo - Error information
 * @param {Object} options - Recovery options
 * @returns {Promise<Object>} Recovery result
 */
ErrorRecoverySystem.prototype.handleJellyfinFailure = async function(errorInfo, options = {}) {
  this._log('Handling Jellyfin service failure:', errorInfo);
  
  const jellyfinState = this.serviceStates.get('jellyfin') || {};
  const failureCount = jellyfinState.errorCount || 0;
  
  try {
    // Update Jellyfin service state
    this.serviceStates.set('jellyfin', {
      status: 'failed',
      lastError: Date.now(),
      errorCount: failureCount + 1,
      lastRecoveryAttempt: null,
      recoveryInProgress: false
    });

    // Try immediate recovery strategies
    const immediateRecovery = await this._attemptJellyfinImmediateRecovery(errorInfo);
    if (immediateRecovery.success) {
      return {
        success: true,
        method: 'immediate_recovery',
        data: immediateRecovery.data,
        recoveryType: immediateRecovery.type
      };
    }

    // Schedule automatic recovery attempts
    this._scheduleJellyfinRecovery(errorInfo);

    // Provide fallback to local-only mode
    const localFallback = await this._switchToLocalOnlyMode(errorInfo);
    
    return {
      success: localFallback.success,
      method: 'local_only_fallback',
      data: localFallback.data,
      recoveryScheduled: true,
      fallbackMode: 'local_only'
    };

  } catch (error) {
    this._log('Error in Jellyfin failure handling:', error);
    return {
      success: false,
      error,
      method: 'jellyfin_failure_handling',
      reason: 'handling_failed'
    };
  }
};

/**
 * Handle connectivity loss with local-only mode fallback
 * @param {Object} errorInfo - Error information
 * @returns {Promise<Object>} Recovery result
 */
ErrorRecoverySystem.prototype.handleConnectivityLoss = async function(errorInfo) {
  this._log('Handling connectivity loss:', errorInfo);
  
  try {
    // Update connectivity state
    this.serviceStates.set('connectivity', {
      status: 'offline',
      lastCheck: Date.now(),
      offlineSince: Date.now()
    });

    // Start connectivity monitoring
    this._startConnectivityMonitoring();

    // Switch to local-only mode immediately
    const localOnlyResult = await this._switchToLocalOnlyMode(errorInfo);
    
    // Cache current state for recovery
    if (errorInfo.context && errorInfo.context.currentData) {
      this.cacheFallbackData(
        `connectivity_loss_${Date.now()}`,
        errorInfo.context.currentData,
        { reason: 'connectivity_loss', timestamp: Date.now() }
      );
    }

    return {
      success: localOnlyResult.success,
      method: 'connectivity_loss_handling',
      data: localOnlyResult.data,
      fallbackMode: 'local_only',
      monitoringStarted: true
    };

  } catch (error) {
    this._log('Error in connectivity loss handling:', error);
    return {
      success: false,
      error,
      method: 'connectivity_loss_handling',
      reason: 'handling_failed'
    };
  }
};

/**
 * Detect service recovery and attempt to reload content
 * @param {string} service - Service name
 * @returns {Promise<Object>} Recovery detection result
 */
ErrorRecoverySystem.prototype.detectServiceRecovery = async function(service) {
  this._log(`Detecting recovery for service: ${service}`);
  
  try {
    let recoveryResult = { success: false, method: 'unknown' };
    
    switch (service) {
      case 'jellyfin':
        recoveryResult = await this._detectJellyfinRecovery();
        break;
      case 'connectivity':
        recoveryResult = await this._detectConnectivityRecovery();
        break;
      default:
        recoveryResult = await this._detectGenericServiceRecovery(service);
    }

    if (recoveryResult.success) {
      // Update service state
      this.serviceStates.set(service, {
        status: 'recovered',
        lastRecovery: Date.now(),
        errorCount: 0,
        recoveryMethod: recoveryResult.method
      });

      // Execute recovery callbacks
      await this._executeServiceRecoveryCallbacks(service, recoveryResult);
    }

    return recoveryResult;

  } catch (error) {
    this._log(`Error detecting recovery for ${service}:`, error);
    return {
      success: false,
      error,
      method: 'recovery_detection',
      reason: 'detection_failed'
    };
  }
};

/**
 * Register callback for service recovery events
 * @param {string} service - Service name
 * @param {Function} callback - Recovery callback function
 */
ErrorRecoverySystem.prototype.onServiceRecovery = function(service, callback) {
  if (!this.serviceRecoveryCallbacks.has(service)) {
    this.serviceRecoveryCallbacks.set(service, []);
  }
  this.serviceRecoveryCallbacks.get(service).push(callback);
  this._log(`Registered recovery callback for service: ${service}`);
};

/**
 * Start automatic service recovery monitoring
 * @param {Array} services - Services to monitor
 */
ErrorRecoverySystem.prototype.startServiceRecoveryMonitoring = function(services = ['jellyfin', 'connectivity']) {
  this._log('Starting service recovery monitoring for:', services);
  
  services.forEach(service => {
    if (!this.serviceRecoveryTimers.has(service)) {
      const interval = service === 'connectivity' 
        ? this.serviceRecoveryOptions.connectivityCheckInterval
        : this.serviceRecoveryOptions.jellyfinRetryInterval;
      
      const timer = setInterval(async () => {
        const serviceState = this.serviceStates.get(service);
        if (serviceState && (serviceState.status === 'failed' || serviceState.status === 'offline')) {
          await this.detectServiceRecovery(service);
        }
      }, interval);
      
      this.serviceRecoveryTimers.set(service, timer);
    }
  });
};

/**
 * Stop service recovery monitoring
 * @param {string} service - Service to stop monitoring (optional, stops all if not provided)
 */
ErrorRecoverySystem.prototype.stopServiceRecoveryMonitoring = function(service = null) {
  if (service) {
    const timer = this.serviceRecoveryTimers.get(service);
    if (timer) {
      clearInterval(timer);
      this.serviceRecoveryTimers.delete(service);
      this._log(`Stopped recovery monitoring for service: ${service}`);
    }
  } else {
    // Stop all monitoring
    this.serviceRecoveryTimers.forEach((timer, serviceName) => {
      clearInterval(timer);
      this._log(`Stopped recovery monitoring for service: ${serviceName}`);
    });
    this.serviceRecoveryTimers.clear();
  }
};

// Private service-specific recovery methods

/**
 * Attempt immediate Jellyfin recovery
 * @private
 * @param {Object} errorInfo - Error information
 * @returns {Promise<Object>} Recovery result
 */
ErrorRecoverySystem.prototype._attemptJellyfinImmediateRecovery = async function(errorInfo) {
  this._log('Attempting immediate Jellyfin recovery');
  
  try {
    // Try to ping Jellyfin health endpoint
    const healthCheck = await this._checkJellyfinHealth();
    if (healthCheck.success) {
      // If health check passes, try to reload the failed operation
      const reloadResult = await this._reloadJellyfinOperation(errorInfo);
      return {
        success: reloadResult.success,
        data: reloadResult.data,
        type: 'health_check_recovery'
      };
    }

    // Try alternative Jellyfin endpoints
    const alternativeResult = await this._tryJellyfinAlternativeEndpoints(errorInfo);
    if (alternativeResult.success) {
      return {
        success: true,
        data: alternativeResult.data,
        type: 'alternative_endpoint_recovery'
      };
    }

    return { success: false, reason: 'immediate_recovery_failed' };

  } catch (error) {
    this._log('Immediate Jellyfin recovery failed:', error);
    return { success: false, error, reason: 'recovery_error' };
  }
};

/**
 * Schedule automatic Jellyfin recovery attempts
 * @private
 * @param {Object} errorInfo - Error information
 */
ErrorRecoverySystem.prototype._scheduleJellyfinRecovery = function(errorInfo) {
  this._log('Scheduling Jellyfin recovery attempts');
  
  // Clear any existing recovery timer
  const existingTimer = this.serviceRecoveryTimers.get('jellyfin_recovery');
  if (existingTimer) {
    clearInterval(existingTimer);
  }

  let recoveryAttempts = 0;
  const maxAttempts = this.serviceRecoveryOptions.maxServiceRetries;
  
  const recoveryTimer = setInterval(async () => {
    recoveryAttempts++;
    this._log(`Jellyfin recovery attempt ${recoveryAttempts}/${maxAttempts}`);
    
    try {
      const recoveryResult = await this.detectServiceRecovery('jellyfin');
      
      if (recoveryResult.success) {
        this._log('Jellyfin recovery successful, clearing timer');
        clearInterval(recoveryTimer);
        this.serviceRecoveryTimers.delete('jellyfin_recovery');
        
        // Attempt to reload original operation
        await this._reloadJellyfinOperation(errorInfo);
      } else if (recoveryAttempts >= maxAttempts) {
        this._log('Max Jellyfin recovery attempts reached, stopping');
        clearInterval(recoveryTimer);
        this.serviceRecoveryTimers.delete('jellyfin_recovery');
      }
    } catch (error) {
      this._log('Error during scheduled Jellyfin recovery:', error);
    }
  }, this.serviceRecoveryOptions.jellyfinRetryInterval);
  
  this.serviceRecoveryTimers.set('jellyfin_recovery', recoveryTimer);
};

/**
 * Switch to local-only mode as fallback
 * @private
 * @param {Object} errorInfo - Error information
 * @returns {Promise<Object>} Local-only mode result
 */
ErrorRecoverySystem.prototype._switchToLocalOnlyMode = async function(errorInfo) {
  this._log('Switching to local-only mode');
  
  try {
    // Try to get local data from cache or context
    let localData = [];
    
    if (errorInfo.context && errorInfo.context.localMedia) {
      localData = errorInfo.context.localMedia;
    } else {
      // Try to get cached local data
      const cachedLocal = await this._getCachedFallback('local_media', errorInfo.context);
      if (cachedLocal.success) {
        localData = cachedLocal.data;
      }
    }

    return {
      success: true,
      data: localData,
      mode: 'local_only',
      itemCount: localData.length
    };

  } catch (error) {
    this._log('Error switching to local-only mode:', error);
    return {
      success: false,
      error,
      mode: 'local_only',
      reason: 'switch_failed'
    };
  }
};

/**
 * Start connectivity monitoring
 * @private
 */
ErrorRecoverySystem.prototype._startConnectivityMonitoring = function() {
  if (this.connectivityMonitor) {
    return; // Already monitoring
  }

  this._log('Starting connectivity monitoring');
  
  this.connectivityMonitor = setInterval(async () => {
    const connectivityCheck = await this._checkConnectivity();
    const currentState = this.serviceStates.get('connectivity');
    
    if (connectivityCheck.online && currentState && currentState.status === 'offline') {
      this._log('Connectivity restored');
      
      // Update connectivity state
      this.serviceStates.set('connectivity', {
        status: 'online',
        lastCheck: Date.now(),
        onlineSince: Date.now()
      });
      
      // Execute connectivity recovery callbacks
      await this._executeServiceRecoveryCallbacks('connectivity', {
        success: true,
        method: 'connectivity_monitoring'
      });
    }
  }, this.serviceRecoveryOptions.connectivityCheckInterval);
};

/**
 * Detect Jellyfin service recovery
 * @private
 * @returns {Promise<Object>} Recovery detection result
 */
ErrorRecoverySystem.prototype._detectJellyfinRecovery = async function() {
  try {
    const healthCheck = await this._checkJellyfinHealth();
    
    if (healthCheck.success) {
      this._log('Jellyfin service recovery detected');
      return {
        success: true,
        method: 'health_check',
        responseTime: healthCheck.responseTime,
        timestamp: Date.now()
      };
    }
    
    return { success: false, reason: 'health_check_failed' };
    
  } catch (error) {
    return { success: false, error, reason: 'detection_error' };
  }
};

/**
 * Detect connectivity recovery
 * @private
 * @returns {Promise<Object>} Recovery detection result
 */
ErrorRecoverySystem.prototype._detectConnectivityRecovery = async function() {
  try {
    const connectivityCheck = await this._checkConnectivity();
    
    if (connectivityCheck.online) {
      this._log('Connectivity recovery detected');
      return {
        success: true,
        method: connectivityCheck.method,
        timestamp: Date.now()
      };
    }
    
    return { success: false, reason: 'still_offline' };
    
  } catch (error) {
    return { success: false, error, reason: 'detection_error' };
  }
};

/**
 * Detect generic service recovery
 * @private
 * @param {string} service - Service name
 * @returns {Promise<Object>} Recovery detection result
 */
ErrorRecoverySystem.prototype._detectGenericServiceRecovery = async function(service) {
  // Generic service recovery detection
  // This would be implemented based on specific service requirements
  return { success: false, reason: 'no_generic_detection' };
};

/**
 * Execute service recovery callbacks
 * @private
 * @param {string} service - Service name
 * @param {Object} recoveryResult - Recovery result
 */
ErrorRecoverySystem.prototype._executeServiceRecoveryCallbacks = async function(service, recoveryResult) {
  const callbacks = this.serviceRecoveryCallbacks.get(service) || [];
  
  this._log(`Executing ${callbacks.length} recovery callbacks for service: ${service}`);
  
  for (const callback of callbacks) {
    try {
      await callback(recoveryResult);
    } catch (error) {
      this._log(`Error executing recovery callback for ${service}:`, error);
    }
  }
};

/**
 * Check Jellyfin service health
 * @private
 * @returns {Promise<Object>} Health check result
 */
ErrorRecoverySystem.prototype._checkJellyfinHealth = async function() {
  try {
    const startTime = Date.now();
    const response = await fetch('/api/jellyfin/health', {
      method: 'GET',
      timeout: 5000
    });
    
    const responseTime = Date.now() - startTime;
    
    return {
      success: response.ok,
      status: response.status,
      responseTime,
      timestamp: Date.now()
    };
    
  } catch (error) {
    return {
      success: false,
      error: error.message,
      timestamp: Date.now()
    };
  }
};

/**
 * Reload Jellyfin operation after recovery
 * @private
 * @param {Object} errorInfo - Original error information
 * @returns {Promise<Object>} Reload result
 */
ErrorRecoverySystem.prototype._reloadJellyfinOperation = async function(errorInfo) {
  this._log('Reloading Jellyfin operation after recovery');
  
  try {
    // If context has a reload function, use it
    if (errorInfo.context && errorInfo.context.reloadFunction) {
      const result = await errorInfo.context.reloadFunction();
      return {
        success: true,
        data: result,
        method: 'context_reload'
      };
    }
    
    // Otherwise, try to reconstruct the operation
    const reconstructed = await this._reconstructJellyfinOperation(errorInfo);
    return reconstructed;
    
  } catch (error) {
    this._log('Error reloading Jellyfin operation:', error);
    return {
      success: false,
      error,
      method: 'reload_operation',
      reason: 'reload_failed'
    };
  }
};

/**
 * Try alternative Jellyfin endpoints
 * @private
 * @param {Object} errorInfo - Error information
 * @returns {Promise<Object>} Alternative endpoint result
 */
ErrorRecoverySystem.prototype._tryJellyfinAlternativeEndpoints = async function(errorInfo) {
  const alternativeEndpoints = [
    '/api/jellyfin/items/alternative',
    '/api/jellyfin/media/fallback',
    '/api/jellyfin/library/basic'
  ];
  
  for (const endpoint of alternativeEndpoints) {
    try {
      this._log(`Trying alternative Jellyfin endpoint: ${endpoint}`);
      
      const response = await fetch(endpoint, {
        method: 'GET',
        timeout: 5000
      });
      
      if (response.ok) {
        const data = await response.json();
        return {
          success: true,
          data: data,
          endpoint: endpoint
        };
      }
    } catch (error) {
      this._log(`Alternative endpoint ${endpoint} failed:`, error);
    }
  }
  
  return { success: false, reason: 'all_alternatives_failed' };
};

/**
 * Reconstruct Jellyfin operation from error context
 * @private
 * @param {Object} errorInfo - Error information
 * @returns {Promise<Object>} Reconstruction result
 */
ErrorRecoverySystem.prototype._reconstructJellyfinOperation = async function(errorInfo) {
  // This would implement operation reconstruction based on the original context
  // For now, return a basic reconstruction attempt
  return {
    success: false,
    reason: 'reconstruction_not_implemented',
    method: 'reconstruct_operation'
  };
};

/**
 * Clean up service recovery resources
 */
ErrorRecoverySystem.prototype.cleanupServiceRecovery = function() {
  this._log('Cleaning up service recovery resources');
  
  // Stop all recovery monitoring
  this.stopServiceRecoveryMonitoring();
  
  // Clear connectivity monitor
  if (this.connectivityMonitor) {
    clearInterval(this.connectivityMonitor);
    this.connectivityMonitor = null;
  }
  
  // Clear service recovery callbacks
  this.serviceRecoveryCallbacks.clear();
  
  this._log('Service recovery cleanup completed');
};

// Override the reset method to include service recovery cleanup
const originalReset = ErrorRecoverySystem.prototype.reset;
ErrorRecoverySystem.prototype.reset = function() {
  this.cleanupServiceRecovery();
  originalReset.call(this);
};