/**
 * Mode Consistency Manager - Handles media merging and consistency across loading modes
 * Ensures media items remain visible during mode transitions and provides consistent results
 */

class ModeConsistencyManager {
    constructor(options = {}) {
        this.options = {
            enableLogging: options.enableLogging === true,
            preserveLocalItems: options.preserveLocalItems !== false,
            validateTransitions: options.validateTransitions !== false,
            mergeStrategy: options.mergeStrategy || 'additive',
            ...options
        };

        // Track mode transition history
        this.transitionHistory = [];
        
        // Current mode state
        this.currentMode = null;
        this.previousMode = null;
        
        // Media state tracking
        this.mediaState = {
            local: [],
            remote: [],
            unified: [],
            lastMergeTimestamp: null,
            consistencyChecks: []
        };

        // Validation rules for mode transitions
        this.validTransitions = new Map([
            ['local', ['unified', 'local']],
            ['remote', ['unified', 'remote']],
            ['unified', ['local', 'remote', 'unified']],
            [null, ['local', 'remote', 'unified']]
        ]);

        this._log('ModeConsistencyManager initialized', this.options);
    }

    /**
     * Merge media results from local and remote sources
     * @param {Array} localItems - Local media items
     * @param {Array} remoteItems - Remote media items
     * @param {Object} options - Merge options
     * @returns {Array} Merged media results
     */
    mergeMediaResults(localItems = [], remoteItems = [], options = {}) {
        const mergeOptions = {
            strategy: options.strategy || this.options.mergeStrategy,
            preserveLocal: options.preserveLocal !== false,
            deduplicateBy: options.deduplicateBy || 'id',
            enhanceLocal: options.enhanceLocal !== false,
            ...options
        };

        // Validate input arrays first
        if (!Array.isArray(localItems)) {
            this._logError('Invalid localItems - not an array', localItems);
            localItems = [];
        }
        if (!Array.isArray(remoteItems)) {
            this._logError('Invalid remoteItems - not an array', remoteItems);
            remoteItems = [];
        }

        this._log('Merging media results', {
            localCount: localItems.length,
            remoteCount: remoteItems.length,
            options: mergeOptions
        });

        // Update media state tracking
        this.mediaState.local = [...localItems];
        this.mediaState.remote = [...remoteItems];

        let mergedResults = [];

        try {
            switch (mergeOptions.strategy) {
                case 'additive':
                    mergedResults = this._mergeAdditive(localItems, remoteItems, mergeOptions);
                    break;
                case 'replace':
                    mergedResults = this._mergeReplace(localItems, remoteItems, mergeOptions);
                    break;
                case 'enhance':
                    mergedResults = this._mergeEnhance(localItems, remoteItems, mergeOptions);
                    break;
                default:
                    this._logError('Unknown merge strategy', mergeOptions.strategy);
                    mergedResults = this._mergeAdditive(localItems, remoteItems, mergeOptions);
            }

            // Update unified state
            this.mediaState.unified = mergedResults;
            this.mediaState.lastMergeTimestamp = Date.now();

            this._log('Media merge completed', {
                strategy: mergeOptions.strategy,
                resultCount: mergedResults.length,
                localPreserved: this._countPreservedLocal(mergedResults, localItems),
                remoteAdded: this._countAddedRemote(mergedResults, localItems)
            });

            return mergedResults;

        } catch (error) {
            this._logError('Error during media merge', error);
            // Fallback to preserving local items
            return this.preserveExistingItems(localItems, remoteItems);
        }
    }

