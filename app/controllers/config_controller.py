"""
Configuration Controller

Handles configuration management endpoints for the RV Media Player.
Provides secure configuration viewing and updating capabilities.
"""
from flask import Blueprint, jsonify, request, render_template, current_app
import logging
import os
from typing import Dict, Any

from config.configuration import Configuration

config_bp = Blueprint('config', __name__)
logger = logging.getLogger(__name__)


@config_bp.route('/')
def config_interface():
    """
    Configuration management interface.
    
    Returns:
        Rendered HTML template for configuration management
    """
    try:
        logger.info("Serving configuration interface")
        
        config = current_app.config.get('MEDIA_CONFIG')
        if not config:
            logger.warning("No configuration available")
            config = Configuration()  # Default configuration
        
        # Prepare configuration data for template (sanitized)
        config_data = {
            'jellyfin_server_url': config.jellyfin_server_url or '',
            'jellyfin_username': config.jellyfin_username or '',
            'jellyfin_api_key': '***' if config.jellyfin_api_key else '',
            'local_media_paths': config.local_media_paths or [],
            'download_directory': config.download_directory or 'media/downloads',
            'vlc_path': config.vlc_path or '',
            'auto_launch': config.auto_launch,
            'fullscreen_browser': config.fullscreen_browser
        }
        
        return render_template('config.html', config=config_data)
        
    except Exception as e:
        logger.error(f"Error serving configuration interface: {e}")
        return render_template('error.html',
                             error_code=500,
                             error_message="Failed to load configuration"), 500


@config_bp.route('/api/current')
def get_current_config():
    """
    Get current configuration (sanitized for security).
    
    Returns:
        JSON response with current configuration
    """
    try:
        config = current_app.config.get('MEDIA_CONFIG')
        if not config:
            return jsonify({'error': 'Configuration not available'}), 503
        
        # Return sanitized configuration (no sensitive data)
        config_data = {
            'jellyfin_server_url': config.jellyfin_server_url or '',
            'jellyfin_username': config.jellyfin_username or '',
            'has_jellyfin_api_key': bool(config.jellyfin_api_key),
            'local_media_paths': config.local_media_paths or [],
            'download_directory': config.download_directory or 'media/downloads',
            'vlc_path': config.vlc_path or '',
            'auto_launch': config.auto_launch,
            'fullscreen_browser': config.fullscreen_browser
        }
        
        return jsonify(config_data)
        
    except Exception as e:
        logger.error(f"Error getting current configuration: {e}")
        return jsonify({
            'error': 'Failed to retrieve configuration',
            'message': str(e)
        }), 500


