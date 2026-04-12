"""
Main Controller

Handles the main web interface routes for the RV Media Player.
Provides the media library interface and static file serving.
"""
from flask import Blueprint, render_template, current_app, request, jsonify
import logging

main_bp = Blueprint('main', __name__)
logger = logging.getLogger(__name__)


@main_bp.route('/')
def index():
    """
    Main media library interface.
    
    Returns:
        Rendered HTML template for the media library
    """
    try:
        logger.info("Serving main media library interface")
        
        # Get media manager from app config
        media_manager = current_app.config.get('MEDIA_MANAGER')
        if not media_manager:
            logger.error("Media manager not available")
            return render_template('error.html',
                                 error_code=503,
                                 error_message="Media services not available"), 503
        
        # Get basic system status for the template
        try:
            # Quick connectivity check
            jellyfin_status = media_manager.jellyfin_service.test_connection()
            jellyfin_connected = jellyfin_status.connected if hasattr(jellyfin_status, 'connected') else bool(jellyfin_status)
            vlc_available = media_manager.vlc_controller.is_vlc_installed()
            
            system_status = {
                'jellyfin_connected': jellyfin_connected,
                'vlc_available': vlc_available,
                'services_ready': True
            }
        except Exception as e:
            logger.warning(f"Error checking system status: {e}")
            system_status = {
                'jellyfin_connected': False,
                'vlc_available': False,
                'services_ready': False
            }
        
        return render_template('index.html', system_status=system_status)
        
    except Exception as e:
        logger.error(f"Error serving main interface: {e}")
        return render_template('error.html',
                             error_code=500,
                             error_message="Failed to load media library"), 500


@main_bp.route('/health')
def health_check():
    """
    Health check endpoint for monitoring.
    
    Returns:
        JSON response with system health status
    """
    try:
        media_manager = current_app.config.get('MEDIA_MANAGER')
        config = current_app.config.get('MEDIA_CONFIG')
        
        health_status = {
            'status': 'healthy',
            'timestamp': None,
            'services': {
                'media_manager': media_manager is not None,
                'configuration': config is not None,
                'jellyfin': False,
                'vlc': False,
                'local_media': False
            }
        }
        
        if media_manager:
            try:
                # Test individual services
                jellyfin_status = media_manager.jellyfin_service.test_connection()
                health_status['services']['jellyfin'] = jellyfin_status.connected if hasattr(jellyfin_status, 'connected') else bool(jellyfin_status)
                health_status['services']['vlc'] = media_manager.vlc_controller.is_vlc_installed()
                
                # Test local media service
                local_media = media_manager.local_service.get_local_media()
                health_status['services']['local_media'] = True
                
            except Exception as e:
                logger.warning(f"Error checking service health: {e}")
                health_status['status'] = 'degraded'
        else:
            health_status['status'] = 'unhealthy'
        
        import time
        health_status['timestamp'] = time.time()
        
        status_code = 200 if health_status['status'] == 'healthy' else 503
        return jsonify(health_status), status_code
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e),
            'timestamp': time.time()
        }), 500


@main_bp.route('/about')
def about():
    """
    About page with application information.
    
    Returns:
        Rendered HTML template with application info
    """
    try:
        app_info = {
            'name': 'RV Media Player',
            'version': '1.0.0',
            'description': 'Unified media player for RV environments with offline/online support'
        }
        
        return render_template('about.html', app_info=app_info)
        
    except Exception as e:
        logger.error(f"Error serving about page: {e}")
        return render_template('error.html',
                             error_code=500,
                             error_message="Failed to load about page"), 500