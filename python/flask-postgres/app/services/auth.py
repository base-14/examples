"""JWT authentication service."""

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from flask import current_app

from app.models import User


def generate_token(user: User) -> str:
    """Generate JWT token for user.

    Args:
        user: User to generate token for.

    Returns:
        JWT token string.
    """
    expiration_hours = current_app.config.get("JWT_EXPIRATION_HOURS", 24)
    secret_key = current_app.config["JWT_SECRET_KEY"]
    algorithm = current_app.config.get("JWT_ALGORITHM", "HS256")

    payload = {
        "user_id": user.id,
        "email": user.email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=expiration_hours),
        "iat": datetime.now(timezone.utc),
    }

    return jwt.encode(payload, secret_key, algorithm=algorithm)


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate JWT token.

    Args:
        token: JWT token string.

    Returns:
        Decoded token payload.

    Raises:
        jwt.InvalidTokenError: If token is invalid or expired.
    """
    secret_key = current_app.config["JWT_SECRET_KEY"]
    algorithm = current_app.config.get("JWT_ALGORITHM", "HS256")

    return jwt.decode(token, secret_key, algorithms=[algorithm])
