/**
 * RV Media Player - Responsive JavaScript Utilities
 * Touch-optimized utilities for responsive web interface
 */

class ResponsiveUtils {
    constructor() {
        this.init();
    }

    init() {
        this.setupTouchHandlers();
        this.setupViewportHandler();
        this.setupAccessibility();
        this.setupOverlayManager();
    }

    /**
     * Setup touch-optimized event handlers
     */
    setupTouchHandlers() {
        // Add touch feedback for buttons
        document.addEventListener('touchstart', (e) => {
            if (e.target.classList.contains('btn') || e.target.closest('.btn')) {
                const btn = e.target.classList.contains('btn') ? e.target : e.target.closest('.btn');
                btn.style.transform = 'scale(0.98)';
            }
        });

        document.addEventListener('touchend', (e) => {
            if (e.target.classList.contains('btn') || e.target.closest('.btn')) {
                const btn = e.target.classList.contains('btn') ? e.target : e.target.closest('.btn');
                setTimeout(() => {
                    btn.style.transform = '';
                }, 100);
            }
        });

        // Prevent double-tap zoom on buttons
        document.addEventListener('touchend', (e) => {
            if (e.target.classList.contains('btn') || e.target.closest('.btn')) {
                e.preventDefault();
            }
        });
    }

    /**
     * Handle viewport changes and orientation
     */
    setupViewportHandler() {
        const handleViewportChange = () => {
            // Update CSS custom properties for viewport dimensions
            document.documentElement.style.setProperty('--vh', `${window.innerHeight * 0.01}px`);
            document.documentElement.style.setProperty('--vw', `${window.innerWidth * 0.01}px`);
            
            // Dispatch custom event for components to respond to viewport changes
            window.dispatchEvent(new CustomEvent('viewportchange', {
                detail: {
                    width: window.innerWidth,
                    height: window.innerHeight,
                    orientation: window.innerWidth > window.innerHeight ? 'landscape' : 'portrait'
                }
            }));
        };

        window.addEventListener('resize', handleViewportChange);
        window.addEventListener('orientationchange', () => {
            setTimeout(handleViewportChange, 100);
        });
        
        // Initial call
        handleViewportChange();
    }

