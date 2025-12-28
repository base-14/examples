"""Authentication endpoints."""

import logging

from flask import Blueprint, jsonify, request
from marshmallow import ValidationError
from sqlalchemy.exc import IntegrityError

from app.errors import error_response
from app.extensions import db
from app.middleware.auth import token_required
from app.models import User
from app.schemas import LoginSchema, RegisterSchema, TokenSchema, UserSchema
from app.services.auth import generate_token
from app.telemetry import get_meter, get_tracer


logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)
meter = get_meter(__name__)

auth_attempts = meter.create_counter(
    name="auth.login.attempts",
    description="Login attempts",
    unit="1",
)

auth_bp = Blueprint("auth", __name__, url_prefix="/api")


@auth_bp.route("/register", methods=["POST"])
def register():
    """Register a new user.

    Returns:
        JSON response with user data and JWT token.
    """
    with tracer.start_as_current_span("user.register") as span:
        # Validate request data
        schema = RegisterSchema()
        try:
            data = schema.load(request.get_json() or {})
        except ValidationError as err:
            return jsonify(err.messages), 400

        # Check if email already exists
        if db.session.query(User).filter(User.email == data["email"]).first():
            span.set_attribute("auth.status", "duplicate_email")
            return error_response("Email already registered", 409)

        # Create user
        user = User(
            email=data["email"],
            name=data["name"],
        )
        user.set_password(data["password"])

        try:
            db.session.add(user)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return error_response("Email already registered", 409)

        span.set_attribute("user.id", user.id)
        span.set_attribute("user.email", user.email)

        # Generate token
        token = generate_token(user)
        logger.info(f"User registered: {user.email}", extra={"user_id": user.id})

        return jsonify({
            "user": UserSchema().dump(user),
            "token": TokenSchema().dump({"access_token": token}),
        }), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    """Authenticate user and return JWT token.

    Returns:
        JSON response with user data and JWT token.
    """
    with tracer.start_as_current_span("user.login") as span:
        # Validate request data
        schema = LoginSchema()
        try:
            data = schema.load(request.get_json() or {})
        except ValidationError as err:
            auth_attempts.add(1, {"status": "invalid_request"})
            return jsonify(err.messages), 400

        email = data["email"]
        password = data["password"]

        # Find user
        user = db.session.query(User).filter(User.email == email).first()
        if not user:
            auth_attempts.add(1, {"status": "user_not_found"})
            span.set_attribute("auth.status", "user_not_found")
            logger.warning(f"Login failed: user not found for {email}")
            return error_response("Invalid credentials", 401)

        # Check password
        if not user.check_password(password):
            auth_attempts.add(1, {"status": "invalid_password"})
            span.set_attribute("auth.status", "invalid_password")
            logger.warning(f"Login failed: invalid password for {email}")
            return error_response("Invalid credentials", 401)

        auth_attempts.add(1, {"status": "success"})
        span.set_attribute("user.id", user.id)
        span.set_attribute("auth.status", "success")

        # Generate token
        token = generate_token(user)
        logger.info(f"User logged in: {user.email}", extra={"user_id": user.id})

        return jsonify({
            "user": UserSchema().dump(user),
            "token": TokenSchema().dump({"access_token": token}),
        })


@auth_bp.route("/user", methods=["GET"])
@token_required
def get_user():
    """Get current authenticated user.

    Returns:
        JSON response with user data.
    """
    from flask import g

    return jsonify(UserSchema().dump(g.current_user))


@auth_bp.route("/logout", methods=["POST"])
@token_required
def logout():
    """Logout current user.

    Returns:
        JSON response with success message.
    """
    return jsonify({"message": "Logged out successfully"})
