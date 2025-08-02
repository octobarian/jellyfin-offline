/**
 * Enhanced Progressive Media Loader - Non-blocking local-first loading strategy
 * Loads local media immediately (< 2 seconds), enables user interaction, then loads remote media in background
 */

class ProgressiveMediaLoader {
  constructor(statusManager = null) {
    this.statusManager = statusManager;
    this.localMedia = [];
    this.remoteMedia = [];
    this.unifiedMedia = [];

    // Initialize PhaseManager component with availability check
    if (typeof PhaseManager !== "undefined") {
      this.phaseManager = new PhaseManager();
    } else {
      console.warn(
        "ProgressiveMediaLoader: PhaseManager not available, using fallback implementation"
      );
      this.phaseManager = this._createFallbackPhaseManager();
    }

    // Initialize ModeConsistencyManager component with availability check
    if (typeof ModeConsistencyManager !== "undefined") {
      this.modeConsistencyManager = new ModeConsistencyManager({
        enableLogging: true,
        preserveLocalItems: true,
        validateTransitions: true,
        mergeStrategy: 'additive'
      });
    } else {
      console.warn(
        "ProgressiveMediaLoader: ModeConsistencyManager not available, using fallback implementation"
      );
      this.modeConsistencyManager = this._createFallbackModeConsistencyManager();
    }

    // Phase constants for consistency
    this.PHASES = {
      INITIALIZING: "initializing",
      LOADING_LOCAL: "loading_local",
      LOCAL_COMPLETE: "local_complete",
      CHECKING_CONNECTIVITY: "checking_connectivity",
      CONNECTIVITY_CHECKED: "connectivity_checked",
      LOADING_REMOTE_DATA: "loading_remote_data",
      REMOTE_COMPLETE: "remote_complete",
      REMOTE_LOADING_COMPLETE: "remote_loading_complete",
      REMOTE_LOADING_ERROR: "remote_loading_error",
      UNIFIED_COMPLETE: "unified_complete",
      ERROR: "error",
      COMPLETE: "complete",
      LOADING_REMOTE: "loading_remote",
      CHECKING_SERVICES: "checking_services",
      MERGING_MEDIA: "merging_media",
    };

    // Loading states for non-blocking operation
    this.loadingStates = {
      phase: this.PHASES.INITIALIZING,
      local: { status: "pending", count: 0, duration: 0, startTime: null },
      remote: { status: "pending", count: 0, duration: 0, startTime: null },
      unified: { status: "pending", count: 0, duration: 0, startTime: null },
      userInteractionEnabled: false,
      backgroundTasksActive: false,
      errors: [],
    };

    this.callbacks = {
      onLocalLoaded: null,
      onRemoteLoaded: null,
      onComplete: null,
      onError: null,
      onLoadingStateChange: null,
      onUserInteractionEnabled: null,
      onBackgroundTasksStarted: null,
      onBackgroundTasksCompleted: null,
    };

    // Performance tracking
    this.performanceMetrics = {
      timeToFirstInteraction: null,
      timeToLocalComplete: null,
      timeToRemoteComplete: null,
      timeToFullComplete: null,
    };

    // Status integration
    this.connectivityMode = "unknown"; // 'online', 'offline', 'degraded'
    this.loadingStrategy = "non-blocking"; // 'non-blocking', 'blocking', 'local-only'

    // Status manager event listeners
    this.statusEventListeners = new Map();

    // Initialize status manager integration
    if (this.statusManager) {
      this._initializeStatusManagerIntegration();
    }

    // Automatic retry configuration
    this.retryConfig = {
      maxRetries: 3,
      retryDelay: 2000,
      exponentialBackoff: true,
      retryOnServiceRecovery: true,
    };

    // Track retry attempts
    this.retryAttempts = new Map();

    console.log(
      "ProgressiveMediaLoader: Initialized with non-blocking strategy and status integration"
    );
  }

  /**
   * Create a fallback ModeConsistencyManager implementation when ModeConsistencyManager class is not available
   * @returns {Object} Fallback ModeConsistencyManager implementation
   * @private
   */
  _createFallbackModeConsistencyManager() {
    return {
      mergeMediaResults: function(localItems = [], remoteItems = [], options = {}) {
        console.warn("Fallback ModeConsistencyManager: Using basic merge logic");
        // Basic additive merge - preserve local items and add remote items
        const result = [...localItems];
        const localIds = new Set(localItems.map(item => item.id || item.Id || item.ID).filter(Boolean));
        
        remoteItems.forEach(remoteItem => {
          const remoteId = remoteItem.id || remoteItem.Id || remoteItem.ID;
          if (!remoteId || !localIds.has(remoteId)) {
            result.push(remoteItem);
          }
        });
        
        return result;
      },

      preserveExistingItems: function(currentItems = [], newItems = [], options = {}) {
        console.warn("Fallback ModeConsistencyManager: Using basic preservation logic");
        // Preserve all current items and add new ones that don't exist
        const result = [...currentItems];
        const currentIds = new Set(currentItems.map(item => item.id || item.Id || item.ID).filter(Boolean));
        
        newItems.forEach(newItem => {
          const newId = newItem.id || newItem.Id || newItem.ID;
          if (!newId || !currentIds.has(newId)) {
            result.push(newItem);
          }
        });
        
        return result;
      },

      validateModeTransition: function(fromMode, toMode, items = []) {
        console.warn("Fallback ModeConsistencyManager: Basic validation only");
        return {
          isValid: true,
          fromMode,
          toMode,
          itemCount: items.length,
          errors: [],
          warnings: [],
          timestamp: Date.now()
        };
      },

      handleModeSwitch: function(newMode, options = {}) {
        console.warn("Fallback ModeConsistencyManager: Basic mode switch handling");
        return {
          success: true,
          fromMode: null,
          toMode: newMode,
          preservedItems: options.items || [],
          errors: [],
          timestamp: Date.now()
        };
      }
    };
  }

  /**
   * Create a fallback PhaseManager implementation when PhaseManager class is not available
   * @returns {Object} Fallback PhaseManager implementation
   * @private
   */
  _createFallbackPhaseManager() {
    const fallbackPhaseMessages = {
      initializing: "Initializing media loading...",
      loading_local: "Loading local media...",
      local_complete: "Local media loaded",
      checking_connectivity: "Checking remote services...",
      connectivity_checked: "Remote services checked",
      loading_remote_data: "Loading remote media in background...",
      remote_complete: "Remote media loaded",
      remote_loading_complete: "Background loading complete",
      remote_loading_error: "Background loading failed",
      unified_complete: "All media loaded",
      error: "Loading error occurred",
      complete: "Loading complete",
      loading_remote: "Loading remote media...",
      checking_services: "Checking remote service availability...",
      merging_media: "Integrating remote media...",
    };

    return {
      currentPhase: null,
      knownPhases: new Set(Object.keys(fallbackPhaseMessages)),

      validatePhase: function (phase) {
        const isValid = this.knownPhases.has(phase);
        if (!isValid) {
          console.warn(
            `Fallback PhaseManager: Unknown phase encountered: "${phase}"`
          );
        }
        return isValid;
      },

      getPhaseMessage: function (phase, progress = {}) {
        if (!this.validatePhase(phase)) {
          return `Loading: ${phase}`;
        }

        let message = fallbackPhaseMessages[phase] || `Loading: ${phase}`;

        // Special handling for specific phases
        if (
          phase === "remote_loading_complete" &&
          progress.remoteCount !== undefined
        ) {
          message = `Background loading complete (${progress.remoteCount} remote items)`;
        } else if (phase === "remote_loading_error" && progress.error) {
          message = `Background loading failed: ${progress.error}`;
        }

        // Add progress information if available
        if (
          progress.current !== undefined &&
          progress.total !== undefined &&
          progress.total > 0
        ) {
          const percentage = Math.round(
            (progress.current / progress.total) * 100
          );
          message += ` (${percentage}%)`;
        }

        if (
          progress.count !== undefined &&
          phase !== "remote_loading_complete"
        ) {
          message += ` - ${progress.count} items`;
        }

        return message;
      },

      transitionToPhase: function (newPhase, context = {}) {
        if (!this.validatePhase(newPhase)) {
          console.error(
            `Fallback PhaseManager: Cannot transition to unknown phase: "${newPhase}"`
          );
          return false;
        }

        const previousPhase = this.currentPhase;
        this.currentPhase = newPhase;

        console.log(
          `Fallback PhaseManager: Transitioned from "${previousPhase}" to "${newPhase}"`
        );
        return true;
      },

      getCurrentPhase: function () {
        return this.currentPhase;
      },

      handleUnknownPhase: function (phase) {
        console.error(
          `Fallback PhaseManager: Unknown phase encountered: "${phase}"`
        );
        return `Loading: ${phase}`;
      },
    };
  }

  /**
   * Handle unknown phases encountered during loading with fallback behavior
   * @param {string} unknownPhase - The unknown phase that was encountered
   * @param {string} context - Context where the unknown phase was encountered
   * @param {Object} fallbackOptions - Options for fallback behavior
   * @returns {string} Fallback phase to use
   */
  handleUnknownPhase(unknownPhase, context = "unknown", fallbackOptions = {}) {
    console.error(
      `ProgressiveMediaLoader: Unknown phase "${unknownPhase}" encountered in ${context}`
    );

    // Log error for debugging
    this.loadingStates.errors.push({
      type: "unknown_phase",
      phase: unknownPhase,
      context: context,
      timestamp: Date.now(),
      fallbackUsed: true,
    });

    // Determine appropriate fallback phase based on context
    let fallbackPhase = this.PHASES.ERROR;

    if (context.includes("local") || context.includes("Local")) {
      fallbackPhase = this.PHASES.LOADING_LOCAL;
    } else if (
      context.includes("remote") ||
      context.includes("Remote") ||
      context.includes("background")
    ) {
      fallbackPhase = this.PHASES.LOADING_REMOTE_DATA;
    } else if (context.includes("complete") || context.includes("Complete")) {
      fallbackPhase = this.PHASES.UNIFIED_COMPLETE;
    } else if (context.includes("init") || context.includes("Init")) {
      fallbackPhase = this.PHASES.INITIALIZING;
    }

    // Use provided fallback if available and valid
    if (
      fallbackOptions.fallbackPhase &&
      this.phaseManager.validatePhase &&
      this.phaseManager.validatePhase(fallbackOptions.fallbackPhase)
    ) {
      fallbackPhase = fallbackOptions.fallbackPhase;
    }

    console.warn(
      `ProgressiveMediaLoader: Using fallback phase "${fallbackPhase}" for unknown phase "${unknownPhase}"`
    );

    // Attempt to transition to fallback phase
    if (
      !this.phaseManager.transitionToPhase(fallbackPhase, {
        context: `fallback_from_${unknownPhase}`,
        originalPhase: unknownPhase,
        fallbackReason: "unknown_phase",
      })
    ) {
      console.error(
        `ProgressiveMediaLoader: Failed to transition to fallback phase "${fallbackPhase}"`
      );
      // Last resort - transition to error phase
      this.phaseManager.transitionToPhase(this.PHASES.ERROR, {
        context: "fallback_failed",
        originalPhase: unknownPhase,
        failedFallback: fallbackPhase,
      });
      return this.PHASES.ERROR;
    }

    return fallbackPhase;
  }

  /**
   * Safely transition to a phase with validation and fallback behavior
   * @param {string} targetPhase - Phase to transition to
   * @param {Object} context - Context information for the transition
   * @param {Object} options - Options for fallback behavior
   * @returns {boolean} True if transition was successful
   */
  safeTransitionToPhase(targetPhase, context = {}, options = {}) {
    // First validate the target phase
    if (
      this.phaseManager.validatePhase &&
      !this.phaseManager.validatePhase(targetPhase)
    ) {
      console.error(
        `ProgressiveMediaLoader: Attempting to transition to unknown phase: "${targetPhase}"`
      );

      // Use fallback behavior
      const fallbackPhase = this.handleUnknownPhase(
        targetPhase,
        context.context || "safeTransitionToPhase",
        options
      );
      targetPhase = fallbackPhase;
    }

    // Attempt the transition
    const success = this.phaseManager.transitionToPhase(targetPhase, context);

    if (!success) {
      console.error(
        `ProgressiveMediaLoader: Failed to transition to phase "${targetPhase}"`
      );

      // If transition failed and we're not already in error state, try to transition to error
      if (
        targetPhase !== this.PHASES.ERROR &&
        this.phaseManager.getCurrentPhase &&
        this.phaseManager.getCurrentPhase() !== this.PHASES.ERROR
      ) {
        console.warn(
          "ProgressiveMediaLoader: Attempting fallback transition to error phase"
        );
        return this.phaseManager.transitionToPhase(this.PHASES.ERROR, {
          context: "transition_fallback",
          failedPhase: targetPhase,
          originalContext: context,
        });
      }
    }

    return success;
  }

  /**
   * Set callback functions for different loading events
   * @param {Object} callbacks - Object containing callback functions
   */
  setCallbacks(callbacks) {
    this.callbacks = { ...this.callbacks, ...callbacks };
  }

  /**
   * Enhanced non-blocking media loading - displays local media immediately
   * @param {boolean} forceRefresh - Force refresh of cached data
   * @param {Object} options - Loading options
   */
  async loadMedia(forceRefresh = false, options = {}) {
    const startTime = Date.now();
    console.log(
      "ProgressiveMediaLoader: Starting non-blocking media loading"
    );

    try {
      // Initialize loading state with phase transition
      this._initializeLoadingState();
      this.safeTransitionToPhase(this.PHASES.INITIALIZING, {
        context: "loadMedia",
      });
      this._notifyLoadingStateChange(
        this.phaseManager.getPhaseMessage(this.PHASES.INITIALIZING)
      );

      // Phase 1: Load local media immediately (< 5 seconds target)
      await this.loadLocalMediaImmediate(forceRefresh);

      // Enable user interaction after local media loads
      this.enableUserInteraction();

      // Phase 2: Start background remote media loading (non-blocking)
      this.loadRemoteMediaBackground(forceRefresh);

      return this.unifiedMedia;
    } catch (error) {
      console.error(
        "ProgressiveMediaLoader: Error during non-blocking loading:",
        error
      );
      this._handleLoadingError(error, "initialization");
      throw error;
    }
  }