@config_bp.route('/api/update', methods=['POST'])
def update_config():
    """
    Update application configuration.
    
    JSON Body:
        Configuration fields to update
        
    Returns:
        JSON response with update status
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No configuration data provided'}), 400
        
        logger.info(f"Updating configuration with data: {list(data.keys())}")
        logger.info(f"Jellyfin data received: server_url={data.get('jellyfin_server_url', 'NOT_PROVIDED')}, username={data.get('jellyfin_username', 'NOT_PROVIDED')}, api_key={'PROVIDED' if data.get('jellyfin_api_key') else 'NOT_PROVIDED'}")
        
        # Get current configuration
        current_config = current_app.config.get('MEDIA_CONFIG')
        if not current_config:
            current_config = Configuration()
        
        # Validate and update configuration fields
        updated_fields = []
        
        if 'jellyfin_server_url' in data:
            url = data['jellyfin_server_url'].strip()
            if url and not url.startswith(('http://', 'https://')):
                return jsonify({'error': 'Jellyfin server URL must start with http:// or https://'}), 400
            current_config.jellyfin_server_url = url
            updated_fields.append('jellyfin_server_url')
        
        if 'jellyfin_username' in data:
            current_config.jellyfin_username = data['jellyfin_username'].strip()
            updated_fields.append('jellyfin_username')
        
        if 'jellyfin_api_key' in data:
            api_key = data['jellyfin_api_key'].strip()
            # Only update if we have a real API key (not empty, not placeholder)
            if api_key and api_key != '***' and len(api_key) > 0:
                current_config.jellyfin_api_key = api_key
                updated_fields.append('jellyfin_api_key')
                logger.info("API key updated")
            elif not api_key:
                # If empty string is provided, clear the API key
                current_config.jellyfin_api_key = ""
                updated_fields.append('jellyfin_api_key')
                logger.info("API key cleared")
        
        if 'local_media_paths' in data:
            paths = data['local_media_paths']
            if isinstance(paths, list):
                # Validate paths exist
                valid_paths = []
                for path in paths:
                    path = path.strip()
                    if path:
                        if not os.path.exists(path):
                            logger.warning(f"Creating media directory: {path}")
                            os.makedirs(path, exist_ok=True)
                        valid_paths.append(path)
                current_config.local_media_paths = valid_paths
                updated_fields.append('local_media_paths')
        
        if 'download_directory' in data:
            download_dir = data['download_directory'].strip()
            if download_dir:
                if not os.path.exists(download_dir):
                    logger.info(f"Creating download directory: {download_dir}")
                    os.makedirs(download_dir, exist_ok=True)
                current_config.download_directory = download_dir
                updated_fields.append('download_directory')
        
        if 'vlc_path' in data:
            current_config.vlc_path = data['vlc_path'].strip()
            updated_fields.append('vlc_path')
        
        if 'auto_launch' in data:
            current_config.auto_launch = bool(data['auto_launch'])
            updated_fields.append('auto_launch')
        
        if 'fullscreen_browser' in data:
            current_config.fullscreen_browser = bool(data['fullscreen_browser'])
            updated_fields.append('fullscreen_browser')
        
        # Save updated configuration
        try:
            logger.info(f"Attempting to save configuration with fields: {updated_fields}")
            logger.info(f"Current config values: server_url={current_config.jellyfin_server_url}, username={current_config.jellyfin_username}, api_key={'SET' if current_config.jellyfin_api_key else 'NOT_SET'}")
            
            success = current_config.save_to_file()
            if success:
                current_app.config['MEDIA_CONFIG'] = current_config
                logger.info(f"Configuration saved successfully. Fields: {updated_fields}")
                
                # If Jellyfin configuration was updated, reload services
                jellyfin_fields = ['jellyfin_server_url', 'jellyfin_username', 'jellyfin_api_key']
                if any(field in updated_fields for field in jellyfin_fields):
                    logger.info("Jellyfin configuration updated, reloading services...")
                    try:
                        # Reinitialize Jellyfin service
                        from ..services.jellyfin_service import JellyfinService
                        
                        new_jellyfin_service = JellyfinService(
                            server_url=current_config.jellyfin_server_url,
                            username=current_config.jellyfin_username,
                            api_key=current_config.jellyfin_api_key
                        )
                        
                        # Update media manager
                        media_manager = current_app.config.get('MEDIA_MANAGER')
                        if media_manager:
                            media_manager.jellyfin_service = new_jellyfin_service
                            current_app.config['MEDIA_MANAGER'] = media_manager
                            logger.info("Services reloaded with new Jellyfin configuration")
                        
                    except Exception as reload_error:
                        logger.error(f"Failed to reload services: {reload_error}")
                        # Don't fail the save operation if service reload fails
                
                return jsonify({
                    'success': True,
                    'message': 'Configuration updated successfully',
                    'updated_fields': updated_fields
                })
            else:
                logger.error("Configuration save returned False")
                return jsonify({
                    'success': False,
                    'error': 'Failed to save configuration to file',
                    'message': 'Save operation returned False'
                }), 500
            
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")
            return jsonify({
                'success': False,
                'error': 'Failed to save configuration',
                'message': str(e)
            }), 500
        
    except Exception as e:
        logger.error(f"Error updating configuration: {e}")
        return jsonify({
            'success': False,
            'error': 'Configuration update failed',
            'message': str(e)
        }), 500


@config_bp.route('/api/test-jellyfin', methods=['POST'])
def test_jellyfin_connection():
    """
    Test Jellyfin server connection with provided credentials.
    
    JSON Body:
        server_url (str): Jellyfin server URL
        username (str): Username (optional for API key auth)
        api_key (str): API key
        
    Returns:
        JSON response with connection test results
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No connection data provided'}), 400
        
        server_url = data.get('server_url', '').strip()
        username = data.get('username', '').strip()
        api_key = data.get('api_key', '').strip()
        
        if not server_url:
            return jsonify({'error': 'Server URL is required'}), 400
        
        if not api_key:
            return jsonify({'error': 'API key is required'}), 400
        
        logger.info(f"Testing Jellyfin connection to: {server_url}")
        
        # Import and test Jellyfin service
        from ..services.jellyfin_service import JellyfinService
        
        test_service = JellyfinService(
            server_url=server_url,
            username=username,
            api_key=api_key
        )
        
        # Test connection
        connection_result = test_service.test_connection()
        
        if connection_result:
            # Try to get basic server info
            try:
                media_count = len(test_service.get_media_library())
                return jsonify({
                    'success': True,
                    'message': 'Connection successful',
                    'server_url': server_url,
                    'media_count': media_count
                })
            except Exception as e:
                logger.warning(f"Connection successful but failed to get media count: {e}")
                return jsonify({
                    'success': True,
                    'message': 'Connection successful (limited access)',
                    'server_url': server_url,
                    'warning': 'Could not retrieve media library'
                })
        else:
            return jsonify({
                'success': False,
                'error': 'Connection failed',
                'message': 'Unable to connect to Jellyfin server'
            }), 400
        
    except Exception as e:
        logger.error(f"Error testing Jellyfin connection: {e}")
        return jsonify({
            'success': False,
            'error': 'Connection test failed',
            'message': str(e)
        }), 500


