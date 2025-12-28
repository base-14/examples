"""JWT authentication middleware."""

from functools import wraps
from typing import Callable, ParamSpec, TypeVar

from flask import g, jsonify, request

from app.extensions import db
from app.models import User
from app.services.auth import decode_token


P = ParamSpec("P")
T = TypeVar("T")


def token_required(f: Callable[P, T]) -> Callable[P, T]:
    """Decorator to require valid JWT token.

    Sets g.current_user if token is valid.
    Returns 401 if token is missing or invalid.
    """

    @wraps(f)
    def decorated(*args: P.args, **kwargs: P.kwargs) -> T:
        auth_header = request.headers.get("Authorization", "")

        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid authorization header"}), 401

        token = auth_header[7:]  # Remove "Bearer " prefix

        try:
            payload = decode_token(token)
        except Exception:
            return jsonify({"error": "Invalid or expired token"}), 401

        user_id = payload.get("user_id")
        if not user_id:
            return jsonify({"error": "Invalid token payload"}), 401

        user = db.session.query(User).filter(User.id == user_id).first()
        if not user:
            return jsonify({"error": "User not found"}), 401

        g.current_user = user
        return f(*args, **kwargs)

    return decorated


def token_optional(f: Callable[P, T]) -> Callable[P, T]:
    """Decorator to optionally parse JWT token.

    Sets g.current_user if token is valid, otherwise None.
    Does not return error if token is missing or invalid.
    """

    @wraps(f)
    def decorated(*args: P.args, **kwargs: P.kwargs) -> T:
        g.current_user = None

        auth_header = request.headers.get("Authorization", "")

        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                payload = decode_token(token)
                user_id = payload.get("user_id")
                if user_id:
                    g.current_user = db.session.query(User).filter(User.id == user_id).first()
            except Exception:
                pass  # Token invalid, but that's okay for optional auth

        return f(*args, **kwargs)

    return decorated