  /**
   * Load local media immediately with 5-second target (increased for reliability)
   * @param {boolean} forceRefresh - Force refresh of cached data
   */
  async loadLocalMediaImmediate(forceRefresh = false) {
    const startTime = Date.now();
    console.log(
      "ProgressiveMediaLoader: Loading local media immediately"
    );

    try {
      // Update loading state with phase transition
      this.safeTransitionToPhase(this.PHASES.LOADING_LOCAL, {
        context: "loadLocalMediaImmediate",
      });
      this.loadingStates.phase = this.PHASES.LOADING_LOCAL;
      this.loadingStates.local.status = "loading";
      this.loadingStates.local.startTime = startTime;
      this._notifyLoadingStateChange(
        this.phaseManager.getPhaseMessage(this.PHASES.LOADING_LOCAL)
      );

      // Load local media with timeout to ensure < 5 second response (increased from 2s)
      // For immediate loading, explicitly disable file validation for speed
      const localMediaPromise = this.loadLocalMediaFast();
      const timeoutPromise = new Promise((_, reject) => {
        setTimeout(
          () => reject(new Error("Local media loading timeout")),
          5000
        );
      });

      // Race between loading and timeout
      await Promise.race([localMediaPromise, timeoutPromise]);

      // Update performance metrics
      const duration = Date.now() - startTime;
      this.performanceMetrics.timeToLocalComplete = duration;
      this.loadingStates.local.duration = duration;
      this.loadingStates.local.status = "complete";
      this.loadingStates.local.count = this.localMedia.length;

      console.log(
        `ProgressiveMediaLoader: Local media loaded in ${duration}ms (${this.localMedia.length} items)`
      );

      // Transition to local_complete phase
      this.safeTransitionToPhase(this.PHASES.LOCAL_COMPLETE, {
        context: "loadLocalMediaImmediate",
        duration: duration,
        count: this.localMedia.length,
      });

      // Update unified media with local items immediately
      this.unifiedMedia = [...this.localMedia];

      // Notify callbacks
      if (this.callbacks.onLocalLoaded) {
        this.callbacks.onLocalLoaded(this.localMedia, this.unifiedMedia);
      }

      this._notifyLoadingStateChange(
        this.phaseManager.getPhaseMessage(this.PHASES.LOCAL_COMPLETE, {
          count: this.localMedia.length,
        })
      );
    } catch (error) {
      const duration = Date.now() - startTime;
      this.loadingStates.local.duration = duration;
      this.loadingStates.local.status = "error";

      console.error(
        `ProgressiveMediaLoader: Local media loading failed after ${duration}ms:`,
        error
      );

      // Try to load from cache as fallback
      const cachedLocal = this._loadLocalFromCache();
      if (cachedLocal.length > 0) {
        this.localMedia = cachedLocal;
        this.unifiedMedia = [...this.localMedia];
        this.loadingStates.local.status = "complete";
        this.loadingStates.local.count = this.localMedia.length;

        console.log(
          `ProgressiveMediaLoader: Loaded ${cachedLocal.length} local items from cache`
        );

        // Transition to local_complete even with cache fallback
        if (
          !this.phaseManager.transitionToPhase(this.PHASES.LOCAL_COMPLETE, {
            context: "cache_fallback",
            duration: duration,
            count: this.localMedia.length,
            fromCache: true,
          })
        ) {
          console.error(
            "ProgressiveMediaLoader: Failed to transition to local_complete phase after cache fallback"
          );
        }

        if (this.callbacks.onLocalLoaded) {
          this.callbacks.onLocalLoaded(this.localMedia, this.unifiedMedia);
        }

        this._notifyLoadingStateChange(
          this.phaseManager.getPhaseMessage(this.PHASES.LOCAL_COMPLETE, {
            count: this.localMedia.length,
          })
        );
      } else {
        // Transition to error phase
        if (
          !this.phaseManager.transitionToPhase(this.PHASES.ERROR, {
            context: "local_loading_error",
            error: error.message,
            duration: duration,
          })
        ) {
          console.error(
            "ProgressiveMediaLoader: Failed to transition to error phase"
          );
        }
        this.loadingStates.phase = this.PHASES.ERROR;
        this._handleLoadingError(error, "local");
        throw error;
      }
    }
  }

  /**
   * Enable user interaction after local media loads
   */
  enableUserInteraction() {
    const interactionTime = Date.now();
    this.loadingStates.userInteractionEnabled = true;
    this.performanceMetrics.timeToFirstInteraction = interactionTime;

    console.log("ProgressiveMediaLoader: User interaction enabled");

    // Notify callback
    if (this.callbacks.onUserInteractionEnabled) {
      this.callbacks.onUserInteractionEnabled({
        localMediaCount: this.localMedia.length,
        timeToInteraction: this.performanceMetrics.timeToFirstInteraction,
      });
    }

    this._notifyLoadingStateChange("Ready for user interaction");
  }

  /**
   * Load remote media in background without blocking UI
   * @param {boolean} forceRefresh - Force refresh of cached data
   * @param {Object} options - Background loading options
   */
  async loadRemoteMediaBackground(forceRefresh = false, options = {}) {
    console.log(
      "ProgressiveMediaLoader: Starting background remote media loading"
    );

    const {
      showProgressIndicators = true,
      enableSeamlessIntegration = true,
      maxBackgroundTime = 30000, // 30 seconds max for background loading
    } = options;

    // Store current state to ensure local items remain visible
    const preLoadingState = {
      localMedia: [...this.localMedia],
      unifiedMedia: [...this.unifiedMedia],
      localCount: this.localMedia.length,
      unifiedCount: this.unifiedMedia.length,
      timestamp: Date.now()
    };

    console.log(
      `ProgressiveMediaLoader: Preserving ${preLoadingState.localCount} local items during background loading`
    );

    // Mark background tasks as active
    this.loadingStates.backgroundTasksActive = true;

    if (this.callbacks.onBackgroundTasksStarted) {
      this.callbacks.onBackgroundTasksStarted({
        showProgressIndicators,
        enableSeamlessIntegration,
        maxBackgroundTime,
        preservedLocalCount: preLoadingState.localCount
      });
    }

    // Use setTimeout to ensure this runs asynchronously without blocking
    setTimeout(async () => {
      try {
        await this._performBackgroundRemoteLoading(forceRefresh, {
          showProgressIndicators,
          enableSeamlessIntegration,
          maxBackgroundTime,
          preLoadingState
        });

        // Final check to ensure local items are still visible after background loading
        const postLoadingValidation = this._validateLocalItemsPreserved(
          this.unifiedMedia,
          preLoadingState.localMedia
        );

        if (!postLoadingValidation.isValid) {
          console.error(
            'ProgressiveMediaLoader: Local items lost during background loading, performing final recovery:',
            postLoadingValidation.errors
          );
          
          // Final recovery - ensure local items are always visible
          this.unifiedMedia = this.modeConsistencyManager.preserveLocalItemsInUnified(
            preLoadingState.localMedia,
            this.remoteMedia,
            {
              enforceLocalPriority: true,
              enhanceWithRemote: true,
              validateConsistency: true
            }
          );
          
          this.loadingStates.errors.push({
            type: 'final_local_items_recovery',
            errors: postLoadingValidation.errors,
            timestamp: Date.now(),
            context: 'loadRemoteMediaBackground',
            recoveryPerformed: true,
            preLoadingState
          });

          console.log(
            `ProgressiveMediaLoader: Final recovery completed - ${this.unifiedMedia.length} items now available`
          );
        }

      } catch (error) {
        console.error(
          "ProgressiveMediaLoader: Background loading failed:",
          error
        );
        
        // Ensure local items remain visible even if remote loading fails
        if (this.unifiedMedia.length < preLoadingState.localCount) {
          console.warn(
            'ProgressiveMediaLoader: Restoring local items after background loading failure'
          );
          this.unifiedMedia = this.modeConsistencyManager.preserveExistingItems(
            preLoadingState.localMedia,
            this.unifiedMedia
          );
        }
        
        this._handleLoadingError(error, "remote");
      }
    }, 0);
  }

  /**
   * Create loading indicators for background progress
   * @param {string} phase - Current loading phase
   * @param {Object} progress - Progress information
   */
  createLoadingIndicators(phase, progress = {}) {
    // Validate phase before use and handle unknown phases
    if (
      this.phaseManager.validatePhase &&
      !this.phaseManager.validatePhase(phase)
    ) {
      console.error(
        `ProgressiveMediaLoader: Unknown phase encountered in createLoadingIndicators: "${phase}"`
      );
      // Use fallback behavior for unknown phases
      const fallbackPhase = this.handleUnknownPhase(
        phase,
        "createLoadingIndicators",
        {
          fallbackPhase: this.PHASES.ERROR,
        }
      );
      phase = fallbackPhase;
    }

    const indicators = {
      phase,
      timestamp: Date.now(),
      progress: {
        current: progress.current || 0,
        total: progress.total || 0,
        percentage:
          progress.total > 0
            ? Math.round((progress.current / progress.total) * 100)
            : 0,
      },
      message: this.phaseManager.getPhaseMessage(phase, progress),
      isVisible: this.loadingStates.backgroundTasksActive,
    };

    console.log(
      `ProgressiveMediaLoader: Loading indicator - ${indicators.message}`
    );

    // Emit progress update event
    if (this.callbacks.onLoadingStateChange) {
      this.callbacks.onLoadingStateChange(
        this.loadingStates,
        indicators.message,
        indicators
      );
    }

    return indicators;
  }

  /**
   * Seamlessly integrate remote media with existing local display
   * @param {Array} newRemoteMedia - Newly loaded remote media
   */
  seamlesslyIntegrateRemoteMedia(newRemoteMedia) {
    console.log(
      `ProgressiveMediaLoader: Seamlessly integrating ${newRemoteMedia.length} remote items`
    );

    const beforeCount = this.unifiedMedia.length;
    const localOnlyCount = this.localMedia.length;
    const previousUnified = [...this.unifiedMedia];

    try {
      // Validate mode transition before integration
      const transitionValidation = this.modeConsistencyManager.validateModeTransition(
        'local', 
        'unified', 
        this.unifiedMedia
      );

      if (!transitionValidation.isValid) {
        console.error(
          'ProgressiveMediaLoader: Mode transition validation failed during seamless integration:',
          transitionValidation.errors
        );
        
        // Log error but continue with fallback behavior
        this.loadingStates.errors.push({
          type: 'mode_transition_validation_failed',
          errors: transitionValidation.errors,
          timestamp: Date.now(),
          context: 'seamlesslyIntegrateRemoteMedia'
        });
      }

      // Use ModeConsistencyManager to merge media while preserving existing items
      const mergedMedia = this.modeConsistencyManager.mergeMediaResults(
        this.localMedia,
        newRemoteMedia,
        {
          strategy: 'additive',
          preserveLocal: true,
          enhanceLocal: true,
          deduplicateBy: 'id'
        }
      );

      // Validate that the merge preserved existing items
      const preservationValidation = this.modeConsistencyManager.validateRemoteItemsAdditive(
        this.unifiedMedia,
        newRemoteMedia
      );

      if (!preservationValidation.isValid || !preservationValidation.isAdditive) {
        console.warn(
          'ProgressiveMediaLoader: Remote items validation failed, using preservation fallback:',
          preservationValidation.errors
        );
        
        // Use preservation method as fallback
        this.unifiedMedia = this.modeConsistencyManager.preserveExistingItems(
          this.unifiedMedia,
          newRemoteMedia,
          {
            preserveAll: true,
            mergeProperties: true,
            deduplicateBy: 'id'
          }
        );
      } else {
        // Use the merged results
        this.unifiedMedia = mergedMedia;
      }

      // Final consistency validation
      const consistencyValidation = this.modeConsistencyManager.validateMediaItemConsistency(
        this.localMedia,
        newRemoteMedia,
        this.unifiedMedia
      );

      if (!consistencyValidation.isConsistent) {
        console.error(
          'ProgressiveMediaLoader: Media consistency validation failed after integration:',
          consistencyValidation.errors
        );
        
        // Implement rollback mechanism if consistency validation fails
        console.warn('ProgressiveMediaLoader: Rolling back to previous unified media state');
        this.unifiedMedia = previousUnified;
        
        this.loadingStates.errors.push({
          type: 'consistency_validation_failed',
          errors: consistencyValidation.errors,
          timestamp: Date.now(),
          context: 'seamlesslyIntegrateRemoteMedia',
          rollbackPerformed: true
        });
        
        // Still try to add new items using basic preservation
        this.unifiedMedia = this.modeConsistencyManager.preserveExistingItems(
          previousUnified,
          newRemoteMedia
        );
      }

    } catch (error) {
      console.error(
        'ProgressiveMediaLoader: Error during seamless integration, using fallback merge:',
        error
      );
      
      // Fallback to basic merge if ModeConsistencyManager fails
      this.unifiedMedia = this.mergeMediaLists(this.localMedia, newRemoteMedia);
      
      this.loadingStates.errors.push({
        type: 'seamless_integration_error',
        error: error.message,
        timestamp: Date.now(),
        context: 'seamlesslyIntegrateRemoteMedia',
        fallbackUsed: true
      });
    }

    const afterCount = this.unifiedMedia.length;
    const newItemsAdded = afterCount - beforeCount;
    const existingItemsEnhanced = beforeCount - localOnlyCount;

    console.log(
      `ProgressiveMediaLoader: Integration complete - ${newItemsAdded} new items, ${existingItemsEnhanced} enhanced items`
    );

    // Create seamless integration event
    const integrationEvent = {
      type: "seamless_integration",
      timestamp: Date.now(),
      stats: {
        beforeCount,
        afterCount,
        newItemsAdded,
        existingItemsEnhanced,
        localOnlyCount,
        remoteCount: newRemoteMedia.length,
      },
      previousUnified,
      newUnified: this.unifiedMedia,
      consistencyValidated: true,
      preservationValidated: true
    };

    // Notify callbacks about the seamless integration
    if (this.callbacks.onRemoteLoaded) {
      this.callbacks.onRemoteLoaded(
        newRemoteMedia,
        this.unifiedMedia,
        integrationEvent
      );
    }

    return integrationEvent;
  }

