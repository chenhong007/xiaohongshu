"""
Flask Application Factory

This module creates and configures the Flask application.
"""
import time
from flask import Flask, g, request, jsonify
from flask_cors import CORS

from .config import Config, get_config
from .extensions import db, migrate
from .api import accounts_bp, notes_bp, auth_bp, search_bp, sync_logs_bp
from .utils.logger import setup_logger, get_logger

# WebSocket support (optional)
try:
    from .websocket import socketio, init_socketio
    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False
    socketio = None


def create_app(config_class=None):
    """Create and configure Flask application.
    
    Args:
        config_class: Configuration class to use. If None, auto-detect from environment.
        
    Returns:
        Configured Flask application instance
    """
    if config_class is None:
        config_class = get_config()
    
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Ensure data directories exist
    Config.init_paths()
    
    # Initialize logging
    setup_logger(
        log_level=app.config.get('LOG_LEVEL', 'INFO'),
        log_file=app.config.get('LOG_FILE')
    )
    
    logger = get_logger('app')
    
    # Initialize CORS
    cors_config = config_class.get_cors_config()
    CORS(app, resources={r"/api/*": cors_config})
    
    # Initialize database
    db.init_app(app)
    
    # Initialize Flask-Migrate
    migrate.init_app(app, db)
    
    # Register blueprints (single prefix, no duplication)
    _register_blueprints(app)
    
    # Perform startup tasks
    # Note: Use 'flask db upgrade' to create/update database tables
    with app.app_context():
        _cleanup_stale_tasks(logger)
    
    # Register handlers and hooks
    _register_error_handlers(app)
    _register_request_hooks(app)
    _register_health_check(app)
    
    # Initialize WebSocket if available
    if WEBSOCKET_AVAILABLE:
        _init_websocket(app, logger)
    
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    logger.info(f"Application initialized, database: {db_uri}")
    
    return app


def _register_blueprints(app):
    """Register API blueprints with single prefix."""
    # Use /api as the primary prefix
    # For versioning, consider using Accept headers or /api/v2 for breaking changes
    app.register_blueprint(accounts_bp, url_prefix='/api')
    app.register_blueprint(notes_bp, url_prefix='/api')
    app.register_blueprint(auth_bp, url_prefix='/api')
    app.register_blueprint(search_bp, url_prefix='/api')
    app.register_blueprint(sync_logs_bp, url_prefix='/api')


def _cleanup_stale_tasks(logger):
    """Clean up stale sync tasks on startup."""
    try:
        from .services.sync_service import SyncService
        cleaned = SyncService.cleanup_stale_tasks()
        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} stale sync tasks on startup")
    except Exception as e:
        logger.warning(f"Failed to cleanup stale tasks: {e}")


def _init_websocket(app, logger):
    """Initialize WebSocket support."""
    try:
        init_socketio(app)
        from .services.sync_log_broadcaster import sync_log_broadcaster
        sync_log_broadcaster.enable_websocket()
        logger.info("WebSocket real-time push enabled")
    except Exception as e:
        logger.warning(f"WebSocket initialization failed, falling back to polling: {e}")


def _register_error_handlers(app):
    """Register global error handlers."""
    from .utils.responses import ApiResponse
    
    @app.errorhandler(400)
    def bad_request(error):
        msg = str(error.description) if hasattr(error, 'description') else 'Bad request'
        return ApiResponse.error(msg, 400, 'BAD_REQUEST')
    
    @app.errorhandler(404)
    def not_found(error):
        msg = str(error.description) if hasattr(error, 'description') else 'Resource not found'
        return ApiResponse.not_found(msg)
    
    @app.errorhandler(405)
    def method_not_allowed(error):
        return ApiResponse.error('Method not allowed', 405, 'METHOD_NOT_ALLOWED')
    
    @app.errorhandler(500)
    def internal_error(error):
        logger = get_logger('error')
        logger.exception(error)
        return ApiResponse.server_error('Internal server error')


def _register_request_hooks(app):
    """Register request timing hooks."""
    
    @app.before_request
    def before_request():
        g.start_time = time.time()
    
    @app.after_request
    def after_request(response):
        if hasattr(g, 'start_time'):
            duration = (time.time() - g.start_time) * 1000
            if duration > 1000:  # Log slow requests
                logger = get_logger('slow_request')
                logger.warning(f"Slow request: {request.method} {request.path} took {duration:.2f}ms")
        return response


def _register_health_check(app):
    """Register health check endpoint."""
    
    @app.route('/api/health')
    def health_check():
        """Health check endpoint for container orchestration."""
        return jsonify({
            'status': 'healthy',
            'service': 'xhs-backend'
        })