    /**
     * Preserve existing items during mode transitions
     * @param {Array} currentItems - Currently displayed items
     * @param {Array} newItems - New items to integrate
     * @param {Object} options - Preservation options
     * @returns {Array} Items with existing ones preserved
     */
    preserveExistingItems(currentItems = [], newItems = [], options = {}) {
        const preserveOptions = {
            preserveAll: options.preserveAll !== false,
            mergeProperties: options.mergeProperties !== false,
            deduplicateBy: options.deduplicateBy || 'id',
            ...options
        };

        // Validate and normalize input arrays first
        if (!Array.isArray(currentItems)) currentItems = [];
        if (!Array.isArray(newItems)) newItems = [];

        this._log('Preserving existing items', {
            currentCount: currentItems.length,
            newCount: newItems.length,
            options: preserveOptions
        });

        // If no current items, return new items
        if (currentItems.length === 0) {
            return [...newItems];
        }

        // If no new items, preserve current items
        if (newItems.length === 0) {
            return [...currentItems];
        }

        try {
            const preserved = [...currentItems];
            const dedupeKey = preserveOptions.deduplicateBy;

            // Create a map of existing items for quick lookup
            const existingMap = new Map();
            currentItems.forEach(item => {
                const key = this._getItemKey(item, dedupeKey);
                if (key) {
                    existingMap.set(key, item);
                }
            });

            // Add new items that don't already exist
            newItems.forEach(newItem => {
                const key = this._getItemKey(newItem, dedupeKey);
                if (key && !existingMap.has(key)) {
                    preserved.push(newItem);
                } else if (key && preserveOptions.mergeProperties) {
                    // Enhance existing item with new properties
                    const existingItem = existingMap.get(key);
                    const enhanced = this._enhanceItem(existingItem, newItem);
                    const index = preserved.findIndex(item => 
                        this._getItemKey(item, dedupeKey) === key
                    );
                    if (index >= 0) {
                        preserved[index] = enhanced;
                    }
                }
            });

            this._log('Items preserved successfully', {
                preservedCount: preserved.length,
                originalCount: currentItems.length,
                newItemsAdded: preserved.length - currentItems.length
            });

            return preserved;

        } catch (error) {
            this._logError('Error preserving existing items', error);
            // Fallback to current items
            return [...currentItems];
        }
    }

    /**
     * Validate mode transition for consistency
     * @param {string} fromMode - Current mode
     * @param {string} toMode - Target mode
     * @param {Array} items - Items involved in transition
     * @returns {Object} Validation result
     */
    validateModeTransition(fromMode, toMode, items = []) {
        const validation = {
            isValid: false,
            fromMode,
            toMode,
            itemCount: items.length,
            errors: [],
            warnings: [],
            timestamp: Date.now()
        };

        this._log('Validating mode transition', { fromMode, toMode, itemCount: items.length });

        try {
            // Check if transition is allowed
            const allowedTransitions = this.validTransitions.get(fromMode) || [];
            if (!allowedTransitions.includes(toMode)) {
                validation.errors.push(`Invalid transition from ${fromMode} to ${toMode}`);
            }

            // Validate items array
            if (!Array.isArray(items)) {
                validation.errors.push('Items must be an array');
                items = []; // Set to empty array to prevent further errors
            } else {
                // Check for required properties in items
                const invalidItems = items.filter(item => !this._isValidMediaItem(item));
                if (invalidItems.length > 0) {
                    validation.warnings.push(`${invalidItems.length} items have invalid structure`);
                }
            }

            // Mode-specific validations
            if (toMode === 'unified' && fromMode === 'local') {
                if (items.length === 0) {
                    validation.warnings.push('Transitioning to unified mode with no items');
                }
            }

            validation.isValid = validation.errors.length === 0;

            this._log('Mode transition validation completed', validation);

            // Store validation result
            this.mediaState.consistencyChecks.push(validation);

            return validation;

        } catch (error) {
            validation.errors.push(`Validation error: ${error.message}`);
            this._logError('Error during mode transition validation', error);
            return validation;
        }
    }

    /**
     * Handle mode switch with seamless transition
     * @param {string} newMode - Target mode
     * @param {Object} options - Switch options
     * @returns {Object} Switch result
     */
    handleModeSwitch(newMode, options = {}) {
        const switchOptions = {
            preserveExisting: options.preserveExisting !== false,
            validateTransition: options.validateTransition !== false,
            items: options.items || [],
            ...options
        };

        this._log('Handling mode switch', { 
            from: this.currentMode, 
            to: newMode, 
            options: switchOptions 
        });

        const switchResult = {
            success: false,
            fromMode: this.currentMode,
            toMode: newMode,
            preservedItems: [],
            errors: [],
            timestamp: Date.now()
        };

        try {
            // Validate transition if requested
            if (switchOptions.validateTransition) {
                const validation = this.validateModeTransition(
                    this.currentMode, 
                    newMode, 
                    switchOptions.items
                );
                
                if (!validation.isValid) {
                    switchResult.errors = validation.errors;
                    this._logError('Mode switch validation failed', validation);
                    return switchResult;
                }
            }

            // Preserve existing items if requested
            if (switchOptions.preserveExisting && this.mediaState.unified.length > 0) {
                switchResult.preservedItems = this.preserveExistingItems(
                    this.mediaState.unified,
                    switchOptions.items,
                    switchOptions
                );
            } else {
                switchResult.preservedItems = [...switchOptions.items];
            }

            // Update mode state
            this.previousMode = this.currentMode;
            this.currentMode = newMode;

            // Record transition
            this.transitionHistory.push({
                from: this.previousMode,
                to: this.currentMode,
                timestamp: Date.now(),
                itemCount: switchResult.preservedItems.length,
                preserved: switchOptions.preserveExisting
            });

            switchResult.success = true;

            this._log('Mode switch completed successfully', switchResult);

            return switchResult;

        } catch (error) {
            switchResult.errors.push(error.message);
            this._logError('Error during mode switch', error);
            return switchResult;
        }
    }