@config_bp.route('/api/test-vlc', methods=['POST'])
def test_vlc_installation():
    """
    Test VLC installation and functionality.
    
    JSON Body:
        vlc_path (str): Optional custom VLC path
        
    Returns:
        JSON response with VLC test results
    """
    try:
        data = request.get_json() or {}
        vlc_path = data.get('vlc_path', '').strip() or None
        
        logger.info(f"Testing VLC installation (path: {vlc_path})")
        
        # Import and test VLC controller
        from ..services.vlc_controller import VLCController
        
        test_controller = VLCController(vlc_path=vlc_path)
        
        # Test VLC installation
        is_installed = test_controller.is_vlc_installed()
        
        if is_installed:
            # Get VLC version info if possible
            try:
                vlc_info = test_controller.get_vlc_info()
                return jsonify({
                    'success': True,
                    'message': 'VLC is installed and accessible',
                    'vlc_path': test_controller.vlc_path,
                    'version_info': vlc_info
                })
            except Exception as e:
                logger.warning(f"VLC installed but couldn't get version info: {e}")
                return jsonify({
                    'success': True,
                    'message': 'VLC is installed and accessible',
                    'vlc_path': test_controller.vlc_path,
                    'warning': 'Could not retrieve version information'
                })
        else:
            return jsonify({
                'success': False,
                'error': 'VLC not found',
                'message': 'VLC Media Player is not installed or not accessible',
                'suggestion': 'Please install VLC or provide the correct path'
            }), 400
        
    except Exception as e:
        logger.error(f"Error testing VLC installation: {e}")
        return jsonify({
            'success': False,
            'error': 'VLC test failed',
            'message': str(e)
        }), 500


@config_bp.route('/api/reload-services', methods=['POST'])
def reload_services():
    """
    Reload services with updated configuration without restarting the application.
    
    Returns:
        JSON response with reload status
    """
    try:
        logger.info("Reloading services with updated configuration")
        
        # Get current configuration
        config = current_app.config.get('MEDIA_CONFIG')
        if not config:
            return jsonify({
                'success': False,
                'error': 'No configuration available'
            }), 500
        
        # Get current media manager
        media_manager = current_app.config.get('MEDIA_MANAGER')
        if not media_manager:
            return jsonify({
                'success': False,
                'error': 'Media manager not available'
            }), 500
        
        # Reinitialize Jellyfin service with new configuration
        from ..services.jellyfin_service import JellyfinService
        
        new_jellyfin_service = JellyfinService(
            server_url=config.jellyfin_server_url,
            username=config.jellyfin_username,
            api_key=config.jellyfin_api_key
        )
        
        # Test authentication if credentials are provided
        auth_success = False
        if config.jellyfin_server_url and config.jellyfin_api_key:
            logger.info("Testing Jellyfin authentication with new configuration...")
            try:
                auth_result = new_jellyfin_service.authenticate(
                    server_url=config.jellyfin_server_url,
                    api_key=config.jellyfin_api_key,
                    username=config.jellyfin_username
                )
                auth_success = bool(auth_result)
                if auth_success:
                    logger.info("Jellyfin service authenticated successfully with new configuration")
                else:
                    logger.warning("Jellyfin authentication failed with new configuration")
            except Exception as auth_error:
                logger.error(f"Jellyfin authentication error: {auth_error}")
        
        # Update the media manager's Jellyfin service
        media_manager.jellyfin_service = new_jellyfin_service
        
        # Update the app config
        current_app.config['MEDIA_MANAGER'] = media_manager
        
        return jsonify({
            'success': True,
            'message': 'Services reloaded successfully',
            'jellyfin_authenticated': auth_success,
            'jellyfin_configured': bool(config.jellyfin_server_url and config.jellyfin_api_key)
        })
        
    except Exception as e:
        logger.error(f"Error reloading services: {e}")
        return jsonify({
            'success': False,
            'error': 'Service reload failed',
            'message': str(e)
        }), 500


@config_bp.route('/api/reset', methods=['POST'])
def reset_config():
    """
    Reset configuration to defaults.
    
    Returns:
        JSON response with reset status
    """
    try:
        logger.info("Resetting configuration to defaults")
        
        # Create default configuration
        default_config = Configuration()
        
        # Save default configuration
        default_config.save_to_file()
        current_app.config['MEDIA_CONFIG'] = default_config
        
        return jsonify({
            'success': True,
            'message': 'Configuration reset to defaults successfully'
        })
        
    except Exception as e:
        logger.error(f"Error resetting configuration: {e}")
        return jsonify({
            'success': False,
            'error': 'Configuration reset failed',
            'message': str(e)
        }), 500