  /**
   * Validate that local items are preserved in the unified media list
   * @param {Array} unifiedMedia - Current unified media list
   * @param {Array} localMedia - Local media items that should be preserved
   * @returns {Object} Validation result
   * @private
   */
  _validateLocalItemsPreserved(unifiedMedia, localMedia) {
    const validation = {
      isValid: true,
      errors: [],
      warnings: [],
      stats: {
        localCount: localMedia.length,
        unifiedCount: unifiedMedia.length,
        missingLocalItems: 0,
        preservedLocalItems: 0
      },
      missingItems: [],
      timestamp: Date.now()
    };

    try {
      // Create map of unified items for quick lookup
      const unifiedMap = new Map();
      unifiedMedia.forEach(item => {
        const id = item.id || item.Id || item.ID;
        if (id) {
          unifiedMap.set(id, item);
        }
      });

      // Check that each local item exists in unified media
      localMedia.forEach(localItem => {
        const localId = localItem.id || localItem.Id || localItem.ID;
        
        if (!localId) {
          validation.warnings.push('Local item without valid ID found');
          return;
        }

        if (unifiedMap.has(localId)) {
          validation.stats.preservedLocalItems++;
        } else {
          validation.stats.missingLocalItems++;
          validation.missingItems.push({
            id: localId,
            name: localItem.name || localItem.Name || localItem.title || 'Unknown',
            item: localItem
          });
          validation.errors.push(`Local item ${localId} missing from unified media`);
        }
      });

      // Validation fails if any local items are missing
      validation.isValid = validation.stats.missingLocalItems === 0;

      if (!validation.isValid) {
        console.error(
          `ProgressiveMediaLoader: ${validation.stats.missingLocalItems} local items missing from unified media`
        );
      }

      return validation;

    } catch (error) {
      validation.errors.push(`Validation error: ${error.message}`);
      validation.isValid = false;
      console.error('ProgressiveMediaLoader: Error validating local items preservation:', error);
      return validation;
    }
  }

  /**
   * Initialize status manager integration for background monitoring
   * @private
   */
  _initializeStatusManagerIntegration() {
    if (!this.statusManager) return;

    console.log(
      "ProgressiveMediaLoader: Initializing status manager integration"
    );

    // Listen for service recovery events
    this._addStatusListener("serviceRecovered", (data) => {
      this._handleServiceRecovery(data);
    });

    // Listen for service failure events
    this._addStatusListener("serviceFailed", (data) => {
      this._handleServiceFailure(data);
    });

    // Listen for Jellyfin-specific events
    this._addStatusListener("jellyfinRecovered", (data) => {
      this._handleJellyfinRecovery(data);
    });

    this._addStatusListener("jellyfinFailed", (data) => {
      this._handleJellyfinFailure(data);
    });

    // Listen for connectivity mode changes
    this._addStatusListener("connectivityModeChange", (data) => {
      this._handleConnectivityModeChange(data);
    });

    // Listen for offline/online mode changes
    this._addStatusListener("offlineModeActivated", (data) => {
      this._handleOfflineModeActivated(data);
    });

    this._addStatusListener("localOnlyModeActivated", (data) => {
      this._handleLocalOnlyModeActivated(data);
    });
  }

  /**
   * Add status manager event listener with cleanup tracking
   * @private
   * @param {string} event - Event name
   * @param {Function} handler - Event handler
   */
  _addStatusListener(event, handler) {
    const unsubscribe = this.statusManager.on(event, handler);
    this.statusEventListeners.set(event, unsubscribe);
  }

  /**
   * Handle service recovery - attempt to reload failed media
   * @private
   * @param {Object} data - Recovery event data
   */
  async _handleServiceRecovery(data) {
    const { service } = data;
    console.log(
      `ProgressiveMediaLoader: Handling ${service} recovery`
    );

    // Clear retry attempts for this service
    this.retryAttempts.delete(service);

    // Update connectivity mode
    this._updateConnectivityMode();

    // Attempt to reload media if remote loading previously failed
    if (
      service === "jellyfin" &&
      this.loadingStates.remote.status === "error"
    ) {
      console.log(
        "ProgressiveMediaLoader: Attempting to reload remote media after Jellyfin recovery"
      );

      try {
        await this._retryRemoteMediaLoading("service_recovery");
      } catch (error) {
        console.error(
          "ProgressiveMediaLoader: Failed to reload remote media after recovery:",
          error
        );
      }
    }

    // Notify callbacks about service recovery
    this._notifyLoadingStateChange(
      `${service} service recovered - attempting to reload content`
    );
  }

  /**
   * Handle service failure - adjust loading strategy
   * @private
   * @param {Object} data - Failure event data
   */
  _handleServiceFailure(data) {
    const { service } = data;
    console.log(`ProgressiveMediaLoader: Handling ${service} failure`);

    // Update connectivity mode
    this._updateConnectivityMode();

    // Adjust loading strategy based on failed service
    if (service === "internet") {
      this.loadingStrategy = "local-only";
      this._notifyLoadingStateChange(
        "Internet connection lost - switched to local-only mode"
      );
    } else if (service === "jellyfin") {
      this.connectivityMode = "degraded";
      this._notifyLoadingStateChange(
        "Jellyfin server unavailable - continuing with local media only"
      );
    }

    // Cancel any ongoing remote loading attempts
    if (this.loadingStates.remote.status === "loading") {
      this.loadingStates.remote.status = "error";
      this.loadingStates.backgroundTasksActive = false;

      if (this.callbacks.onBackgroundTasksCompleted) {
        this.callbacks.onBackgroundTasksCompleted({
          success: false,
          reason: `${service}_failure`,
          localCount: this.localMedia.length,
          remoteCount: this.remoteMedia.length,
        });
      }
    }
  }

  /**
   * Handle Jellyfin recovery - reload remote media
   * @private
   * @param {Object} data - Recovery event data
   */
  async _handleJellyfinRecovery(data) {
    console.log("ProgressiveMediaLoader: Handling Jellyfin recovery");

    // Update connectivity mode to online
    this.connectivityMode = "online";
    this.loadingStrategy = "non-blocking";

    // Attempt to load remote media if not already loaded
    if (this.loadingStates.remote.status !== "complete") {
      console.log(
        "ProgressiveMediaLoader: Loading remote media after Jellyfin recovery"
      );

      try {
        await this.loadRemoteMediaBackground(false, {
          showProgressIndicators: true,
          enableSeamlessIntegration: true,
          recoveryMode: true,
        });

        this._notifyLoadingStateChange(
          "Jellyfin recovered - remote media loading resumed"
        );
      } catch (error) {
        console.error(
          "ProgressiveMediaLoader: Failed to load remote media after Jellyfin recovery:",
          error
        );
      }
    }
  }

  /**
   * Handle Jellyfin failure - switch to local-only mode
   * @private
   * @param {Object} data - Failure event data
   */
  _handleJellyfinFailure(data) {
    console.log("ProgressiveMediaLoader: Handling Jellyfin failure");

    // Update connectivity mode
    this.connectivityMode = "degraded";

    // Mark remote loading as failed if it was in progress
    if (this.loadingStates.remote.status === "loading") {
      this.loadingStates.remote.status = "error";
      this.loadingStates.remote.count = 0;
      this.loadingStates.errors.push({
        service: "jellyfin",
        message: "Jellyfin server unavailable",
        timestamp: Date.now(),
        recoverable: true,
      });
    }

    this._notifyLoadingStateChange(
      "Jellyfin server unavailable - continuing with local media only"
    );
  }

  /**
   * Handle connectivity mode changes
   * @private
   * @param {Object} data - Connectivity change data
   */
  _handleConnectivityModeChange(data) {
    const { newMode, oldMode } = data;
    console.log(
      `ProgressiveMediaLoader: Connectivity mode changed from ${oldMode} to ${newMode}`
    );

    this.connectivityMode = newMode;

    // Adjust loading strategy based on new connectivity mode
    switch (newMode) {
      case "online":
        this.loadingStrategy = "non-blocking";
        break;
      case "degraded":
        this.loadingStrategy = "local-first";
        break;
      case "offline":
        this.loadingStrategy = "local-only";
        break;
    }

    this._notifyLoadingStateChange(`Connectivity mode: ${newMode}`);
  }

  /**
   * Handle offline mode activation
   * @private
   * @param {Object} data - Offline mode data
   */
  _handleOfflineModeActivated(data) {
    console.log("ProgressiveMediaLoader: Offline mode activated");

    this.connectivityMode = "offline";
    this.loadingStrategy = "local-only";

    // Cancel any remote loading attempts
    if (this.loadingStates.remote.status === "loading") {
      this.loadingStates.remote.status = "error";
      this.loadingStates.backgroundTasksActive = false;
    }

    this._notifyLoadingStateChange("Offline mode - local media only");
  }

  /**
   * Handle local-only mode activation
   * @private
   * @param {Object} data - Local-only mode data
   */
  _handleLocalOnlyModeActivated(data) {
    console.log("ProgressiveMediaLoader: Local-only mode activated");

    this.connectivityMode = "degraded";
    this.loadingStrategy = "local-only";

    this._notifyLoadingStateChange(
      "Local-only mode - remote services unavailable"
    );
  }

  /**
   * Retry remote media loading with exponential backoff
   * @private
   * @param {string} reason - Reason for retry
   */
  async _retryRemoteMediaLoading(reason = "manual") {
    const service = "jellyfin";
    const currentAttempts = this.retryAttempts.get(service) || 0;

    if (currentAttempts >= this.retryConfig.maxRetries) {
      console.log(
        `ProgressiveMediaLoader: Max retry attempts (${this.retryConfig.maxRetries}) reached for ${service}`
      );
      return;
    }

    // Calculate delay with exponential backoff
    const delay = this.retryConfig.exponentialBackoff
      ? this.retryConfig.retryDelay * Math.pow(2, currentAttempts)
      : this.retryConfig.retryDelay;

    console.log(
      `ProgressiveMediaLoader: Retrying remote media loading (attempt ${
        currentAttempts + 1
      }/${this.retryConfig.maxRetries}) after ${delay}ms delay`
    );

    // Update retry attempts
    this.retryAttempts.set(service, currentAttempts + 1);

    // Wait for delay
    await new Promise((resolve) => setTimeout(resolve, delay));

    try {
      // Reset remote loading state
      this.loadingStates.remote.status = "loading";
      this.loadingStates.backgroundTasksActive = true;

      // Attempt to load remote media
      await this._performBackgroundRemoteLoading(false, {
        showProgressIndicators: true,
        enableSeamlessIntegration: true,
        retryMode: true,
        retryAttempt: currentAttempts + 1,
        retryReason: reason,
      });

      // Clear retry attempts on success
      this.retryAttempts.delete(service);

      console.log(
        `ProgressiveMediaLoader: Remote media loading retry successful`
      );
    } catch (error) {
      console.error(
        `ProgressiveMediaLoader: Remote media loading retry failed:`,
        error
      );

      // Schedule next retry if within limits
      if (currentAttempts + 1 < this.retryConfig.maxRetries) {
        setTimeout(() => {
          this._retryRemoteMediaLoading(reason);
        }, delay);
      } else {
        // Max retries reached, mark as permanently failed
        this.loadingStates.remote.status = "error";
        this.loadingStates.backgroundTasksActive = false;
        this.loadingStates.errors.push({
          service,
          message: `Max retry attempts reached (${this.retryConfig.maxRetries})`,
          timestamp: Date.now(),
          recoverable: false,
        });
      }
    }
  }

  /**
   * Update connectivity mode based on current service status
   * @private
   */
  _updateConnectivityMode() {
    if (!this.statusManager) return;

    const internetStatus = this.statusManager.getStatus("internet");
    const jellyfinStatus = this.statusManager.getStatus("jellyfin");

    if (internetStatus?.connected && jellyfinStatus?.connected) {
      this.connectivityMode = "online";
      this.loadingStrategy = "non-blocking";
    } else if (internetStatus?.connected && !jellyfinStatus?.connected) {
      this.connectivityMode = "degraded";
      this.loadingStrategy = "local-first";
    } else {
      this.connectivityMode = "offline";
      this.loadingStrategy = "local-only";
    }

    console.log(
      `ProgressiveMediaLoader: Updated connectivity mode to ${this.connectivityMode}, strategy: ${this.loadingStrategy}`
    );
  }

  /**
   * Enable seamless service recovery without user intervention
   * @param {boolean} enabled - Whether to enable seamless recovery
   */
  enableSeamlessServiceRecovery(enabled = true) {
    this.retryConfig.retryOnServiceRecovery = enabled;

    console.log(
      `ProgressiveMediaLoader: Seamless service recovery ${
        enabled ? "enabled" : "disabled"
      }`
    );

    if (enabled && this.statusManager) {
      // Ensure we're listening for recovery events
      if (!this.statusEventListeners.has("serviceRecovered")) {
        this._addStatusListener("serviceRecovered", (data) => {
          this._handleServiceRecovery(data);
        });
      }
    }
  }