    /**
     * Preserve local items when switching to unified mode
     * @param {Array} localItems - Local media items to preserve
     * @param {Array} remoteItems - Remote items to add
     * @param {Object} options - Preservation options
     * @returns {Array} Unified results with local items preserved
     */
    preserveLocalItemsInUnified(localItems = [], remoteItems = [], options = {}) {
        const preserveOptions = {
            enforceLocalPriority: options.enforceLocalPriority !== false,
            enhanceWithRemote: options.enhanceWithRemote !== false,
            validateConsistency: options.validateConsistency !== false,
            ...options
        };

        this._log('Preserving local items in unified mode', {
            localCount: localItems.length,
            remoteCount: remoteItems.length,
            options: preserveOptions
        });

        // Validate inputs
        if (!Array.isArray(localItems)) localItems = [];
        if (!Array.isArray(remoteItems)) remoteItems = [];

        try {
            // Start with all local items (they have priority)
            const unified = [...localItems];
            
            // Create map of local items for quick lookup
            const localMap = new Map();
            localItems.forEach(item => {
                const key = this._getItemKey(item, 'id');
                if (key) localMap.set(key, item);
            });

            // Add remote items that don't conflict with local items
            remoteItems.forEach(remoteItem => {
                const key = this._getItemKey(remoteItem, 'id');
                
                if (!key) {
                    // Remote item without valid key - add it
                    unified.push(remoteItem);
                } else if (!localMap.has(key)) {
                    // Remote item not in local - add it
                    unified.push(remoteItem);
                } else if (preserveOptions.enhanceWithRemote) {
                    // Enhance local item with remote data
                    const localIndex = unified.findIndex(item => 
                        this._getItemKey(item, 'id') === key
                    );
                    if (localIndex >= 0) {
                        unified[localIndex] = this._enhanceItem(unified[localIndex], remoteItem);
                    }
                }
            });

            // Validate consistency if requested
            if (preserveOptions.validateConsistency) {
                const validation = this._validateUnifiedConsistency(localItems, remoteItems, unified);
                if (!validation.isValid) {
                    this._logError('Unified consistency validation failed', validation.errors);
                }
            }

            this._log('Local items preserved in unified mode', {
                unifiedCount: unified.length,
                localPreserved: this._countPreservedLocal(unified, localItems),
                remoteAdded: unified.length - localItems.length
            });

            return unified;

        } catch (error) {
            this._logError('Error preserving local items in unified mode', error);
            // Fallback to local items only
            return [...localItems];
        }
    }

    /**
     * Validate that remote items are additive, not replacement
     * @param {Array} existingItems - Currently displayed items
     * @param {Array} newRemoteItems - New remote items to validate
     * @returns {Object} Validation result
     */
    validateRemoteItemsAdditive(existingItems = [], newRemoteItems = []) {
        const validation = {
            isValid: true,
            isAdditive: true,
            errors: [],
            warnings: [],
            stats: {
                existingCount: 0,
                newRemoteCount: 0,
                conflictCount: 0,
                additiveCount: 0
            },
            timestamp: Date.now()
        };

        this._log('Validating remote items are additive', {
            existingCount: existingItems.length,
            newRemoteCount: newRemoteItems.length
        });

        try {
            // Validate inputs
            if (!Array.isArray(existingItems)) {
                validation.errors.push('Existing items must be an array');
                existingItems = [];
            }
            if (!Array.isArray(newRemoteItems)) {
                validation.errors.push('New remote items must be an array');
                newRemoteItems = [];
            }

            validation.stats.existingCount = existingItems.length;
            validation.stats.newRemoteCount = newRemoteItems.length;

            // Create map of existing items
            const existingMap = new Map();
            existingItems.forEach(item => {
                const key = this._getItemKey(item, 'id');
                if (key) existingMap.set(key, item);
            });

            // Check each remote item
            newRemoteItems.forEach(remoteItem => {
                const key = this._getItemKey(remoteItem, 'id');
                
                if (!key) {
                    validation.warnings.push('Remote item without valid ID found');
                    return;
                }

                if (existingMap.has(key)) {
                    validation.stats.conflictCount++;
                    // This is okay - it's enhancement, not replacement
                } else {
                    validation.stats.additiveCount++;
                }
            });

            // Determine if remote items are truly additive
            const totalExpected = validation.stats.existingCount + validation.stats.additiveCount;
            validation.isAdditive = validation.stats.conflictCount === 0 || 
                                   validation.stats.additiveCount > 0;

            if (!validation.isAdditive) {
                validation.errors.push('Remote items appear to be replacement rather than additive');
                validation.isValid = false;
            }

            this._log('Remote items additivity validation completed', validation);

            return validation;

        } catch (error) {
            validation.errors.push(`Validation error: ${error.message}`);
            validation.isValid = false;
            this._logError('Error validating remote items additivity', error);
            return validation;
        }
    }

