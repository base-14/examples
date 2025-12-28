"""Flask application factory with OpenTelemetry instrumentation."""

import logging
import os

from flask import Flask

from app.extensions import db, ma


def create_app(config_class: type | None = None) -> Flask:
    """Create and configure the Flask application.

    Args:
        config_class: Configuration class to use. Defaults to Config.

    Returns:
        Configured Flask application instance.
    """
    # Initialize telemetry BEFORE creating Flask app
    if not os.getenv("OTEL_SDK_DISABLED"):
        from app.telemetry import get_otel_log_handler, instrument_flask_app, setup_telemetry

        setup_telemetry()

    app = Flask(__name__)

    # Instrument Flask app (needed for Gunicorn worker forks)
    if not os.getenv("OTEL_SDK_DISABLED"):
        instrument_flask_app(app)

    # Load configuration
    if config_class is None:
        from app.config import Config

        config_class = Config
    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)
    ma.init_app(app)

    # Register blueprints
    from app.routes.articles import articles_bp
    from app.routes.auth import auth_bp
    from app.routes.health import health_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(articles_bp)

    # Register error handlers
    from app.errors import register_error_handlers

    register_error_handlers(app)

    # Register metrics middleware
    if not os.getenv("OTEL_SDK_DISABLED"):
        from app.middleware.metrics import register_metrics_middleware

        register_metrics_middleware(app)

    # Attach OTel log handler after app setup
    if not os.getenv("OTEL_SDK_DISABLED"):
        handler = get_otel_log_handler()
        if handler:
            root_logger = logging.getLogger()
            if handler not in root_logger.handlers:
                root_logger.addHandler(handler)

    # Configure logging
    _configure_logging()

    # Create database tables
    with app.app_context():
        db.create_all()

    return app


def _configure_logging() -> None:
    """Configure logging for the application."""
    # App loggers - propagate to root (where OTel handler is)
    logging.getLogger("app").setLevel(logging.DEBUG)
    logging.getLogger("app").propagate = True

    # Reduce noise from framework loggers
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("werkzeug").propagate = False

    # SQLAlchemy engine logs can be noisy
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