  /**
   * Configure automatic retry behavior
   * @param {Object} config - Retry configuration
   */
  configureAutoRetry(config = {}) {
    this.retryConfig = {
      ...this.retryConfig,
      ...config,
    };

    console.log(
      "ProgressiveMediaLoader: Auto-retry configured:",
      this.retryConfig
    );
  }

  /**
   * Get current loading status with service integration info
   * @returns {Object} Enhanced loading status
   */
  getLoadingStatus() {
    const baseStatus = {
      ...this.loadingStates,
      connectivityMode: this.connectivityMode,
      loadingStrategy: this.loadingStrategy,
      performanceMetrics: this.performanceMetrics,
    };

    // Add service status if available
    if (this.statusManager) {
      baseStatus.serviceStatus = {
        internet: this.statusManager.getStatus("internet"),
        jellyfin: this.statusManager.getStatus("jellyfin"),
        vlc: this.statusManager.getStatus("vlc"),
        localMedia: this.statusManager.getStatus("localMedia"),
      };
    }

    // Add retry information
    baseStatus.retryInfo = {
      config: this.retryConfig,
      attempts: Object.fromEntries(this.retryAttempts),
    };

    return baseStatus;
  }

  /**
   * Cleanup status manager integration
   */
  destroy() {
    console.log(
      "ProgressiveMediaLoader: Cleaning up status manager integration"
    );

    // Remove all status event listeners
    this.statusEventListeners.forEach((unsubscribe, event) => {
      try {
        unsubscribe();
      } catch (error) {
        console.warn(
          `ProgressiveMediaLoader: Error removing listener for ${event}:`,
          error
        );
      }
    });

    this.statusEventListeners.clear();
    this.retryAttempts.clear();
  }

  /**
   * Load local media fast without file validation (for immediate display)
   */
  async loadLocalMediaFast() {
    console.log("ProgressiveMediaLoader: Loading local media fast (no validation)");

    try {
      const params = new URLSearchParams();
      params.append("mode", "local");
      params.append("validate_files", "false"); // Explicitly disable validation for speed

      const url = `/api/media?${params.toString()}`;
      const response = await fetch(url);

      if (!response.ok) {
        throw new Error(
          `Local media API error: ${response.status} ${response.statusText}`
        );
      }

      const data = await response.json();
      this.localMedia = data.media || [];

      console.log(
        `ProgressiveMediaLoader: Loaded ${this.localMedia.length} local media items (fast mode)`
      );

      // Update unified media list with local items
      this.unifiedMedia = [...this.localMedia];

      // Notify callback
      if (this.callbacks.onLocalLoaded) {
        this.callbacks.onLocalLoaded(this.localMedia, this.unifiedMedia);
      }

      return this.localMedia;
    } catch (error) {
      console.error(
        "ProgressiveMediaLoader: Error loading local media (fast mode):",
        error
      );

      // Try to load from cache if available
      const cachedLocal = this._loadLocalFromCache();
      if (cachedLocal.length > 0) {
        this.localMedia = cachedLocal;
        this.unifiedMedia = [...this.localMedia];
        console.log(
          `ProgressiveMediaLoader: Loaded ${cachedLocal.length} local items from cache (fast mode)`
        );

        if (this.callbacks.onLocalLoaded) {
          this.callbacks.onLocalLoaded(this.localMedia, this.unifiedMedia);
        }

        return this.localMedia;
      }

      throw error;
    }
  }

  /**
   * Load local media with file validation
   * @param {boolean} forceRefresh - Force refresh of cached data
   */
  async loadLocalMedia(forceRefresh = false) {
    console.log("ProgressiveMediaLoader: Loading local media");

    try {
      const params = new URLSearchParams();
      if (forceRefresh) {
        params.append("validate_files", "true");
      }

      params.append("mode", "local");
      const url = `/api/media?${params.toString()}`;
      const response = await fetch(url);

      if (!response.ok) {
        throw new Error(
          `Local media API error: ${response.status} ${response.statusText}`
        );
      }

      const data = await response.json();
      this.localMedia = data.media || [];

      console.log(
        `ProgressiveMediaLoader: Loaded ${this.localMedia.length} local media items`
      );

      // Update unified media list with local items
      this.unifiedMedia = [...this.localMedia];

      // Notify callback
      if (this.callbacks.onLocalLoaded) {
        this.callbacks.onLocalLoaded(this.localMedia, this.unifiedMedia);
      }

      return this.localMedia;
    } catch (error) {
      console.error(
        "ProgressiveMediaLoader: Error loading local media:",
        error
      );

      // Try to load from cache if available
      const cachedLocal = this._loadLocalFromCache();
      if (cachedLocal.length > 0) {
        this.localMedia = cachedLocal;
        this.unifiedMedia = [...this.localMedia];

        if (this.callbacks.onLocalLoaded) {
          this.callbacks.onLocalLoaded(this.localMedia, this.unifiedMedia);
        }

        console.log(
          `ProgressiveMediaLoader: Loaded ${cachedLocal.length} local items from cache`
        );
        return this.localMedia;
      }

      throw error;
    }
  }

  /**
   * Load unified media from the backend (properly merged)
   * @param {boolean} forceRefresh - Force refresh of cached data
   */
  async loadUnifiedMedia(forceRefresh = false) {
    console.log("ProgressiveMediaLoader: Loading unified media");

    try {
      const params = new URLSearchParams();
      params.append("mode", "unified");
      if (forceRefresh) {
        params.append("force_refresh", "true");
        params.append("validate_files", "true");
      }

      const url = `/api/media?${params.toString()}`;
      const response = await fetch(url);

      if (!response.ok) {
        throw new Error(
          `Unified media API error: ${response.status} ${response.statusText}`
        );
      }

      const data = await response.json();
      this.unifiedMedia = data.media || [];

      // Extract local and remote items for compatibility
      this.localMedia = this.unifiedMedia.filter((item) => item.has_local);
      this.remoteMedia = this.unifiedMedia.filter((item) => item.has_remote);

      console.log(
        `ProgressiveMediaLoader: Loaded ${this.unifiedMedia.length} unified media items (${this.localMedia.length} local, ${this.remoteMedia.length} remote)`
      );

      // Cache the unified data
      this._cacheUnifiedMedia(this.unifiedMedia);

      // Notify callback
      if (this.callbacks.onRemoteLoaded) {
        this.callbacks.onRemoteLoaded(this.remoteMedia, this.unifiedMedia);
      }

      return this.unifiedMedia;
    } catch (error) {
      console.error(
        "ProgressiveMediaLoader: Error loading unified media:",
        error
      );

      // Try to load from cache if available
      const cachedUnified = this._loadUnifiedFromCache();
      if (cachedUnified.length > 0) {
        this.unifiedMedia = cachedUnified;
        this.localMedia = this.unifiedMedia.filter((item) => item.has_local);
        this.remoteMedia = this.unifiedMedia.filter((item) => item.has_remote);

        if (this.callbacks.onRemoteLoaded) {
          this.callbacks.onRemoteLoaded(this.remoteMedia, this.unifiedMedia);
        }

        console.log(
          `ProgressiveMediaLoader: Loaded ${cachedUnified.length} unified items from cache`
        );
        return this.unifiedMedia;
      }

      // If unified loading fails, fall back to local-only mode
      console.warn(
        "ProgressiveMediaLoader: Unified loading failed, continuing with local-only mode"
      );
      this.unifiedMedia = [...this.localMedia];

      if (this.callbacks.onError) {
        this.callbacks.onError(
          new Error("Remote media unavailable - local-only mode")
        );
      }

      return this.unifiedMedia;
    }
  }

  /**
   * Load remote media from Jellyfin (kept for compatibility)
   * @param {boolean} forceRefresh - Force refresh of cached data
   */
  async loadRemoteMedia(forceRefresh = false) {
    console.log("ProgressiveMediaLoader: Loading remote media");

    try {
      const params = new URLSearchParams();
      if (forceRefresh) {
        params.append("force_refresh", "true");
      }

      const url = `/api/media/remote${
        params.toString() ? "?" + params.toString() : ""
      }`;
      const response = await fetch(url);

      if (!response.ok) {
        throw new Error(
          `Remote media API error: ${response.status} ${response.statusText}`
        );
      }

      const data = await response.json();
      this.remoteMedia = data.media || [];

      console.log(
        `ProgressiveMediaLoader: Loaded ${this.remoteMedia.length} remote media items`
      );

      // Merge with local media
      this.unifiedMedia = this.mergeMediaLists(
        this.localMedia,
        this.remoteMedia
      );

      // Cache remote data
      this._cacheRemoteMedia(this.remoteMedia);

      // Notify callback
      if (this.callbacks.onRemoteLoaded) {
        this.callbacks.onRemoteLoaded(this.remoteMedia, this.unifiedMedia);
      }

      return this.remoteMedia;
    } catch (error) {
      console.error(
        "ProgressiveMediaLoader: Error loading remote media:",
        error
      );

      // Try to load from cache if available
      const cachedRemote = this._loadRemoteFromCache();
      if (cachedRemote.length > 0) {
        this.remoteMedia = cachedRemote;
        this.unifiedMedia = this.mergeMediaLists(
          this.localMedia,
          this.remoteMedia
        );

        if (this.callbacks.onRemoteLoaded) {
          this.callbacks.onRemoteLoaded(this.remoteMedia, this.unifiedMedia);
        }

        console.log(
          `ProgressiveMediaLoader: Loaded ${cachedRemote.length} remote items from cache`
        );
        return this.remoteMedia;
      }

      // If remote loading fails, continue with local-only mode
      console.warn(
        "ProgressiveMediaLoader: Remote loading failed, continuing with local-only mode"
      );

      if (this.callbacks.onError) {
        this.callbacks.onError(
          new Error("Remote media unavailable - local-only mode")
        );
      }

      return [];
    }
  }

  /**
   * Merge local and remote media lists, avoiding duplicates
   * @param {Array} localMedia - Array of local media items
   * @param {Array} remoteMedia - Array of remote media items
   * @returns {Array} Merged and deduplicated media list
   */
  mergeMediaLists(localMedia, remoteMedia) {
    console.log(
      `ProgressiveMediaLoader: Merging ${localMedia.length} local and ${remoteMedia.length} remote items`
    );

    // Create a map of local media by ID for quick lookup
    const localMediaMap = new Map();
    localMedia.forEach((item) => {
      localMediaMap.set(item.id, item);
    });

    // Start with local media
    const merged = [...localMedia];

    // Add remote media, updating local items or adding new ones
    remoteMedia.forEach((remoteItem) => {
      const localItem = localMediaMap.get(remoteItem.id);

      if (localItem) {
        // Update existing local item with remote information
        const mergedItem = {
          ...localItem,
          ...remoteItem,
          // Preserve local-specific fields
          has_local: localItem.has_local || false,
          local_path: localItem.local_path || null,
          file_validated: localItem.file_validated || false,
          validation_timestamp: localItem.validation_timestamp || 0,
          // Update availability based on both sources
          has_remote: true,
          availability: localItem.has_local ? "both" : "remote_only",
        };

        // Replace the local item in the merged array
        const index = merged.findIndex((item) => item.id === remoteItem.id);
        if (index !== -1) {
          merged[index] = mergedItem;
        }
      } else {
        // Add new remote-only item
        const newItem = {
          ...remoteItem,
          has_local: false,
          has_remote: true,
          availability: "remote_only",
        };
        merged.push(newItem);
      }
    });

    console.log(
      `ProgressiveMediaLoader: Merged result contains ${merged.length} total items`
    );
    return merged;
  }

  /**
   * Get current loading state with enhanced information
   * @returns {Object} Current loading states
   */
  getLoadingState() {
    return {
      ...this.loadingStates,
      connectivityMode: this.connectivityMode,
      loadingStrategy: this.loadingStrategy,
      performanceMetrics: { ...this.performanceMetrics },
    };
  }

  /**
   * Get current media data
   * @returns {Object} Object containing local, remote, and unified media arrays
   */
  getMediaData() {
    return {
      local: [...this.localMedia],
      remote: [...this.remoteMedia],
      unified: [...this.unifiedMedia],
    };
  }

  /**
   * Check if user interaction is enabled
   * @returns {boolean} True if user can interact with the interface
   */
  isUserInteractionEnabled() {
    return this.loadingStates.userInteractionEnabled;
  }

  /**
   * Check if background tasks are active
   * @returns {boolean} True if background loading is in progress
   */
  areBackgroundTasksActive() {
    return this.loadingStates.backgroundTasksActive;
  }

  /**
   * Get performance metrics
   * @returns {Object} Performance timing information
   */
  getPerformanceMetrics() {
    return { ...this.performanceMetrics };
  }

  /**
   * Disable user interaction (for testing or special cases)
   */
  disableUserInteraction() {
    this.loadingStates.userInteractionEnabled = false;
    console.log("ProgressiveMediaLoader: User interaction disabled");

    this._notifyLoadingStateChange("User interaction disabled");
  }

  /**
   * Set status manager for integration
   * @param {StatusManager} statusManager - Status manager instance
   */
  setStatusManager(statusManager) {
    // Clean up existing integration
    if (this.statusManager) {
      this._cleanupStatusManagerIntegration();
    }

    this.statusManager = statusManager;

    if (this.statusManager) {
      this._initializeStatusManagerIntegration();
      console.log(
        "ProgressiveMediaLoader: Status manager integration initialized"
      );
    }
  }