    /**
     * Check consistency of media item properties across modes
     * @param {Array} localItems - Local mode items
     * @param {Array} remoteItems - Remote mode items  
     * @param {Array} unifiedItems - Unified mode items
     * @returns {Object} Consistency check result
     */
    validateMediaItemConsistency(localItems = [], remoteItems = [], unifiedItems = []) {
        const consistency = {
            isConsistent: true,
            errors: [],
            warnings: [],
            stats: {
                localCount: 0,
                remoteCount: 0,
                unifiedCount: 0,
                missingInUnified: 0,
                extraInUnified: 0,
                propertyMismatches: 0
            },
            details: {
                missingItems: [],
                extraItems: [],
                propertyMismatches: []
            },
            timestamp: Date.now()
        };

        this._log('Validating media item consistency across modes', {
            localCount: localItems.length,
            remoteCount: remoteItems.length,
            unifiedCount: unifiedItems.length
        });

        try {
            // Validate inputs
            if (!Array.isArray(localItems)) localItems = [];
            if (!Array.isArray(remoteItems)) remoteItems = [];
            if (!Array.isArray(unifiedItems)) unifiedItems = [];

            consistency.stats.localCount = localItems.length;
            consistency.stats.remoteCount = remoteItems.length;
            consistency.stats.unifiedCount = unifiedItems.length;

            // Create maps for comparison
            const localMap = new Map();
            const remoteMap = new Map();
            const unifiedMap = new Map();

            localItems.forEach(item => {
                const key = this._getItemKey(item, 'id');
                if (key) localMap.set(key, item);
            });

            remoteItems.forEach(item => {
                const key = this._getItemKey(item, 'id');
                if (key) remoteMap.set(key, item);
            });

            unifiedItems.forEach(item => {
                const key = this._getItemKey(item, 'id');
                if (key) unifiedMap.set(key, item);
            });

            // Check that all local items appear in unified
            localItems.forEach(localItem => {
                const key = this._getItemKey(localItem, 'id');
                if (key && !unifiedMap.has(key)) {
                    consistency.stats.missingInUnified++;
                    consistency.details.missingItems.push({
                        id: key,
                        source: 'local',
                        item: localItem
                    });
                    consistency.errors.push(`Local item ${key} missing from unified results`);
                }
            });

            // Check for property consistency between modes
            unifiedItems.forEach(unifiedItem => {
                const key = this._getItemKey(unifiedItem, 'id');
                if (!key) return;

                const localItem = localMap.get(key);
                const remoteItem = remoteMap.get(key);

                if (localItem) {
                    const mismatch = this._checkPropertyConsistency(localItem, unifiedItem, 'local');
                    if (mismatch) {
                        consistency.stats.propertyMismatches++;
                        consistency.details.propertyMismatches.push(mismatch);
                    }
                }

                if (remoteItem && !localItem) {
                    const mismatch = this._checkPropertyConsistency(remoteItem, unifiedItem, 'remote');
                    if (mismatch) {
                        consistency.stats.propertyMismatches++;
                        consistency.details.propertyMismatches.push(mismatch);
                    }
                }
            });

            // Determine overall consistency
            consistency.isConsistent = consistency.errors.length === 0 && 
                                     consistency.stats.missingInUnified === 0;

            if (consistency.stats.propertyMismatches > 0) {
                consistency.warnings.push(`${consistency.stats.propertyMismatches} property mismatches found`);
            }

            this._log('Media item consistency validation completed', consistency);

            return consistency;

        } catch (error) {
            consistency.errors.push(`Consistency validation error: ${error.message}`);
            consistency.isConsistent = false;
            this._logError('Error validating media item consistency', error);
            return consistency;
        }
    }

