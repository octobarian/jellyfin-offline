/**
 * Test suite for ProgressiveMediaLoader
 * Basic tests to verify functionality
 */

class ProgressiveLoaderTest {
    constructor() {
        this.testResults = [];
    }

    async runAllTests() {
        console.log('Starting ProgressiveMediaLoader tests...');
        
        await this.testBasicInstantiation();
        await this.testCallbackSetup();
        await this.testMergeMediaLists();
        await this.testLoadingStates();
        
        this.printResults();
        return this.testResults;
    }

    async testBasicInstantiation() {
        try {
            const loader = new ProgressiveMediaLoader();
            this.assert(loader instanceof ProgressiveMediaLoader, 'ProgressiveMediaLoader instantiation');
            this.assert(Array.isArray(loader.localMedia), 'localMedia is array');
            this.assert(Array.isArray(loader.remoteMedia), 'remoteMedia is array');
            this.assert(Array.isArray(loader.unifiedMedia), 'unifiedMedia is array');
            this.assert(typeof loader.loadingStates === 'object', 'loadingStates is object');
        } catch (error) {
            this.fail('Basic instantiation', error.message);
        }
    }

    async testCallbackSetup() {
        try {
            const loader = new ProgressiveMediaLoader();
            const callbacks = {
                onLocalLoaded: () => {},
                onRemoteLoaded: () => {},
                onComplete: () => {},
                onError: () => {}
            };
            
            loader.setCallbacks(callbacks);
            this.assert(loader.callbacks.onLocalLoaded === callbacks.onLocalLoaded, 'onLocalLoaded callback set');
            this.assert(loader.callbacks.onRemoteLoaded === callbacks.onRemoteLoaded, 'onRemoteLoaded callback set');
            this.assert(loader.callbacks.onComplete === callbacks.onComplete, 'onComplete callback set');
            this.assert(loader.callbacks.onError === callbacks.onError, 'onError callback set');
        } catch (error) {
            this.fail('Callback setup', error.message);
        }
    }

    async testMergeMediaLists() {
        try {
            const loader = new ProgressiveMediaLoader();
            
            const localMedia = [
                { id: '1', title: 'Local Movie 1', has_local: true, availability: 'local_only' },
                { id: '2', title: 'Local Movie 2', has_local: true, availability: 'local_only' }
            ];
            
            const remoteMedia = [
                { id: '2', title: 'Remote Movie 2', has_remote: true, availability: 'remote_only' },
                { id: '3', title: 'Remote Movie 3', has_remote: true, availability: 'remote_only' }
            ];
            
            const merged = loader.mergeMediaLists(localMedia, remoteMedia);
            
            this.assert(merged.length === 3, 'Merged list has correct length');
            
            // Check that item 2 was merged (should have both local and remote)
            const mergedItem2 = merged.find(item => item.id === '2');
            this.assert(mergedItem2.has_local === true, 'Merged item has local flag');
            this.assert(mergedItem2.has_remote === true, 'Merged item has remote flag');
            this.assert(mergedItem2.availability === 'both', 'Merged item availability is both');
            
            // Check that item 1 remains local-only
            const item1 = merged.find(item => item.id === '1');
            this.assert(item1.availability === 'local_only', 'Local-only item preserved');
            
            // Check that item 3 is remote-only
            const item3 = merged.find(item => item.id === '3');
            this.assert(item3.availability === 'remote_only', 'Remote-only item added');
            
        } catch (error) {
            this.fail('Merge media lists', error.message);
        }
    }

    async testLoadingStates() {
        try {
            const loader = new ProgressiveMediaLoader();
            
            const initialState = loader.getLoadingState();
            this.assert(initialState.local === false, 'Initial local state is false');
            this.assert(initialState.remote === false, 'Initial remote state is false');
            this.assert(initialState.complete === false, 'Initial complete state is false');
            
            // Test state changes during loading simulation
            loader.loadingStates.local = true;
            const localLoadingState = loader.getLoadingState();
            this.assert(localLoadingState.local === true, 'Local loading state updated');
            
        } catch (error) {
            this.fail('Loading states', error.message);
        }
    }

    assert(condition, testName) {
        if (condition) {
            this.testResults.push({ test: testName, status: 'PASS' });
            console.log(`✅ ${testName}`);
        } else {
            this.testResults.push({ test: testName, status: 'FAIL', error: 'Assertion failed' });
            console.log(`❌ ${testName} - Assertion failed`);
        }
    }

    fail(testName, error) {
        this.testResults.push({ test: testName, status: 'FAIL', error });
        console.log(`❌ ${testName} - ${error}`);
    }

    printResults() {
        const passed = this.testResults.filter(r => r.status === 'PASS').length;
        const failed = this.testResults.filter(r => r.status === 'FAIL').length;
        
        console.log('\n=== Test Results ===');
        console.log(`Passed: ${passed}`);
        console.log(`Failed: ${failed}`);
        console.log(`Total: ${this.testResults.length}`);
        
        if (failed > 0) {
            console.log('\nFailed tests:');
            this.testResults
                .filter(r => r.status === 'FAIL')
                .forEach(r => console.log(`- ${r.test}: ${r.error}`));
        }
    }
}

// Run tests when script loads (if in test environment)
if (typeof ProgressiveMediaLoader !== 'undefined') {
    // Auto-run tests in development
    if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
        document.addEventListener('DOMContentLoaded', async function() {
            const tester = new ProgressiveLoaderTest();
            await tester.runAllTests();
        });
    }
}

// Export for manual testing
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ProgressiveLoaderTest;
}

// Make available globally for manual testing
window.ProgressiveLoaderTest = ProgressiveLoaderTest;