  /**
   * Handle status manager events for loading decisions
   * @param {string} event - Event name
   * @param {Object} data - Event data
   */
  onStatusChange(event, data) {
    console.log(
      `ProgressiveMediaLoader: Handling status event: ${event}`,
      data
    );

    switch (event) {
      case "connectivityModeChange":
        this._handleConnectivityModeChange(data);
        break;
      case "internet:connected":
        this._handleInternetConnected(data);
        break;
      case "internet:disconnected":
        this._handleInternetDisconnected(data);
        break;
      case "jellyfin:connected":
        this._handleJellyfinConnected(data);
        break;
      case "jellyfin:disconnected":
        this._handleJellyfinDisconnected(data);
        break;
      case "statusChange":
        this._handleGeneralStatusChange(data);
        break;
      default:
        console.log(
          `ProgressiveMediaLoader: Unhandled status event: ${event}`
        );
    }
  }

  /**
   * Implement status-aware loading strategies
   * @param {string} mode - Connectivity mode ('online', 'offline', 'degraded')
   * @param {Object} options - Loading options
   */
  adjustLoadingStrategy(mode, options = {}) {
    console.log(
      `ProgressiveMediaLoader: Adjusting loading strategy for ${mode} mode`
    );

    const previousStrategy = this.loadingStrategy;
    this.connectivityMode = mode;

    switch (mode) {
      case "online":
        this.loadingStrategy = "non-blocking";
        this._enableFullFunctionality();
        break;
      case "degraded":
        this.loadingStrategy = "local-priority";
        this._enableLimitedFunctionality();
        break;
      case "offline":
        this.loadingStrategy = "local-only";
        this._enableOfflineMode();
        break;
      default:
        console.warn(
          `ProgressiveMediaLoader: Unknown connectivity mode: ${mode}`
        );
        this.loadingStrategy = "local-only";
        this._enableOfflineMode();
    }

    if (previousStrategy !== this.loadingStrategy) {
      console.log(
        `ProgressiveMediaLoader: Loading strategy changed from ${previousStrategy} to ${this.loadingStrategy}`
      );
      this._notifyLoadingStateChange(
        `Loading strategy adjusted to ${this.loadingStrategy} mode`
      );
    }
  }

  /**
   * Handle service unavailability scenarios with appropriate fallbacks
   * @param {string} service - Service name that became unavailable
   * @param {Object} error - Error information
   */
  handleServiceUnavailability(service, error) {
    console.log(
      `ProgressiveMediaLoader: Handling ${service} unavailability:`,
      error
    );

    const errorInfo = {
      service,
      error: error.message || "Service unavailable",
      timestamp: Date.now(),
      recoverable: this._isRecoverableError(error),
    };

    this.loadingStates.errors.push(errorInfo);

    switch (service) {
      case "internet":
        this._handleInternetUnavailable(errorInfo);
        break;
      case "jellyfin":
        this._handleJellyfinUnavailable(errorInfo);
        break;
      case "localMedia":
        this._handleLocalMediaUnavailable(errorInfo);
        break;
      default:
        console.warn(
          `ProgressiveMediaLoader: Unknown service unavailable: ${service}`
        );
    }

    // Notify error callback
    if (this.callbacks.onError) {
      this.callbacks.onError(error, errorInfo);
    }
  }

  /**
   * Display clear error messages for service unavailability
   * @param {Object} errorInfo - Error information object
   */
  displayServiceUnavailabilityMessage(errorInfo) {
    const { service, error, recoverable } = errorInfo;

    // Get user-friendly error message
    const userFriendlyError = this.statusManager
      ? this.statusManager.getUserFriendlyError(service, { message: error })
      : this._getDefaultErrorMessage(service, error);

    // Create error notification element
    const errorNotification = this._createErrorNotification(userFriendlyError);

    // Display the notification
    this._showErrorNotification(errorNotification);

    // Update loading indicators with error state
    this._updateLoadingIndicatorsForError(service, userFriendlyError);

    console.log(
      `ProgressiveMediaLoader: Displayed error message for ${service}:`,
      userFriendlyError
    );
  }

  /**
   * Create user feedback for background loading progress
   * @param {string} phase - Current loading phase
   * @param {Object} progress - Progress information
   * @param {Object} options - Display options
   */
  createBackgroundLoadingFeedback(phase, progress = {}, options = {}) {
    const {
      showDetailedProgress = true,
      showTimeEstimates = true,
      showServiceStatus = true,
    } = options;

    const feedback = {
      phase,
      timestamp: Date.now(),
      progress: {
        current: progress.current || 0,
        total: progress.total || 0,
        percentage:
          progress.total > 0
            ? Math.round((progress.current / progress.total) * 100)
            : 0,
      },
      message: this.phaseManager.getPhaseMessage(phase, progress),
      detailedMessage: showDetailedProgress
        ? this._getDetailedProgressMessage(phase, progress)
        : null,
      timeEstimate: showTimeEstimates
        ? this._getTimeEstimate(phase, progress)
        : null,
      serviceStatus: showServiceStatus ? this._getCurrentServiceStatus() : null,
      isBackgroundTask: true,
      userCanInteract: this.loadingStates.userInteractionEnabled,
    };

    // Update UI with feedback
    this._updateBackgroundProgressUI(feedback);

    // Emit progress event
    if (this.callbacks.onLoadingStateChange) {
      this.callbacks.onLoadingStateChange(
        this.loadingStates,
        feedback.message,
        feedback
      );
    }

    console.log(
      `ProgressiveMediaLoader: Background loading feedback - ${feedback.message}`
    );
    return feedback;
  }

  /**
   * Show offline mode indicators and enable offline functionality
   */
  enableOfflineModeIndicators() {
    console.log(
      "ProgressiveMediaLoader: Enabling offline mode indicators"
    );

    // Update connectivity mode
    this.connectivityMode = "offline";
    this.loadingStrategy = "local-only";

    // Create offline mode notification
    const offlineNotification = {
      type: "offline_mode",
      title: "Offline Mode Active",
      message: "You're currently offline. Only local media is available.",
      icon: "📱",
      severity: "info",
      persistent: true,
      actions: [
        {
          label: "Retry Connection",
          action: () => this._retryConnection(),
          primary: true,
        },
        {
          label: "Continue Offline",
          action: () => this._dismissOfflineNotification(),
          secondary: true,
        },
      ],
    };

    // Display offline mode UI elements
    this._showOfflineModeUI(offlineNotification);

    // Update status indicators
    this._updateStatusIndicatorsForOfflineMode();

    // Disable features that require internet
    this._disableOnlineFeatures();

    // Notify callbacks
    if (this.callbacks.onLoadingStateChange) {
      this.callbacks.onLoadingStateChange(
        this.loadingStates,
        "Offline mode active - local media only"
      );
    }
  }

  /**
   * Handle recovery from offline mode
   */
  handleOfflineModeRecovery() {
    console.log(
      "ProgressiveMediaLoader: Handling offline mode recovery"
    );

    // Update connectivity mode
    this.connectivityMode = "online";
    this.loadingStrategy = "non-blocking";

    // Hide offline mode indicators
    this._hideOfflineModeUI();

    // Re-enable online features
    this._enableOnlineFeatures();

    // Start background loading of remote media
    this.loadRemoteMediaBackground(true);

    // Show recovery notification
    const recoveryNotification = {
      type: "connection_restored",
      title: "Connection Restored",
      message: "Internet connection is back. Loading remote media...",
      icon: "🌐",
      severity: "success",
      autoHide: true,
      duration: 3000,
    };

    this._showNotification(recoveryNotification);

    // Notify callbacks
    if (this.callbacks.onLoadingStateChange) {
      this.callbacks.onLoadingStateChange(
        this.loadingStates,
        "Connection restored - loading remote media"
      );
    }
  }

  /**
   * Clear all cached data
   */
  clearCache() {
    try {
      localStorage.removeItem("progressiveLoader_localMedia");
      localStorage.removeItem("progressiveLoader_remoteMedia");
      localStorage.removeItem("progressiveLoader_unifiedMedia");
      console.log("ProgressiveMediaLoader: Cache cleared");
    } catch (error) {
      console.warn("ProgressiveMediaLoader: Error clearing cache:", error);
    }
  }

  /**
   * Perform background remote loading
   * @param {boolean} forceRefresh - Force refresh of cached data
   * @param {Object} options - Loading options
   * @private
   */
  async _performBackgroundRemoteLoading(forceRefresh, options) {
    const startTime = Date.now();

    // Transition to loading_remote phase with validation
    this.safeTransitionToPhase(this.PHASES.LOADING_REMOTE_DATA, {
      context: "_performBackgroundRemoteLoading",
    });
    this.loadingStates.phase = this.PHASES.LOADING_REMOTE_DATA;
    this.loadingStates.remote.status = "loading";
    this.loadingStates.remote.startTime = startTime;

    try {
      // Show background progress indicator with phase validation
      if (options.showProgressIndicators) {
        this.safeTransitionToPhase(this.PHASES.CHECKING_CONNECTIVITY, {
          context: "background_loading",
        });
        this.createLoadingIndicators(this.PHASES.CHECKING_CONNECTIVITY, {
          current: 0,
          total: 2,
        });
      }

      // Check if we have internet connectivity
      if (this.statusManager) {
        const internetStatus = this.statusManager.getStatus("internet");
        if (!internetStatus?.connected) {
          throw new Error("No internet connection available");
        }
      }

      // Load remote media with progress tracking
      if (options.showProgressIndicators) {
        this.createLoadingIndicators(this.PHASES.LOADING_REMOTE_DATA, {
          current: 1,
          total: 2,
        });
      }

      const remoteMedia = await this.loadUnifiedMedia(forceRefresh);

      // Seamlessly integrate if enabled
      if (options.enableSeamlessIntegration && remoteMedia.length > 0) {
        if (options.showProgressIndicators) {
          this.createLoadingIndicators(this.PHASES.MERGING_MEDIA, {
            current: 2,
            total: 2,
          });
        }

        this.seamlesslyIntegrateRemoteMedia(remoteMedia);
      }

      // Mark background tasks as complete with phase transition
      const duration = Date.now() - startTime;
      this.loadingStates.backgroundTasksActive = false;
      this.loadingStates.remote.status = "complete";
      this.loadingStates.remote.duration = duration;
      this.loadingStates.remote.count = remoteMedia.length;

      // Transition to unified_complete phase
      this.safeTransitionToPhase(this.PHASES.UNIFIED_COMPLETE, {
        context: "background_loading_complete",
        remoteCount: remoteMedia.length,
        totalCount: this.unifiedMedia.length,
      });
      this.loadingStates.phase = this.PHASES.UNIFIED_COMPLETE;

      this.performanceMetrics.timeToRemoteComplete = duration;
      this.performanceMetrics.timeToFullComplete = Date.now();

      console.log(
        `ProgressiveMediaLoader: Background loading completed in ${duration}ms`
      );

      // Notify completion
      if (this.callbacks.onBackgroundTasksCompleted) {
        this.callbacks.onBackgroundTasksCompleted({
          duration,
          remoteCount: remoteMedia.length,
          totalCount: this.unifiedMedia.length,
        });
      }

      // Hide progress indicator
      if (options.showProgressIndicators) {
        this.createLoadingIndicators(this.PHASES.COMPLETE, {
          current: 2,
          total: 2,
        });
        setTimeout(() => {
          if (window.hideBackgroundProgress) {
            window.hideBackgroundProgress();
          }
        }, 2000);
      }
    } catch (error) {
      const duration = Date.now() - startTime;
      this.loadingStates.backgroundTasksActive = false;
      this.loadingStates.remote.status = "error";
      this.loadingStates.remote.duration = duration;

      console.error(
        `ProgressiveMediaLoader: Background loading failed after ${duration}ms:`,
        error
      );

      // Transition to error phase
      if (
        !this.phaseManager.transitionToPhase(this.PHASES.ERROR, {
          context: "background_loading_error",
          error: error.message,
          duration: duration,
        })
      ) {
        console.error(
          "ProgressiveMediaLoader: Failed to transition to error phase"
        );
      }
      this.loadingStates.phase = this.PHASES.ERROR;

      // Handle the error appropriately
      this.handleServiceUnavailability("jellyfin", error);

      // Hide progress indicator
      if (options.showProgressIndicators && window.hideBackgroundProgress) {
        setTimeout(() => window.hideBackgroundProgress(), 1000);
      }

      throw error;
    }
  }

  /**
   * Load local media from cache
   * @returns {Array} Cached local media items
   * @private
   */
  _loadLocalFromCache() {
    try {
      const cached = localStorage.getItem("progressiveLoader_localMedia");
      if (cached) {
        const data = JSON.parse(cached);
        const age = Date.now() - (data.timestamp || 0);

        // Use cache if less than 5 minutes old
        if (age < 300000) {
          return data.media || [];
        }
      }
    } catch (error) {
      console.warn(
        "ProgressiveMediaLoader: Error loading local cache:",
        error
      );
    }
    return [];
  }

  /**
   * Load remote media from cache
   * @returns {Array} Cached remote media items
   * @private
   */
  _loadRemoteFromCache() {
    try {
      const cached = localStorage.getItem("progressiveLoader_remoteMedia");
      if (cached) {
        const data = JSON.parse(cached);
        const age = Date.now() - (data.timestamp || 0);

        // Use cache if less than 10 minutes old
        if (age < 600000) {
          return data.media || [];
        }
      }
    } catch (error) {
      console.warn(
        "ProgressiveMediaLoader: Error loading remote cache:",
        error
      );
    }
    return [];
  }