    /**
     * Get current consistency state
     * @returns {Object} Current consistency state
     */
    getConsistencyState() {
        return {
            currentMode: this.currentMode,
            previousMode: this.previousMode,
            mediaState: { ...this.mediaState },
            transitionHistory: [...this.transitionHistory],
            lastCheck: this.mediaState.consistencyChecks.slice(-1)[0] || null
        };
    }

    // Private helper methods

    /**
     * Additive merge strategy - adds remote items to local items
     * @private
     */
    _mergeAdditive(localItems, remoteItems, options) {
        const result = [...localItems];
        const dedupeKey = options.deduplicateBy;

        // Create map of local items for deduplication
        const localMap = new Map();
        localItems.forEach(item => {
            const key = this._getItemKey(item, dedupeKey);
            if (key) localMap.set(key, item);
        });

        // Add remote items that don't exist locally
        remoteItems.forEach(remoteItem => {
            const key = this._getItemKey(remoteItem, dedupeKey);
            if (!key || !localMap.has(key)) {
                result.push(remoteItem);
            } else if (options.enhanceLocal) {
                // Enhance local item with remote data
                const localIndex = result.findIndex(item => 
                    this._getItemKey(item, dedupeKey) === key
                );
                if (localIndex >= 0) {
                    result[localIndex] = this._enhanceItem(result[localIndex], remoteItem);
                }
            }
        });

        return result;
    }

    /**
     * Replace merge strategy - replaces local items with combined results
     * @private
     */
    _mergeReplace(localItems, remoteItems, options) {
        if (!options.preserveLocal) {
            return [...remoteItems];
        }

        // Combine and deduplicate
        const combined = [...localItems, ...remoteItems];
        return this._deduplicateItems(combined, options.deduplicateBy);
    }

    /**
     * Enhance merge strategy - enhances local items with remote data
     * @private
     */
    _mergeEnhance(localItems, remoteItems, options) {
        const result = [...localItems];
        const dedupeKey = options.deduplicateBy;

        // Create map of remote items
        const remoteMap = new Map();
        remoteItems.forEach(item => {
            const key = this._getItemKey(item, dedupeKey);
            if (key) remoteMap.set(key, item);
        });

        // Enhance local items with remote data
        result.forEach((localItem, index) => {
            const key = this._getItemKey(localItem, dedupeKey);
            if (key && remoteMap.has(key)) {
                result[index] = this._enhanceItem(localItem, remoteMap.get(key));
            }
        });

        // Add remote-only items
        remoteItems.forEach(remoteItem => {
            const key = this._getItemKey(remoteItem, dedupeKey);
            const existsLocally = result.some(item => 
                this._getItemKey(item, dedupeKey) === key
            );
            if (!existsLocally) {
                result.push(remoteItem);
            }
        });

        return result;
    }

    /**
     * Get item key for deduplication
     * @private
     */
    _getItemKey(item, keyField) {
        if (!item || typeof item !== 'object') return null;
        
        if (keyField === 'id') {
            return item.id || item.Id || item.ID || null;
        } else if (keyField === 'path') {
            return item.path || item.Path || item.file_path || null;
        } else if (keyField === 'name') {
            return item.name || item.Name || item.title || item.Title || null;
        }
        
        return item[keyField] || null;
    }

    /**
     * Enhance item with additional properties
     * @private
     */
    _enhanceItem(baseItem, enhancementItem) {
        if (!baseItem || !enhancementItem) return baseItem;

        // Create enhanced item preserving base item properties
        const enhanced = { ...baseItem };

        // Add non-conflicting properties from enhancement
        Object.keys(enhancementItem).forEach(key => {
            if (!(key in enhanced) || enhanced[key] === null || enhanced[key] === undefined) {
                enhanced[key] = enhancementItem[key];
            }
        });

        // Mark as enhanced
        enhanced._enhanced = true;
        enhanced._enhancedAt = Date.now();

        return enhanced;
    }

