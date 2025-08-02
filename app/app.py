"""
RV Media Player Flask Application

Main Flask application module that provides web interface and API endpoints
for the RV Media Player system.
"""
import logging
import os
import sys
from flask import Flask, jsonify, request, render_template, send_from_directory
from werkzeug.exceptions import HTTPException
import traceback

# Add the application root directory to Python path for imports
app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if app_root not in sys.path:
    sys.path.insert(0, app_root)

# Also add the current working directory to handle installed locations
current_dir = os.getcwd()
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Now import with absolute paths
from app.services.media_manager import MediaManager
from app.services.local_media_service import LocalMediaService
from app.services.jellyfin_service import JellyfinService
from app.services.vlc_controller import VLCController
from config.configuration import Configuration


def create_app(config_path: str = None) -> Flask:
    """
    Create and configure Flask application.
    ...
    """
    app = Flask(__name__,
                template_folder='../templates',
                static_folder='../static')

    setup_logging(app)

    try:
        config = Configuration.load_from_file(config_path)
        app.config['MEDIA_CONFIG'] = config
        app.logger.info("Configuration loaded successfully")
    except Exception as e:
        app.logger.error(f"Failed to load configuration: {e}")
        config = Configuration()
        app.config['MEDIA_CONFIG'] = config

    # Initialize services
    try:
        local_db_path = config.local_db_path if hasattr(config, 'local_db_path') else "media/local_media.db"
        local_service = LocalMediaService(
            db_path=local_db_path,
            validation_cache_ttl=config.validation_cache_ttl,
            max_validation_workers=config.max_validation_workers
        )
        local_service.scan_media_directories(config.local_media_paths)
        local_service.start_watching(config.local_media_paths)

        jellyfin_service = JellyfinService(
            server_url=config.jellyfin_server_url,
            username=config.jellyfin_username,
            api_key=config.jellyfin_api_key
        )

        # Attempt to authenticate Jellyfin service on startup
        if config.jellyfin_server_url and config.jellyfin_api_key and config.jellyfin_username:
            app.logger.info("Attempting to authenticate Jellyfin service...")
            auth_success = jellyfin_service.authenticate(
                server_url=config.jellyfin_server_url,
                api_key=config.jellyfin_api_key,
                username=config.jellyfin_username
            )
            if auth_success:
                app.logger.info("Jellyfin service authenticated successfully.")
            else:
                app.logger.error("Jellyfin service authentication failed during startup. Media library features may be limited.")
        else:
            app.logger.warning("Jellyfin server URL, API Key, or Username is missing. Skipping initial authentication.")

        vlc_controller = VLCController()

        media_manager = MediaManager(
            local_service=local_service,
            jellyfin_service=jellyfin_service,
            vlc_controller=vlc_controller
        )

        app.config['MEDIA_MANAGER'] = media_manager
        app.logger.info("Services initialized successfully")

    except Exception as e:
        app.logger.error(f"Failed to initialize services: {e}")
        app.logger.error(traceback.format_exc())
        app.config['MEDIA_MANAGER'] = None

    register_error_handlers(app)
    register_routes(app)

    return app



def setup_logging(app: Flask) -> None:
    """
    Configure application logging.

    Args:
        app: Flask application instance
    """
    # Determine the application root directory
    app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    logs_dir = os.path.join(app_root, 'logs')
    
    # Create logs directory if it doesn't exist
    try:
        os.makedirs(logs_dir, exist_ok=True)
        # Ensure proper permissions
        os.chmod(logs_dir, 0o755)
    except (OSError, PermissionError) as e:
        print(f"Warning: Could not create logs directory {logs_dir}: {e}")
        # Fall back to system temp directory
        import tempfile
        logs_dir = tempfile.gettempdir()
        print(f"Using temporary directory for logs: {logs_dir}")

    # Configure logging format
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # File handler for application logs
    log_file = os.path.join(logs_dir, 'app.log')
    try:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        
        # Configure Flask app logger
        app.logger.setLevel(logging.DEBUG)
        app.logger.addHandler(file_handler)
        
        # Configure werkzeug logger (Flask's built-in server)
        werkzeug_logger = logging.getLogger('werkzeug')
        werkzeug_logger.setLevel(logging.INFO)
        werkzeug_logger.addHandler(file_handler)
        
        app.logger.info(f"Logging initialized. Log file: {log_file}")
        
    except (OSError, PermissionError) as e:
        print(f"Warning: Could not create log file {log_file}: {e}")
        print("Continuing with console logging only")

    # Console handler (always available)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)

    # Configure Flask app logger
    app.logger.setLevel(logging.DEBUG)
    app.logger.addHandler(console_handler)

    # Configure werkzeug logger (Flask's built-in server)
    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.setLevel(logging.INFO)
    werkzeug_logger.addHandler(console_handler)


def register_error_handlers(app: Flask) -> None:
    """
    Register error handlers for the application.

    Args:
        app: Flask application instance
    """

    @app.errorhandler(404)
    def not_found_error(error):
        """Handle 404 errors."""
        app.logger.warning(f"404 error: {request.url}")
        if request.path.startswith('/api/'):
            return jsonify({
                'error': 'Not Found',
                'message': 'The requested resource was not found',
                'status_code': 404
            }), 404
        return render_template('error.html',
                               error_code=404,
                               error_message="Page not found"), 404

    @app.errorhandler(500)
    def internal_error(error):
        """Handle 500 errors."""
        app.logger.error(f"500 error: {error}")
        app.logger.error(traceback.format_exc())
        if request.path.startswith('/api/'):
            return jsonify({
                'error': 'Internal Server Error',
                'message': 'An internal server error occurred',
                'status_code': 500
            }), 500
        return render_template('error.html',
                               error_code=500,
                               error_message="Internal server error"), 500

    @app.errorhandler(HTTPException)
    def handle_http_exception(error):
        """Handle all HTTP exceptions."""
        app.logger.warning(f"HTTP exception: {error.code} - {error.description}")
        if request.path.startswith('/api/'):
            return jsonify({
                'error': error.name,
                'message': error.description,
                'status_code': error.code
            }), error.code
        return render_template('error.html',
                               error_code=error.code,
                               error_message=error.description), error.code

    @app.errorhandler(Exception)
    def handle_exception(error):
        """Handle unexpected exceptions."""
        app.logger.error(f"Unexpected error: {error}")
        app.logger.error(traceback.format_exc())
        if request.path.startswith('/api/'):
            return jsonify({
                'error': 'Unexpected Error',
                'message': 'An unexpected error occurred',
                'status_code': 500
            }), 500
        return render_template('error.html',
                               error_code=500,
                               error_message="An unexpected error occurred"), 500


def register_routes(app: Flask) -> None:
    """
    Register application routes.

    Args:
        app: Flask application instance
    """
    from app.controllers.main_controller import main_bp
    from app.controllers.api_controller import api_bp
    from app.controllers.config_controller import config_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(config_bp, url_prefix='/config')
    
    # Add a route for favicon.ico
    @app.route('/favicon.ico')
    def favicon():
        return send_from_directory(app.static_folder, 'favicon.ico')


if __name__ == '__main__':
    app = create_app()
    # Disable debug mode to prevent frequent reloads that interrupt downloads
    app.run(host='0.0.0.0', port=5000, debug=False)
