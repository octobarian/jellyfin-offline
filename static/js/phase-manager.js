/**
 * Phase Manager Component
 * Centralizes loading phase management and ensures all phases are recognized
 */

class PhaseManager {
    /**
     * Create a PhaseManager instance
     * @param {Array<string>} knownPhases - Array of known phase names
     */
    constructor(knownPhases = []) {
        // Default known phases based on design document
        this.knownPhases = new Set([
            'initializing',
            'loading_local',
            'local_complete',
            'checking_connectivity',
            'loading_remote_data',
            'remote_complete',
            'unified_complete',
            'error',
            // Additional phases from current implementation
            'connectivity_checked',
            'remote_loading_complete',
            'remote_loading_error',
            ...knownPhases
        ]);
        
        // Phase messages mapping
        this.phaseMessages = {
            'initializing': 'Initializing media loading...',
            'loading_local': 'Loading local media...',
            'local_complete': 'Local media loaded',
            'checking_connectivity': 'Checking remote services...',
            'loading_remote_data': 'Loading remote media in background...',
            'remote_complete': 'Remote media loaded',
            'unified_complete': 'All media loaded',
            'error': 'Loading error occurred',
            'connectivity_checked': 'Remote services checked',
            'remote_loading_complete': 'Background loading complete',
            'remote_loading_error': 'Background loading failed'
        };
        
        // Phase state tracking
        this.currentPhase = null;
        this.phaseHistory = [];
        this.transitionTimestamps = new Map();
        
        // Valid phase transitions mapping
        this.validTransitions = {
            'initializing': ['loading_local', 'error'],
            'loading_local': ['local_complete', 'error'],
            'local_complete': ['checking_connectivity', 'unified_complete', 'error'],
            'checking_connectivity': ['connectivity_checked', 'loading_remote_data', 'error'],
            'connectivity_checked': ['loading_remote_data', 'error'],
            'loading_remote_data': ['remote_complete', 'remote_loading_error', 'error'],
            'remote_complete': ['unified_complete', 'error'],
            'remote_loading_complete': ['unified_complete', 'error'],
            'remote_loading_error': ['unified_complete', 'error'],
            'unified_complete': ['error'], // Can only go to error from complete
            'error': [] // Terminal state
        };
        
        console.log('PhaseManager: Initialized with', this.knownPhases.size, 'known phases');
    }
    
    /**
     * Validate if a phase exists in the known phases registry
     * @param {string} phase - Phase name to validate
     * @returns {boolean} True if phase is known, false otherwise
     */
    validatePhase(phase) {
        if (typeof phase !== 'string') {
            console.warn('PhaseManager: Invalid phase type, expected string, got:', typeof phase);
            return false;
        }
        
        const isValid = this.knownPhases.has(phase);
        
        if (!isValid) {
            console.warn(`PhaseManager: Unknown phase encountered: "${phase}"`);
        }
        
        return isValid;
    }
    
    /**
     * Get appropriate message for a phase
     * @param {string} phase - Phase name
     * @param {Object} progress - Optional progress information
     * @returns {string} Human-readable message for the phase
     */
    getPhaseMessage(phase, progress = {}) {
        // Validate phase first
        if (!this.validatePhase(phase)) {
            return this.handleUnknownPhase(phase);
        }
        
        let baseMessage = this.phaseMessages[phase] || `Loading: ${phase}`;
        
        // Enhance message with progress information if available
        if (progress.current !== undefined && progress.total !== undefined && progress.total > 0) {
            const percentage = Math.round((progress.current / progress.total) * 100);
            baseMessage += ` (${percentage}%)`;
        }
        
        if (progress.count !== undefined) {
            baseMessage += ` - ${progress.count} items`;
        }
        
        if (progress.remoteCount !== undefined) {
            baseMessage = baseMessage.replace('Background loading complete', 
                `Background loading complete (${progress.remoteCount} remote items)`);
        }
        
        if (progress.error && phase === 'remote_loading_error') {
            baseMessage += `: ${progress.error}`;
        }
        
        return baseMessage;
    }
    
    /**
     * Transition to a new phase with validation logic
     * @param {string} newPhase - Phase to transition to
     * @param {Object} context - Optional context information for the transition
     * @returns {boolean} True if transition was successful, false otherwise
     */
    transitionToPhase(newPhase, context = {}) {
        // Validate the new phase exists
        if (!this.validatePhase(newPhase)) {
            console.error(`PhaseManager: Cannot transition to unknown phase: "${newPhase}"`);
            return false;
        }
        
        // Check if transition is valid
        if (!this._isValidTransition(this.currentPhase, newPhase)) {
            console.warn(`PhaseManager: Invalid transition from "${this.currentPhase}" to "${newPhase}"`);
            // Allow transition but log warning for debugging
        }
        
        // Record the transition
        const previousPhase = this.currentPhase;
        const timestamp = Date.now();
        
        this.currentPhase = newPhase;
        this.phaseHistory.push({
            from: previousPhase,
            to: newPhase,
            timestamp: timestamp,
            context: context
        });
        this.transitionTimestamps.set(newPhase, timestamp);
        
        console.log(`PhaseManager: Transitioned from "${previousPhase}" to "${newPhase}"`);
        
        return true;
    }
    
    /**
     * Get the current phase
     * @returns {string|null} Current phase name or null if not set
     */
    getCurrentPhase() {
        return this.currentPhase;
    }
    
