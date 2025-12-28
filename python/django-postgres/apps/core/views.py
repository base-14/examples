from __future__ import annotations

from typing import Any

import redis
from django.conf import settings
from django.db import connection
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response


@api_view(["GET"])
def health_check(request: Request) -> Response:
    health: dict[str, Any] = {
        "status": "healthy",
        "components": {},
        "service": {
            "name": settings.OTEL_SERVICE_NAME,
            "version": settings.OTEL_SERVICE_VERSION,
        },
    }

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        health["components"]["database"] = "healthy"
    except Exception as e:
        health["components"]["database"] = f"unhealthy: {e!s}"
        health["status"] = "unhealthy"

    try:
        r = redis.from_url(settings.REDIS_URL)
        r.ping()
        health["components"]["redis"] = "healthy"
    except Exception as e:
        health["components"]["redis"] = f"unhealthy: {e!s}"
        health["status"] = "unhealthy"

    status_code = 200 if health["status"] == "healthy" else 503
    return Response(health, status=status_code)