    /**
     * Deduplicate items array
     * @private
     */
    _deduplicateItems(items, keyField) {
        const seen = new Map();
        const result = [];

        items.forEach(item => {
            const key = this._getItemKey(item, keyField);
            if (key && !seen.has(key)) {
                seen.set(key, true);
                result.push(item);
            } else if (!key) {
                // Include items without valid keys
                result.push(item);
            }
        });

        return result;
    }

    /**
     * Validate media item structure
     * @private
     */
    _isValidMediaItem(item) {
        if (!item || typeof item !== 'object') return false;
        
        // Check for required properties
        const hasId = item.id || item.Id || item.ID;
        const hasName = item.name || item.Name || item.title || item.Title;
        
        return !!(hasId || hasName);
    }

    /**
     * Count preserved local items
     * @private
     */
    _countPreservedLocal(mergedResults, localItems) {
        if (!Array.isArray(localItems) || !Array.isArray(mergedResults)) return 0;
        
        return localItems.filter(localItem => {
            const localKey = this._getItemKey(localItem, 'id');
            return mergedResults.some(merged => 
                this._getItemKey(merged, 'id') === localKey
            );
        }).length;
    }

    /**
     * Count added remote items
     * @private
     */
    _countAddedRemote(mergedResults, localItems) {
        if (!Array.isArray(localItems) || !Array.isArray(mergedResults)) return 0;
        
        const localKeys = new Set(localItems.map(item => this._getItemKey(item, 'id')).filter(Boolean));
        
        return mergedResults.filter(merged => {
            const mergedKey = this._getItemKey(merged, 'id');
            return mergedKey && !localKeys.has(mergedKey);
        }).length;
    }

    /**
     * Log message if logging is enabled
     * @private
     */
    _log(message, data = null) {
        if (this.options.enableLogging) {
            console.log(`ModeConsistencyManager: ${message}`, data || '');
        }
    }

    /**
     * Validate unified consistency
     * @private
     */
    _validateUnifiedConsistency(localItems, remoteItems, unifiedItems) {
        const validation = {
            isValid: true,
            errors: [],
            warnings: []
        };

        // Check that all local items are preserved
        const localKeys = new Set(localItems.map(item => this._getItemKey(item, 'id')).filter(Boolean));
        const unifiedKeys = new Set(unifiedItems.map(item => this._getItemKey(item, 'id')).filter(Boolean));

        localKeys.forEach(localKey => {
            if (!unifiedKeys.has(localKey)) {
                validation.errors.push(`Local item ${localKey} not preserved in unified results`);
                validation.isValid = false;
            }
        });

        // Check that unified count is reasonable
        const expectedMinCount = localItems.length;
        const expectedMaxCount = localItems.length + remoteItems.length;
        
        if (unifiedItems.length < expectedMinCount) {
            validation.errors.push(`Unified count ${unifiedItems.length} is less than local count ${localItems.length}`);
            validation.isValid = false;
        }

        if (unifiedItems.length > expectedMaxCount) {
            validation.warnings.push(`Unified count ${unifiedItems.length} exceeds expected maximum ${expectedMaxCount}`);
        }

        return validation;
    }

    /**
     * Check property consistency between items
     * @private
     */
    _checkPropertyConsistency(sourceItem, targetItem, sourceType) {
        const criticalProperties = ['id', 'name', 'title', 'path', 'type'];
        const mismatches = [];

        criticalProperties.forEach(prop => {
            const sourceValue = sourceItem[prop] || sourceItem[prop.charAt(0).toUpperCase() + prop.slice(1)];
            const targetValue = targetItem[prop] || targetItem[prop.charAt(0).toUpperCase() + prop.slice(1)];

            if (sourceValue && targetValue && sourceValue !== targetValue) {
                mismatches.push({
                    property: prop,
                    sourceValue,
                    targetValue,
                    sourceType
                });
            }
        });

        if (mismatches.length > 0) {
            return {
                itemId: this._getItemKey(sourceItem, 'id'),
                sourceType,
                mismatches
            };
        }

        return null;
    }

    /**
     * Log message if logging is enabled
     * @private
     */
    _log(message, data = null) {
        if (this.options.enableLogging) {
            console.log(`ModeConsistencyManager: ${message}`, data || '');
        }
    }

    /**
     * Log error message
     * @private
     */
    _logError(message, error = null) {
        console.error(`ModeConsistencyManager Error: ${message}`, error || '');
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ModeConsistencyManager;
}