    /**
     * Get phase transition history
     * @returns {Array} Array of transition records
     */
    getPhaseHistory() {
        return [...this.phaseHistory];
    }
    
    /**
     * Get time spent in current phase
     * @returns {number} Time in milliseconds since entering current phase
     */
    getTimeInCurrentPhase() {
        if (!this.currentPhase) {
            return 0;
        }
        
        const startTime = this.transitionTimestamps.get(this.currentPhase);
        return startTime ? Date.now() - startTime : 0;
    }
    
    /**
     * Check if a phase transition is valid
     * @private
     * @param {string|null} fromPhase - Current phase
     * @param {string} toPhase - Target phase
     * @returns {boolean} True if transition is valid
     */
    _isValidTransition(fromPhase, toPhase) {
        // If no current phase, any valid phase is allowed
        if (!fromPhase) {
            return this.knownPhases.has(toPhase);
        }
        
        // Check if transition is in valid transitions map
        const validTargets = this.validTransitions[fromPhase];
        if (!validTargets) {
            // If no specific rules, allow any valid phase
            return this.knownPhases.has(toPhase);
        }
        
        return validTargets.includes(toPhase);
    }
    
    /**
     * Reset phase state (useful for testing or restarting)
     */
    resetPhaseState() {
        this.currentPhase = null;
        this.phaseHistory = [];
        this.transitionTimestamps.clear();
        console.log('PhaseManager: Phase state reset');
    }
    
    /**
     * Handle unknown phase by logging error and providing fallback
     * @param {string} phase - Unknown phase name
     * @returns {string} Fallback message for unknown phase
     */
    handleUnknownPhase(phase) {
        const errorMessage = `Unknown phase encountered: "${phase}"`;
        console.error(`PhaseManager: ${errorMessage}`);
        
        // Log to help with debugging
        console.error('PhaseManager: Known phases:', Array.from(this.knownPhases).sort());
        console.error('PhaseManager: Current phase:', this.currentPhase);
        console.error('PhaseManager: Phase history:', this.phaseHistory.slice(-3)); // Last 3 transitions
        
        // Try to suggest a similar known phase
        const suggestion = this._findSimilarPhase(phase);
        if (suggestion) {
            console.warn(`PhaseManager: Did you mean "${suggestion}"?`);
        }
        
        // Transition to error state if we have a current phase
        if (this.currentPhase && this.currentPhase !== 'error') {
            console.warn('PhaseManager: Transitioning to error state due to unknown phase');
            this.transitionToPhase('error', { reason: 'unknown_phase', unknownPhase: phase });
        }
        
        // Return fallback message
        return `Loading: ${phase}`;
    }
    
    /**
     * Find a similar known phase for suggestions
     * @private
     * @param {string} unknownPhase - The unknown phase to find suggestions for
     * @returns {string|null} Similar phase name or null if none found
     */
    _findSimilarPhase(unknownPhase) {
        if (typeof unknownPhase !== 'string') {
            return null;
        }
        
        const lowerUnknown = unknownPhase.toLowerCase();
        const knownPhasesArray = Array.from(this.knownPhases);
        
        // Look for exact substring matches first
        for (const phase of knownPhasesArray) {
            if (phase.toLowerCase().includes(lowerUnknown) || lowerUnknown.includes(phase.toLowerCase())) {
                return phase;
            }
        }
        
        // Look for phases with similar words
        const unknownWords = lowerUnknown.split(/[_\s-]+/);
        for (const phase of knownPhasesArray) {
            const phaseWords = phase.toLowerCase().split(/[_\s-]+/);
            const commonWords = unknownWords.filter(word => phaseWords.includes(word));
            if (commonWords.length > 0) {
                return phase;
            }
        }
        
        return null;
    }
    
    /**
     * Add a new known phase to the registry
     * @param {string} phase - Phase name to add
     * @param {string} message - Optional custom message for the phase
     */
    addKnownPhase(phase, message = null) {
        if (typeof phase !== 'string') {
            console.warn('PhaseManager: Cannot add phase, invalid type:', typeof phase);
            return false;
        }
        
        this.knownPhases.add(phase);
        
        if (message) {
            this.phaseMessages[phase] = message;
        }
        
        console.log(`PhaseManager: Added known phase: "${phase}"`);
        return true;
    }
    
    /**
     * Get all known phases
     * @returns {Array<string>} Array of known phase names
     */
    getKnownPhases() {
        return Array.from(this.knownPhases).sort();
    }
    
    /**
     * Check if phase manager has a custom message for a phase
     * @param {string} phase - Phase name to check
     * @returns {boolean} True if custom message exists
     */
    hasCustomMessage(phase) {
        return this.phaseMessages.hasOwnProperty(phase);
    }
    
    /**
     * Set custom message for a phase
     * @param {string} phase - Phase name
     * @param {string} message - Custom message
     */
    setPhaseMessage(phase, message) {
        if (typeof phase !== 'string' || typeof message !== 'string') {
            console.warn('PhaseManager: Invalid parameters for setPhaseMessage');
            return false;
        }
        
        // Add phase to known phases if not already present
        if (!this.knownPhases.has(phase)) {
            this.addKnownPhase(phase);
        }
        
        this.phaseMessages[phase] = message;
        console.log(`PhaseManager: Set custom message for phase "${phase}": "${message}"`);
        return true;
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = PhaseManager;
}