from starlette.middleware.base import BaseHTTPMiddleware
from opentelemetry.metrics import get_meter

class MetricsMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.meter = get_meter("custom-fastapi-service")
        self.http_requests_counter = self.meter.create_counter(
            name="http_requests_total",
            unit="1",
            description="Number of HTTP requests per route"
        )

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        self.http_requests_counter.add(
            1,
            {
                "method": request.method,
                "path": request.url.path,
                "status_code": str(response.status_code),
            }
        )
        return response