  /**
   * Load unified media from cache
   * @returns {Array} Cached unified media items
   * @private
   */
  _loadUnifiedFromCache() {
    try {
      const cached = localStorage.getItem("progressiveLoader_unifiedMedia");
      if (cached) {
        const data = JSON.parse(cached);
        const age = Date.now() - (data.timestamp || 0);

        // Use cache if less than 10 minutes old
        if (age < 600000) {
          return data.media || [];
        }
      }
    } catch (error) {
      console.warn(
        "ProgressiveMediaLoader: Error loading unified cache:",
        error
      );
    }
    return [];
  }

  /**
   * Cache local media data
   * @param {Array} media - Media items to cache
   * @private
   */
  _cacheLocalMedia(media) {
    try {
      localStorage.setItem(
        "progressiveLoader_localMedia",
        JSON.stringify({
          media,
          timestamp: Date.now(),
        })
      );
    } catch (error) {
      console.warn(
        "ProgressiveMediaLoader: Error caching local media:",
        error
      );
    }
  }

  /**
   * Cache remote media data
   * @param {Array} media - Media items to cache
   * @private
   */
  _cacheRemoteMedia(media) {
    try {
      localStorage.setItem(
        "progressiveLoader_remoteMedia",
        JSON.stringify({
          media,
          timestamp: Date.now(),
        })
      );
    } catch (error) {
      console.warn(
        "ProgressiveMediaLoader: Error caching remote media:",
        error
      );
    }
  }

  /**
   * Cache unified media data
   * @param {Array} media - Media items to cache
   * @private
   */
  _cacheUnifiedMedia(media) {
    try {
      localStorage.setItem(
        "progressiveLoader_unifiedMedia",
        JSON.stringify({
          media,
          timestamp: Date.now(),
        })
      );
    } catch (error) {
      console.warn(
        "ProgressiveMediaLoader: Error caching unified media:",
        error
      );
    }
  }

  // Private methods

  /**
   * Get default error message when status manager is not available
   * @param {string} service - Service name
   * @param {string} error - Error message
   * @returns {Object} Default error information
   * @private
   */
  _getDefaultErrorMessage(service, error) {
    const defaultMessages = {
      internet: {
        title: "Internet Connection Lost",
        message:
          "Unable to connect to the internet. Local media is still available.",
        icon: "🌐",
        severity: "warning",
      },
      jellyfin: {
        title: "Remote Server Unavailable",
        message:
          "Cannot connect to remote media server. Using local media only.",
        icon: "📺",
        severity: "warning",
      },
      localMedia: {
        title: "Local Media Error",
        message: "Unable to load local media files.",
        icon: "💾",
        severity: "error",
      },
    };

    return (
      defaultMessages[service] || {
        title: "Service Error",
        message: `${service} is currently unavailable.`,
        icon: "⚠️",
        severity: "warning",
      }
    );
  }

  /**
   * Create error notification element
   * @param {Object} errorInfo - Error information
   * @returns {HTMLElement} Error notification element
   * @private
   */
  _createErrorNotification(errorInfo) {
    const notification = document.createElement("div");
    notification.className = `error-notification severity-${errorInfo.severity}`;
    notification.innerHTML = `
            <div class="error-icon">${errorInfo.icon}</div>
            <div class="error-content">
                <div class="error-title">${errorInfo.title}</div>
                <div class="error-message">${errorInfo.message}</div>
                ${
                  errorInfo.suggestions
                    ? `
                    <div class="error-suggestions">
                        <ul>
                            ${errorInfo.suggestions
                              .map((suggestion) => `<li>${suggestion}</li>`)
                              .join("")}
                        </ul>
                    </div>
                `
                    : ""
                }
            </div>
            <div class="error-actions">
                ${
                  errorInfo.recoverable
                    ? `
                    <button class="btn-retry" onclick="this.closest('.error-notification').dispatchEvent(new CustomEvent('retry'))">
                        Retry
                    </button>
                `
                    : ""
                }
                <button class="btn-dismiss" onclick="this.closest('.error-notification').dispatchEvent(new CustomEvent('dismiss'))">
                    Dismiss
                </button>
            </div>
        `;

    // Add event listeners
    notification.addEventListener("retry", () =>
      this._retryService(errorInfo.service)
    );
    notification.addEventListener("dismiss", () =>
      this._dismissErrorNotification(notification)
    );

    return notification;
  }

  /**
   * Show error notification to user
   * @param {HTMLElement} notification - Notification element
   * @private
   */
  _showErrorNotification(notification) {
    let container = document.getElementById("errorNotificationContainer");
    if (!container) {
      container = document.createElement("div");
      container.id = "errorNotificationContainer";
      container.className = "error-notification-container";
      document.body.appendChild(container);
    }

    container.appendChild(notification);

    // Animate in
    setTimeout(() => notification.classList.add("show"), 100);
  }

  /**
   * Update loading indicators to show error state
   * @param {string} service - Service that failed
   * @param {Object} errorInfo - Error information
   * @private
   */
  _updateLoadingIndicatorsForError(service, errorInfo) {
    const progressElement = document.getElementById(`${service}Progress`);
    if (progressElement) {
      progressElement.className = "progress-status error";
      progressElement.textContent = "Error";
      progressElement.title = errorInfo.message;
    }

    // Update main loading text if this is a critical error
    if (service === "localMedia") {
      const loadingText = document.getElementById("loadingText");
      if (loadingText) {
        loadingText.textContent = "Error loading media library";
        loadingText.className = "error-state";
      }
    }
  }

  /**
   * Get detailed progress message for background loading
   * @param {string} phase - Current phase
   * @param {Object} progress - Progress information
   * @returns {string} Detailed progress message
   * @private
   */
  _getDetailedProgressMessage(phase, progress) {
    switch (phase) {
      case this.PHASES.LOADING_REMOTE:
        return `Loading remote media... (${progress.current || 0}/${
          progress.total || 0
        } items)`;
      case this.PHASES.CHECKING_SERVICES:
        return "Checking remote service availability...";
      case this.PHASES.MERGING_MEDIA:
        return "Integrating remote media with local library...";
      case this.PHASES.COMPLETE:
        return `Loading complete - ${progress.total || 0} items available`;
      default:
        return "Processing...";
    }
  }

  /**
   * Get time estimate for current operation
   * @param {string} phase - Current phase
   * @param {Object} progress - Progress information
   * @returns {string|null} Time estimate
   * @private
   */
  _getTimeEstimate(phase, progress) {
    if (!progress.startTime) return null;

    const elapsed = Date.now() - progress.startTime;
    const rate = progress.current / elapsed;
    const remaining = progress.total - progress.current;

    if (rate > 0 && remaining > 0) {
      const estimatedMs = remaining / rate;
      const estimatedSeconds = Math.ceil(estimatedMs / 1000);

      if (estimatedSeconds < 60) {
        return `~${estimatedSeconds} seconds remaining`;
      } else {
        const minutes = Math.ceil(estimatedSeconds / 60);
        return `~${minutes} minute${minutes > 1 ? "s" : ""} remaining`;
      }
    }

    return null;
  }

  /**
   * Get current service status for progress display
   * @returns {Object} Service status information
   * @private
   */
  _getCurrentServiceStatus() {
    if (!this.statusManager) return null;

    const status = this.statusManager.getStatus();
    return {
      internet: status.internet?.connected || false,
      jellyfin: status.jellyfin?.connected || false,
      vlc: status.vlc?.available || false,
      localMedia: status.localMedia?.available || false,
    };
  }

  /**
   * Update background progress UI
   * @param {Object} feedback - Progress feedback information
   * @private
   */
  _updateBackgroundProgressUI(feedback) {
    // Update progress bar if it exists
    const progressBar = document.getElementById("backgroundProgressBar");
    if (progressBar) {
      progressBar.style.width = `${feedback.progress.percentage}%`;
    }

    // Update progress text
    const progressText = document.getElementById("backgroundProgressText");
    if (progressText) {
      progressText.textContent = feedback.message;
    }

    // Update detailed progress if available
    const detailedProgress = document.getElementById(
      "backgroundProgressDetails"
    );
    if (detailedProgress && feedback.detailedMessage) {
      detailedProgress.textContent = feedback.detailedMessage;
    }

    // Update time estimate
    const timeEstimate = document.getElementById("backgroundProgressTime");
    if (timeEstimate && feedback.timeEstimate) {
      timeEstimate.textContent = feedback.timeEstimate;
    }
  }

  /**
   * Show offline mode UI elements
   * @param {Object} notification - Offline mode notification
   * @private
   */
  _showOfflineModeUI(notification) {
    // Show offline mode indicator in status bar
    const offlineMode = document.getElementById("offlineMode");
    if (offlineMode) {
      offlineMode.style.display = "flex";
    }

    // Add offline class to system status
    const systemStatus = document.getElementById("systemStatus");
    if (systemStatus) {
      systemStatus.classList.add("offline");
    }

    // Show offline notification
    this._showNotification(notification);

    // Update page title to indicate offline mode
    const originalTitle = document.title;
    document.title = "[Offline] " + originalTitle.replace("[Offline] ", "");
  }

  /**
   * Hide offline mode UI elements
   * @private
   */
  _hideOfflineModeUI() {
    // Hide offline mode indicator
    const offlineMode = document.getElementById("offlineMode");
    if (offlineMode) {
      offlineMode.style.display = "none";
    }

    // Remove offline class from system status
    const systemStatus = document.getElementById("systemStatus");
    if (systemStatus) {
      systemStatus.classList.remove("offline");
    }

    // Restore page title
    document.title = document.title.replace("[Offline] ", "");
  }

  /**
   * Update status indicators for offline mode
   * @private
   */
  _updateStatusIndicatorsForOfflineMode() {
    // Update internet status
    const internetStatus = document.getElementById("internetStatus");
    const internetText = document.getElementById("internetText");
    if (internetStatus && internetText) {
      internetStatus.className = "status-indicator status-offline";
      internetText.textContent = "Internet: Offline";
    }

    // Update Jellyfin status
    const jellyfinStatus = document.getElementById("jellyfinStatus");
    const jellyfinText = document.getElementById("jellyfinText");
    if (jellyfinStatus && jellyfinText) {
      jellyfinStatus.className = "status-indicator status-offline";
      jellyfinText.textContent = "Jellyfin: Offline";
    }
  }

  /**
   * Disable features that require internet connection
   * @private
   */
  _disableOnlineFeatures() {
    // Disable remote media related buttons
    const remoteButtons = document.querySelectorAll(
      ".btn-stream, .btn-download"
    );
    remoteButtons.forEach((button) => {
      button.disabled = true;
      button.title = "Requires internet connection";
      button.classList.add("disabled-offline");
    });

    // Update filter options to hide remote-only content
    const filterSelect = document.getElementById("filterSelect");
    if (filterSelect) {
      const remoteOption = filterSelect.querySelector('option[value="remote"]');
      if (remoteOption) {
        remoteOption.disabled = true;
        remoteOption.textContent += " (Offline)";
      }
    }
  }

  /**
   * Re-enable online features when connection is restored
   * @private
   */
  _enableOnlineFeatures() {
    // Re-enable remote media buttons
    const remoteButtons = document.querySelectorAll(
      ".btn-stream, .btn-download"
    );
    remoteButtons.forEach((button) => {
      button.disabled = false;
      button.title = "";
      button.classList.remove("disabled-offline");
    });

    // Re-enable filter options
    const filterSelect = document.getElementById("filterSelect");
    if (filterSelect) {
      const remoteOption = filterSelect.querySelector('option[value="remote"]');
      if (remoteOption) {
        remoteOption.disabled = false;
        remoteOption.textContent = remoteOption.textContent.replace(
          " (Offline)",
          ""
        );
      }
    }
  }

  /**
   * Retry connection to a specific service
   * @param {string} service - Service to retry
   * @private
   */
  _retryService(service) {
    console.log(
      `ProgressiveMediaLoader: Retrying ${service} connection`
    );

    if (this.statusManager) {
      // Clear cache for the service and retry
      this.statusManager.clearCache(service);

      // Trigger a new check for the service
      switch (service) {
        case "internet":
          this.statusManager.checkInternetConnectivity();
          break;
        case "jellyfin":
          this.statusManager.checkJellyfinConnectivity();
          break;
        case "localMedia":
          this.loadLocalMediaImmediate(true);
          break;
      }
    }
  }

  /**
   * Retry internet connection
   * @private
   */
  _retryConnection() {
    console.log(
      "ProgressiveMediaLoader: Retrying internet connection"
    );

    if (this.statusManager) {
      this.statusManager.clearCache();
      this.statusManager.initialize().then(() => {
        // Check if we're back online
        const status = this.statusManager.getStatus();
        if (status.internet.connected) {
          this.handleOfflineModeRecovery();
        }
      });
    }
  }

  /**
   * Dismiss error notification
   * @param {HTMLElement} notification - Notification element to dismiss
   * @private
   */
  _dismissErrorNotification(notification) {
    notification.classList.add("dismissing");
    setTimeout(() => {
      if (notification.parentNode) {
        notification.parentNode.removeChild(notification);
      }
    }, 300);
  }

  /**
   * Dismiss offline notification
   * @private
   */
  _dismissOfflineNotification() {
    const notifications = document.querySelectorAll(
      '.error-notification[data-type="offline_mode"]'
    );
    notifications.forEach((notification) =>
      this._dismissErrorNotification(notification)
    );
  }

  /**
   * Show general notification
   * @param {Object} notification - Notification information
   * @private
   */
  _showNotification(notification) {
    const element = this._createErrorNotification(notification);
    element.setAttribute("data-type", notification.type);
    this._showErrorNotification(element);
  }

  /**
   * Check if an error is recoverable
   * @param {Error} error - Error object
   * @returns {boolean} True if error is recoverable
   * @private
   */
  _isRecoverableError(error) {
    const recoverableErrors = [
      "timeout",
      "network",
      "connection",
      "unavailable",
      "not found",
    ];

    const errorMessage = (error?.message || "").toLowerCase();
    return recoverableErrors.some((keyword) => errorMessage.includes(keyword));
  }

