import logging

from opentelemetry import trace
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.telemetry import get_meter, get_tracer

from .authentication import generate_token
from .models import User
from .serializers import LoginSerializer, RegisterSerializer, TokenSerializer, UserSerializer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)
meter = get_meter(__name__)

auth_attempts = meter.create_counter(
    name="auth.login.attempts",
    description="Login attempts",
    unit="1",
)


@api_view(["POST"])
def register(request: Request) -> Response:
    with tracer.start_as_current_span("user.register") as span:
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning(f"Registration failed: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.save()
        span.set_attribute("user.id", user.id)
        span.set_attribute("user.email", user.email)

        token = generate_token(user)
        logger.info(f"User registered: {user.email}", extra={"user_id": user.id})
        return Response(
            {
                "user": UserSerializer(user).data,
                "token": TokenSerializer({"access_token": token}).data,
            },
            status=status.HTTP_201_CREATED,
        )


@api_view(["POST"])
def login(request: Request) -> Response:
    with tracer.start_as_current_span("user.login") as span:
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            auth_attempts.add(1, {"status": "invalid_request"})
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            auth_attempts.add(1, {"status": "user_not_found"})
            span.set_attribute("auth.status", "user_not_found")
            logger.warning(f"Login failed: user not found for {email}")
            return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

        if not user.check_password(password):
            auth_attempts.add(1, {"status": "invalid_password"})
            span.set_attribute("auth.status", "invalid_password")
            logger.warning(f"Login failed: invalid password for {email}")
            return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

        auth_attempts.add(1, {"status": "success"})
        span.set_attribute("user.id", user.id)
        span.set_attribute("auth.status", "success")

        token = generate_token(user)
        logger.info(f"User logged in: {user.email}", extra={"user_id": user.id})
        return Response(
            {
                "user": UserSerializer(user).data,
                "token": TokenSerializer({"access_token": token}).data,
            }
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_user(request: Request) -> Response:
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attribute("user.id", request.user.id)
    return Response(UserSerializer(request.user).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout(_request: Request) -> Response:
    return Response({"message": "Logged out successfully"})
