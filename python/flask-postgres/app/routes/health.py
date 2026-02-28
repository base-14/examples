"""Health check endpoint."""

from typing import Any

import redis
from flask import Blueprint, current_app, jsonify
from sqlalchemy import text

from app.extensions import db


health_bp = Blueprint("health", __name__, url_prefix="/api")


@health_bp.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint for monitoring.

    Returns:
        JSON response with health status of database and redis.
    """
    health_status: dict[str, Any] = {
        "status": "healthy",
        "components": {
            "database": "healthy",
            "redis": "healthy",
        },
        "service": {
            "name": "flask-postgres-app",
            "version": "1.0.0",
        },
    }

    # Check database connection
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:
        health_status["status"] = "unhealthy"
        health_status["components"]["database"] = "unhealthy"

    # Check Redis connection
    try:
        redis_url = current_app.config.get("REDIS_URL", "redis://localhost:6379/0")
        redis_client = redis.from_url(redis_url)
        redis_client.ping()
    except Exception:
        health_status["status"] = "unhealthy"
        health_status["components"]["redis"] = "unhealthy"

    status_code = 200 if health_status["status"] == "healthy" else 503
    return jsonify(health_status), status_code
