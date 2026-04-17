"""Health-check controller.

Liveness probe used by Docker and orchestrators. Kept dependency-free so a
failing database does not mark the pod unhealthy — that is what readiness
probes are for. The collector filters out spans for this path so health checks
do not pollute traces (see config/otel-config.yaml `filter/noisy`).
"""

from litestar import Controller, get


class HealthController(Controller):
    path = "/api/health"

    @get("/")
    async def health(self) -> dict[str, str]:
        return {"status": "ok", "service": "litestar-postgres-app"}