    /**
     * Setup accessibility features
     */
    setupAccessibility() {
        // Add focus management for keyboard navigation
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Tab') {
                document.body.classList.add('keyboard-navigation');
            }
        });

        document.addEventListener('mousedown', () => {
            document.body.classList.remove('keyboard-navigation');
        });

        // Add skip links for screen readers
        this.addSkipLinks();
    }

    /**
     * Add skip navigation links for accessibility
     */
    addSkipLinks() {
        const skipLink = document.createElement('a');
        skipLink.href = '#main-content';
        skipLink.textContent = 'Skip to main content';
        skipLink.className = 'skip-link';
        skipLink.style.cssText = `
            position: absolute;
            top: -40px;
            left: 6px;
            background: #4CAF50;
            color: white;
            padding: 8px;
            text-decoration: none;
            border-radius: 4px;
            z-index: 10000;
            transition: top 0.3s;
        `;

        skipLink.addEventListener('focus', () => {
            skipLink.style.top = '6px';
        });

        skipLink.addEventListener('blur', () => {
            skipLink.style.top = '-40px';
        });

        document.body.insertBefore(skipLink, document.body.firstChild);
    }

    /**
     * Overlay management system
     */
    setupOverlayManager() {
        this.overlayStack = [];
        
        // Close overlay on escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.overlayStack.length > 0) {
                this.closeTopOverlay();
            }
        });

        // Close overlay on backdrop click
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('overlay')) {
                this.closeOverlay(e.target);
            }
        });
    }

    /**
     * Show an overlay
     */
    showOverlay(overlayElement) {
        if (!overlayElement) return;

        // Add to stack
        this.overlayStack.push(overlayElement);
        
        // Prevent body scroll
        document.body.style.overflow = 'hidden';
        
        // Show overlay
        overlayElement.classList.add('active');
        
        // Focus management
        const focusableElements = overlayElement.querySelectorAll(
            'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        
        if (focusableElements.length > 0) {
            focusableElements[0].focus();
        }

        // Dispatch event
        overlayElement.dispatchEvent(new CustomEvent('overlay:shown'));
    }

    /**
     * Close an overlay
     */
    closeOverlay(overlayElement) {
        if (!overlayElement) return;

        // Remove from stack
        const index = this.overlayStack.indexOf(overlayElement);
        if (index > -1) {
            this.overlayStack.splice(index, 1);
        }

        // Hide overlay
        overlayElement.classList.remove('active');

        // Restore body scroll if no overlays remain
        if (this.overlayStack.length === 0) {
            document.body.style.overflow = '';
        }

        // Dispatch event
        overlayElement.dispatchEvent(new CustomEvent('overlay:hidden'));
    }

    /**
     * Close the topmost overlay
     */
    closeTopOverlay() {
        if (this.overlayStack.length > 0) {
            this.closeOverlay(this.overlayStack[this.overlayStack.length - 1]);
        }
    }

    /**
     * Detect if device supports touch
     */
    static isTouchDevice() {
        return 'ontouchstart' in window || navigator.maxTouchPoints > 0;
    }

    /**
     * Get current breakpoint
     */
    static getCurrentBreakpoint() {
        const width = window.innerWidth;
        if (width < 576) return 'xs';
        if (width < 768) return 'sm';
        if (width < 992) return 'md';
        return 'lg';
    }

    /**
     * Debounce utility function
     */
    static debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    /**
     * Throttle utility function
     */
    static throttle(func, limit) {
        let inThrottle;
        return function(...args) {
            if (!inThrottle) {
                func.apply(this, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    }
}

/**
 * Toast notification system
 */
class ToastManager {
    constructor() {
        this.container = null;
        this.init();
    }

    init() {
        this.createContainer();
    }

    createContainer() {
        this.container = document.createElement('div');
        this.container.className = 'toast-container';
        this.container.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 10000;
            display: flex;
            flex-direction: column;
            gap: 12px;
            max-width: 400px;
        `;
        document.body.appendChild(this.container);
    }

    show(message, type = 'info', duration = 5000) {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        
        const colors = {
            success: '#4CAF50',
            error: '#f44336',
            warning: '#ff9800',
            info: '#2196F3'
        };

        toast.style.cssText = `
            background-color: ${colors[type] || colors.info};
            color: white;
            padding: 16px 20px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
            transform: translateX(100%);
            transition: transform 0.3s ease;
            cursor: pointer;
            font-size: 14px;
            line-height: 1.4;
        `;

        toast.textContent = message;

        // Add close functionality
        toast.addEventListener('click', () => {
            this.hide(toast);
        });

        this.container.appendChild(toast);

        // Animate in
        setTimeout(() => {
            toast.style.transform = 'translateX(0)';
        }, 10);

        // Auto-hide
        if (duration > 0) {
            setTimeout(() => {
                this.hide(toast);
            }, duration);
        }

        return toast;
    }

    hide(toast) {
        toast.style.transform = 'translateX(100%)';
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 300);
    }
}

/**
 * Loading indicator utility
 */
class LoadingManager {
    constructor() {
        this.overlay = null;
        this.init();
    }

    init() {
        this.createOverlay();
    }

    createOverlay() {
        this.overlay = document.createElement('div');
        this.overlay.className = 'loading-overlay';
        this.overlay.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background-color: rgba(0, 0, 0, 0.8);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 9999;
            opacity: 0;
            visibility: hidden;
            transition: all 0.3s ease;
        `;

        const spinner = document.createElement('div');
        spinner.style.cssText = `
            width: 40px;
            height: 40px;
            border: 4px solid #333;
            border-top: 4px solid #4CAF50;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        `;

        // Add spinner animation
        const style = document.createElement('style');
        style.textContent = `
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
        `;
        document.head.appendChild(style);

        this.overlay.appendChild(spinner);
        document.body.appendChild(this.overlay);
    }

    show() {
        this.overlay.style.opacity = '1';
        this.overlay.style.visibility = 'visible';
        document.body.style.overflow = 'hidden';
    }

    hide() {
        this.overlay.style.opacity = '0';
        this.overlay.style.visibility = 'hidden';
        document.body.style.overflow = '';
    }
}

// Initialize utilities when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.responsiveUtils = new ResponsiveUtils();
    window.toastManager = new ToastManager();
    window.loadingManager = new LoadingManager();
    
    // Add body class for touch devices
    if (ResponsiveUtils.isTouchDevice()) {
        document.body.classList.add('touch-device');
    }
    
    // Add current breakpoint class
    const updateBreakpointClass = () => {
        document.body.className = document.body.className.replace(/breakpoint-\w+/g, '');
        document.body.classList.add(`breakpoint-${ResponsiveUtils.getCurrentBreakpoint()}`);
    };
    
    updateBreakpointClass();
    window.addEventListener('resize', ResponsiveUtils.debounce(updateBreakpointClass, 250));
});

// Export for module use
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { ResponsiveUtils, ToastManager, LoadingManager };
}