  /**
   * Handle internet unavailable scenario
   * @param {Object} errorInfo - Error information
   * @private
   */
  _handleInternetUnavailable(errorInfo) {
    console.log(
      "ProgressiveMediaLoader: Handling internet unavailable"
    );
    this.adjustLoadingStrategy("offline");
    this.enableOfflineModeIndicators();
  }

  /**
   * Handle Jellyfin unavailable scenario
   * @param {Object} errorInfo - Error information
   * @private
   */
  _handleJellyfinUnavailable(errorInfo) {
    console.log(
      "ProgressiveMediaLoader: Handling Jellyfin unavailable"
    );
    this.adjustLoadingStrategy("degraded");

    // Continue with local-only mode
    this.loadingStates.remote.status = "error";
    this.loadingStates.remote.count = 0;

    // Update loading indicators
    this._notifyLoadingStateChange(
      "Remote media server unavailable - local media only"
    );
  }

  /**
   * Handle local media unavailable scenario
   * @param {Object} errorInfo - Error information
   * @private
   */
  _handleLocalMediaUnavailable(errorInfo) {
    console.log(
      "ProgressiveMediaLoader: Handling local media unavailable"
    );

    // This is a critical error - local media should always be available
    this.loadingStates.local.status = "error";
    this.loadingStates.phase = "error";

    // Try to load from cache as last resort
    const cachedLocal = this._loadLocalFromCache();
    if (cachedLocal.length > 0) {
      this.localMedia = cachedLocal;
      this.unifiedMedia = [...this.localMedia];
      this.loadingStates.local.status = "complete";
      this.loadingStates.local.count = this.localMedia.length;

      this._notifyLoadingStateChange(
        `Loaded ${cachedLocal.length} items from cache`
      );
    } else {
      this._notifyLoadingStateChange(
        "Local media unavailable - check storage access"
      );
    }
  }

  /**
   * Initialize loading state for non-blocking operation
   * @private
   */
  _initializeLoadingState() {
    const now = Date.now();
    this.loadingStates = {
      phase: "initializing",
      local: { status: "pending", count: 0, duration: 0, startTime: null },
      remote: { status: "pending", count: 0, duration: 0, startTime: null },
      unified: { status: "pending", count: 0, duration: 0, startTime: null },
      userInteractionEnabled: false,
      backgroundTasksActive: false,
      errors: [],
    };

    this.performanceMetrics = {
      timeToFirstInteraction: null,
      timeToLocalComplete: null,
      timeToRemoteComplete: null,
      timeToFullComplete: null,
    };
  }

  /**
   * Perform background remote media loading with progress indicators
   * @private
   * @param {boolean} forceRefresh - Force refresh of cached data
   * @param {Object} options - Background loading options
   */
  async _performBackgroundRemoteLoading(forceRefresh = false, options = {}) {
    const startTime = Date.now();
    const {
      showProgressIndicators = true,
      enableSeamlessIntegration = true,
      maxBackgroundTime = 30000,
    } = options;

    console.log(
      "ProgressiveMediaLoader: Performing background remote loading with options:",
      options
    );

    try {
      // Update loading state
      this.loadingStates.phase = "loading_remote";
      this.loadingStates.remote.status = "loading";
      this.loadingStates.remote.startTime = startTime;

      // Show initial progress indicator
      if (showProgressIndicators) {
        this.createLoadingIndicators("checking_connectivity", {
          current: 0,
          total: 3,
        });
      }

      // Check connectivity before attempting remote loading
      if (this.statusManager) {
        const internetStatus = this.statusManager.getStatus("internet");
        const jellyfinStatus = this.statusManager.getStatus("jellyfin");

        if (showProgressIndicators) {
          this.createLoadingIndicators("connectivity_checked", {
            current: 1,
            total: 3,
          });
        }

        if (!internetStatus?.connected) {
          console.log(
            "ProgressiveMediaLoader: No internet connection, skipping remote loading"
          );
          this._completeBackgroundLoading("offline");
          return;
        }

        if (!jellyfinStatus?.connected) {
          console.log(
            "ProgressiveMediaLoader: Jellyfin not available, skipping remote loading"
          );
          this._completeBackgroundLoading("degraded");
          return;
        }
      }

      // Set up timeout for background loading
      const timeoutPromise = new Promise((_, reject) => {
        setTimeout(
          () => reject(new Error("Background loading timeout")),
          maxBackgroundTime
        );
      });

      // Show loading progress
      if (showProgressIndicators) {
        this.createLoadingIndicators("loading_remote_data", {
          current: 2,
          total: 3,
        });
      }

      // Store current unified media state before loading remote data
      const existingUnifiedMedia = [...this.unifiedMedia];
      const existingLocalCount = this.localMedia.length;

      // Load unified media with timeout protection
      const loadingPromise = this.loadUnifiedMedia(forceRefresh);
      await Promise.race([loadingPromise, timeoutPromise]);

      // Preserve existing items during background loading
      if (enableSeamlessIntegration && this.remoteMedia.length > 0) {
        // Validate that local items are preserved before integration
        const localItemsPreserved = this._validateLocalItemsPreserved(
          existingUnifiedMedia,
          this.localMedia
        );

        if (!localItemsPreserved.isValid) {
          console.warn(
            'ProgressiveMediaLoader: Local items not properly preserved, using consistency manager:',
            localItemsPreserved.errors
          );
          
          // Use ModeConsistencyManager to ensure local items are preserved
          this.unifiedMedia = this.modeConsistencyManager.preserveLocalItemsInUnified(
            this.localMedia,
            this.remoteMedia,
            {
              enforceLocalPriority: true,
              enhanceWithRemote: true,
              validateConsistency: true
            }
          );
        }

        // Seamlessly integrate remote media while preserving existing items
        this.seamlesslyIntegrateRemoteMedia(this.remoteMedia);

        // Final validation to ensure no local items were removed
        const finalValidation = this._validateLocalItemsPreserved(
          this.unifiedMedia,
          this.localMedia
        );

        if (!finalValidation.isValid) {
          console.error(
            'ProgressiveMediaLoader: Local items lost during background loading, performing recovery:',
            finalValidation.errors
          );
          
          // Recovery: merge local items back into unified media
          this.unifiedMedia = this.modeConsistencyManager.preserveExistingItems(
            this.localMedia,
            this.unifiedMedia,
            {
              preserveAll: true,
              mergeProperties: true
            }
          );
          
          this.loadingStates.errors.push({
            type: 'local_items_recovery',
            errors: finalValidation.errors,
            timestamp: Date.now(),
            context: '_performBackgroundRemoteLoading',
            recoveryPerformed: true
          });
        }
      }

      // Update performance metrics
      const duration = Date.now() - startTime;
      this.performanceMetrics.timeToRemoteComplete = duration;
      this.loadingStates.remote.duration = duration;
      this.loadingStates.remote.status = "complete";
      this.loadingStates.remote.count = this.remoteMedia.length;

      // Show completion progress
      if (showProgressIndicators) {
        this.createLoadingIndicators(this.PHASES.REMOTE_LOADING_COMPLETE, {
          current: 3,
          total: 3,
        });
      }

      console.log(
        `ProgressiveMediaLoader: Background remote loading completed in ${duration}ms (${this.remoteMedia.length} remote items)`
      );

      this._completeBackgroundLoading("online");
    } catch (error) {
      const duration = Date.now() - startTime;
      this.loadingStates.remote.duration = duration;
      this.loadingStates.remote.status = "error";

      console.error(
        "ProgressiveMediaLoader: Background remote loading failed:",
        error
      );

      // Show error progress indicator
      if (showProgressIndicators) {
        this.createLoadingIndicators("remote_loading_error", {
          current: 0,
          total: 0,
          error: error.message,
        });
      }

      this._completeBackgroundLoading("error", error);
    }
  }

  /**
   * Complete background loading process
   * @private
   * @param {string} mode - Completion mode ('online', 'offline', 'degraded', 'error')
   * @param {Error} error - Error if completion mode is 'error'
   */
  _completeBackgroundLoading(mode, error = null) {
    this.loadingStates.backgroundTasksActive = false;
    this.loadingStates.phase = this.PHASES.COMPLETE;
    this.performanceMetrics.timeToFullComplete = Date.now();

    // Set connectivity mode
    this.connectivityMode = mode;

    let message = "";
    switch (mode) {
      case "online":
        message = `Loading complete (${this.unifiedMedia.length} total items)`;
        break;
      case "offline":
        message = `Local-only mode (${this.localMedia.length} items available)`;
        break;
      case "degraded":
        message = `Limited connectivity (${this.localMedia.length} local items available)`;
        break;
      case "error":
        message = `Background loading failed - local media available (${this.localMedia.length} items)`;
        this._handleLoadingError(error, "remote");
        break;
    }

    console.log(
      `ProgressiveMediaLoader: Background loading completed in ${mode} mode`
    );

    // Notify callbacks
    if (this.callbacks.onBackgroundTasksCompleted) {
      this.callbacks.onBackgroundTasksCompleted({
        mode,
        localCount: this.localMedia.length,
        remoteCount: this.remoteMedia.length,
        totalCount: this.unifiedMedia.length,
        error,
      });
    }

    if (this.callbacks.onComplete) {
      this.callbacks.onComplete(this.unifiedMedia);
    }

    this._notifyLoadingStateChange(message);
  }

  /**
   * Handle loading errors with categorization
   * @private
   * @param {Error} error - The error that occurred
   * @param {string} phase - Loading phase where error occurred
   */
  _handleLoadingError(error, phase) {
    const errorInfo = {
      phase,
      message: error.message,
      timestamp: Date.now(),
      recoverable: this._isRecoverableError(error),
    };

    this.loadingStates.errors.push(errorInfo);

    console.error(
      `ProgressiveMediaLoader: Error in ${phase} phase:`,
      error
    );

    if (this.callbacks.onError) {
      this.callbacks.onError(error, errorInfo);
    }
  }

  /**
   * Determine if an error is recoverable
   * @private
   * @param {Error} error - The error to check
   * @returns {boolean} True if error is recoverable
   */
  _isRecoverableError(error) {
    const recoverablePatterns = [
      /timeout/i,
      /network/i,
      /fetch/i,
      /connection/i,
      /unavailable/i,
    ];

    return recoverablePatterns.some((pattern) => pattern.test(error.message));
  }

  /**
   * Get progress message for loading phase (DEPRECATED - use PhaseManager.getPhaseMessage)
   * @private
   * @param {string} phase - Loading phase
   * @param {Object} progress - Progress information
   * @returns {string} Human-readable progress message
   */
  _getProgressMessage(phase, progress = {}) {
    // Log deprecation warning and delegate to PhaseManager
    console.warn(
      "ProgressiveMediaLoader: _getProgressMessage is deprecated, use PhaseManager.getPhaseMessage instead"
    );
    return this.phaseManager.getPhaseMessage(phase, progress);
  }

  /**
   * Initialize status manager integration
   * @private
   */
  _initializeStatusManagerIntegration() {
    if (!this.statusManager) return;

    console.log(
      "ProgressiveMediaLoader: Setting up status manager event listeners"
    );

    // Set up event listeners
    const eventMappings = [
      "connectivityModeChange",
      "internet:connected",
      "internet:disconnected",
      "jellyfin:connected",
      "jellyfin:disconnected",
      "statusChange",
    ];

    eventMappings.forEach((event) => {
      const listener = (data) => this.onStatusChange(event, data);
      this.statusEventListeners.set(event, listener);
      this.statusManager.on(event, listener);
    });

    // Get initial connectivity mode
    const currentStatus = this.statusManager.getStatus();
    if (currentStatus) {
      const internetConnected = currentStatus.internet?.connected || false;
      const jellyfinConnected = currentStatus.jellyfin?.connected || false;

      let mode = "offline";
      if (internetConnected && jellyfinConnected) {
        mode = "online";
      } else if (internetConnected) {
        mode = "degraded";
      }

      this.adjustLoadingStrategy(mode);
    }
  }

  /**
   * Clean up status manager integration
   * @private
   */
  _cleanupStatusManagerIntegration() {
    if (!this.statusManager) return;

    console.log(
      "ProgressiveMediaLoader: Cleaning up status manager event listeners"
    );

    // Remove all event listeners
    this.statusEventListeners.forEach((listener, event) => {
      this.statusManager.off(event, listener);
    });

    this.statusEventListeners.clear();
  }

  /**
   * Handle connectivity mode changes
   * @private
   * @param {Object} data - Event data
   */
  _handleConnectivityModeChange(data) {
    const { oldMode, newMode } = data;
    console.log(
      `ProgressiveMediaLoader: Connectivity mode changed from ${oldMode} to ${newMode}`
    );

    this.adjustLoadingStrategy(newMode);

    // If we went from offline/degraded to online, try to load remote media
    if (
      (oldMode === "offline" || oldMode === "degraded") &&
      newMode === "online"
    ) {
      if (
        !this.loadingStates.backgroundTasksActive &&
        this.loadingStates.userInteractionEnabled
      ) {
        console.log(
          "ProgressiveMediaLoader: Connectivity restored, starting background remote loading"
        );
        this.loadRemoteMediaBackground(false, { showProgressIndicators: true });
      }
    }
  }

  /**
   * Handle internet connection established
   * @private
   * @param {Object} data - Event data
   */
  _handleInternetConnected(data) {
    console.log(
      "ProgressiveMediaLoader: Internet connection established"
    );

    // If we were in offline mode and now have internet, upgrade to degraded mode
    if (this.connectivityMode === "offline") {
      this.adjustLoadingStrategy("degraded");
    }
  }

  /**
   * Handle internet connection lost
   * @private
   * @param {Object} data - Event data
   */
  _handleInternetDisconnected(data) {
    console.log("ProgressiveMediaLoader: Internet connection lost");

    // Switch to offline mode
    this.adjustLoadingStrategy("offline");

    // Cancel any ongoing background tasks
    if (this.loadingStates.backgroundTasksActive) {
      console.log(
        "ProgressiveMediaLoader: Cancelling background tasks due to internet loss"
      );
      this.loadingStates.backgroundTasksActive = false;
      this._notifyLoadingStateChange(
        "Background loading cancelled - no internet connection"
      );
    }
  }

  /**
   * Handle Jellyfin connection established
   * @private
   * @param {Object} data - Event data
   */
  _handleJellyfinConnected(data) {
    console.log(
      "ProgressiveMediaLoader: Jellyfin connection established"
    );

    // If we have internet and now Jellyfin, upgrade to online mode
    const internetStatus = this.statusManager?.getStatus("internet");
    if (internetStatus?.connected) {
      this.adjustLoadingStrategy("online");

      // Start background loading if not already active
      if (
        !this.loadingStates.backgroundTasksActive &&
        this.loadingStates.userInteractionEnabled
      ) {
        console.log(
          "ProgressiveMediaLoader: Jellyfin available, starting background remote loading"
        );
        this.loadRemoteMediaBackground(false, { showProgressIndicators: true });
      }
    }
  }

  /**
   * Handle Jellyfin connection lost
   * @private
   * @param {Object} data - Event data
   */
  _handleJellyfinDisconnected(data) {
    console.log("ProgressiveMediaLoader: Jellyfin connection lost");

    // Downgrade to degraded mode if we still have internet
    const internetStatus = this.statusManager?.getStatus("internet");
    if (internetStatus?.connected) {
      this.adjustLoadingStrategy("degraded");
    } else {
      this.adjustLoadingStrategy("offline");
    }
  }

  /**
   * Handle general status changes
   * @private
   * @param {Object} data - Event data
   */
  _handleGeneralStatusChange(data) {
    const { service, oldStatus, newStatus } = data;

    // Log significant status changes
    if (service === "localMedia" && oldStatus.count !== newStatus.count) {
      console.log(
        `ProgressiveMediaLoader: Local media count changed from ${oldStatus.count} to ${newStatus.count}`
      );

      // Update our local media if the count changed significantly
      if (Math.abs(oldStatus.count - newStatus.count) > 0) {
        this._refreshLocalMediaIfNeeded();
      }
    }
  }

  /**
   * Enable full functionality for online mode
   * @private
   */
  _enableFullFunctionality() {
    console.log(
      "ProgressiveMediaLoader: Enabling full functionality (online mode)"
    );
    // All features available - no restrictions
  }

  /**
   * Enable limited functionality for degraded mode
   * @private
   */
  _enableLimitedFunctionality() {
    console.log(
      "ProgressiveMediaLoader: Enabling limited functionality (degraded mode)"
    );
    // Local media + internet available but no Jellyfin
    // Could potentially load from other remote sources if implemented
  }

  /**
   * Enable offline mode functionality
   * @private
   */
  _enableOfflineMode() {
    console.log(
      "ProgressiveMediaLoader: Enabling offline mode (local-only)"
    );
    // Only local media available
    // Cancel any background tasks
    if (this.loadingStates.backgroundTasksActive) {
      this.loadingStates.backgroundTasksActive = false;
      this._notifyLoadingStateChange(
        "Switched to offline mode - local media only"
      );
    }
  }

  /**
   * Handle internet unavailability
   * @private
   * @param {Object} errorInfo - Error information
   */
  _handleInternetUnavailable(errorInfo) {
    console.log(
      "ProgressiveMediaLoader: Handling internet unavailability"
    );
    this.adjustLoadingStrategy("offline");
    this._notifyLoadingStateChange("No internet connection - local media only");
  }

  /**
   * Handle Jellyfin unavailability
   * @private
   * @param {Object} errorInfo - Error information
   */
  _handleJellyfinUnavailable(errorInfo) {
    console.log(
      "ProgressiveMediaLoader: Handling Jellyfin unavailability"
    );

    // Check if we still have internet
    const internetStatus = this.statusManager?.getStatus("internet");
    if (internetStatus?.connected) {
      this.adjustLoadingStrategy("degraded");
      this._notifyLoadingStateChange(
        "Jellyfin unavailable - local media and limited remote features"
      );
    } else {
      this.adjustLoadingStrategy("offline");
      this._notifyLoadingStateChange(
        "No remote services available - local media only"
      );
    }
  }

  /**
   * Handle local media unavailability
   * @private
   * @param {Object} errorInfo - Error information
   */
  _handleLocalMediaUnavailable(errorInfo) {
    console.log(
      "ProgressiveMediaLoader: Handling local media unavailability"
    );

    // This is a critical error - local media should always be available
    this._notifyLoadingStateChange(
      "Warning: Local media unavailable - check media directory"
    );

    // Try to recover by clearing cache and retrying
    setTimeout(() => {
      console.log(
        "ProgressiveMediaLoader: Attempting to recover local media"
      );
      this.clearCache();
      this.loadLocalMediaImmediate(true).catch((error) => {
        console.error(
          "ProgressiveMediaLoader: Local media recovery failed:",
          error
        );
      });
    }, 5000);
  }

  /**
   * Refresh local media if needed based on status changes
   * @private
   */
  _refreshLocalMediaIfNeeded() {
    // Only refresh if we're not currently loading and user interaction is enabled
    if (
      !this.loadingStates.backgroundTasksActive &&
      this.loadingStates.userInteractionEnabled &&
      this.loadingStates.local.status === "complete"
    ) {
      console.log(
        "ProgressiveMediaLoader: Refreshing local media due to status change"
      );

      // Refresh local media in background
      setTimeout(() => {
        this.loadLocalMediaImmediate(true).catch((error) => {
          console.error(
            "ProgressiveMediaLoader: Local media refresh failed:",
            error
          );
        });
      }, 1000);
    }
  }

  /**
   * Notify loading state change
   * @private
   */
  _notifyLoadingStateChange(message) {
    if (this.callbacks.onLoadingStateChange) {
      this.callbacks.onLoadingStateChange(this.loadingStates, message);
    }
  }

  /**
   * Load local media from cache
   * @private
   * @returns {Array} Cached local media or empty array
   */
  _loadLocalFromCache() {
    try {
      const cached = localStorage.getItem("progressiveLoader_localMedia");
      if (cached) {
        const data = JSON.parse(cached);
        const ageInMinutes = (Date.now() - (data.timestamp || 0)) / (1000 * 60);

        // Use cache if less than 30 minutes old
        if (ageInMinutes < 30) {
          console.log(
            `ProgressiveMediaLoader: Using cached local media (${ageInMinutes.toFixed(
              1
            )} minutes old)`
          );
          return data.media || [];
        }
      }
    } catch (error) {
      console.warn("ProgressiveMediaLoader: Error loading local cache:", error);
    }
    return [];
  }

  /**
   * Load remote media from cache
   * @private
   * @returns {Array} Cached remote media or empty array
   */
  _loadRemoteFromCache() {
    try {
      const cached = localStorage.getItem("progressiveLoader_remoteMedia");
      if (cached) {
        const data = JSON.parse(cached);
        const ageInMinutes = (Date.now() - (data.timestamp || 0)) / (1000 * 60);

        // Use cache if less than 10 minutes old
        if (ageInMinutes < 10) {
          console.log(
            `ProgressiveMediaLoader: Using cached remote media (${ageInMinutes.toFixed(
              1
            )} minutes old)`
          );
          return data.media || [];
        }
      }
    } catch (error) {
      console.warn(
        "ProgressiveMediaLoader: Error loading remote cache:",
        error
      );
    }
    return [];
  }

  /**
   * Cache remote media data
   * @private
   * @param {Array} remoteMedia - Remote media to cache
   */
  _cacheRemoteMedia(remoteMedia) {
    try {
      const cacheData = {
        media: remoteMedia,
        timestamp: Date.now(),
      };
      localStorage.setItem(
        "progressiveLoader_remoteMedia",
        JSON.stringify(cacheData)
      );
    } catch (error) {
      console.warn(
        "ProgressiveMediaLoader: Error caching remote media:",
        error
      );
    }
  }

  /**
   * Load unified media from cache
   * @private
   * @returns {Array} Cached unified media or empty array
   */
  _loadUnifiedFromCache() {
    try {
      const cached = localStorage.getItem("progressiveLoader_unifiedMedia");
      if (cached) {
        const data = JSON.parse(cached);
        const ageInMinutes = (Date.now() - (data.timestamp || 0)) / (1000 * 60);

        // Use cache if less than 10 minutes old
        if (ageInMinutes < 10) {
          console.log(
            `ProgressiveMediaLoader: Using cached unified media (${ageInMinutes.toFixed(
              1
            )} minutes old)`
          );
          return data.media || [];
        }
      }
    } catch (error) {
      console.warn(
        "ProgressiveMediaLoader: Error loading unified cache:",
        error
      );
    }
    return [];
  }

  /**
   * Cache unified media data
   * @private
   * @param {Array} unifiedMedia - Unified media to cache
   */
  _cacheUnifiedMedia(unifiedMedia) {
    try {
      const cacheData = {
        media: unifiedMedia,
        timestamp: Date.now(),
      };
      localStorage.setItem(
        "progressiveLoader_unifiedMedia",
        JSON.stringify(cacheData)
      );
    } catch (error) {
      console.warn(
        "ProgressiveMediaLoader: Error caching unified media:",
        error
      );
    }
  }

  /**
   * Initialize status manager integration
   * @private
   */
  _initializeStatusManagerIntegration() {
    if (!this.statusManager) return;

    // Listen for status change events
    const statusEvents = [
      "connectivityModeChange",
      "internet:connected",
      "internet:disconnected",
      "jellyfin:connected",
      "jellyfin:disconnected",
      "statusChange",
      "serviceError",
    ];

    statusEvents.forEach((event) => {
      const listener = (data) => this.onStatusChange(event, data);
      this.statusManager.on(event, listener);
      this.statusEventListeners.set(event, listener);
    });

    console.log(
      "ProgressiveMediaLoader: Status manager integration initialized"
    );
  }

  /**
   * Cleanup status manager integration
   * @private
   */
  _cleanupStatusManagerIntegration() {
    if (!this.statusManager) return;

    // Remove all event listeners
    this.statusEventListeners.forEach((listener, event) => {
      this.statusManager.off(event, listener);
    });
    this.statusEventListeners.clear();

    console.log(
      "ProgressiveMediaLoader: Status manager integration cleaned up"
    );
  }

  /**
   * Initialize loading state
   * @private
   */
  _initializeLoadingState() {
    this.loadingStates = {
      phase: "initializing",
      local: { status: "pending", count: 0, duration: 0, startTime: null },
      remote: { status: "pending", count: 0, duration: 0, startTime: null },
      unified: { status: "pending", count: 0, duration: 0, startTime: null },
      userInteractionEnabled: false,
      backgroundTasksActive: false,
      errors: [],
    };

    this.performanceMetrics = {
      timeToFirstInteraction: null,
      timeToLocalComplete: null,
      timeToRemoteComplete: null,
      timeToFullComplete: null,
    };
  }

  /**
   * Notify loading state change
   * @param {string} message - Status message
   * @private
   */
  _notifyLoadingStateChange(message) {
    if (this.callbacks.onLoadingStateChange) {
      this.callbacks.onLoadingStateChange(this.loadingStates, message);
    }
  }

  /**
   * Get progress message for current phase (DEPRECATED - use PhaseManager.getPhaseMessage)
   * @param {string} phase - Current phase
   * @param {Object} progress - Progress information
   * @returns {string} Progress message
   * @private
   */
  _getProgressMessage(phase, progress) {
    // Log deprecation warning and delegate to PhaseManager
    console.warn(
      "ProgressiveMediaLoader: _getProgressMessage is deprecated, use PhaseManager.getPhaseMessage instead"
    );
    return this.phaseManager.getPhaseMessage(phase, progress);
  }

  /**
   * Handle loading error
   * @param {Error} error - Error object
   * @param {string} context - Error context
   * @private
   */
  _handleLoadingError(error, context) {
    const errorInfo = {
      service: context,
      error: error.message || "Unknown error",
      timestamp: Date.now(),
      recoverable: this._isRecoverableError(error),
    };

    this.loadingStates.errors.push(errorInfo);

    // Transition to error phase with proper validation
    if (
      !this.phaseManager.transitionToPhase(this.PHASES.ERROR, {
        context: `loading_error_${context}`,
        error: error.message,
        recoverable: errorInfo.recoverable,
      })
    ) {
      console.error(
        "ProgressiveMediaLoader: Failed to transition to error phase during error handling"
      );
    }
    this.loadingStates.phase = this.PHASES.ERROR;

    console.error(
      `ProgressiveMediaLoader: Loading error in ${context}:`,
      error
    );

    // Display error message
    this.displayServiceUnavailabilityMessage(errorInfo);
  }

  /**
   * Check if error is recoverable
   * @param {Error} error - Error object
   * @returns {boolean} True if error is recoverable
   * @private
   */
  _isRecoverableError(error) {
    const recoverablePatterns = [
      /timeout/i,
      /network/i,
      /connection/i,
      /unavailable/i,
      /temporary/i,
    ];

    return recoverablePatterns.some((pattern) =>
      pattern.test(error.message || error.toString())
    );
  }
}

// Export for module use
if (typeof module !== "undefined" && module.exports) {
  module.exports = ProgressiveMediaLoader;
}

// Make available globally
window.ProgressiveMediaLoader = ProgressiveMediaLoader;
