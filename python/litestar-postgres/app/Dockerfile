# Build stage — install deps with uv into a project venv
FROM python:3.14-slim AS builder

# uv: fast Python package manager
COPY --from=ghcr.io/astral-sh/uv:0.6.12 /uv /usr/local/bin/uv

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Cache deps layer: copy lock+manifest first
COPY pyproject.toml uv.lock* ./

# Install runtime deps only (no dev), into /app/.venv, system-independent
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv
RUN uv sync --no-dev --frozen

# Runtime stage
FROM python:3.14-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && adduser --disabled-password --gecos '' --uid 1000 appuser

COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv

COPY --chown=appuser:appuser . .

ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8080/api/health || exit 1

# Run migrations then boot uvicorn under the OTel auto-instrumentation wrapper
# (instruments ASGI, SQLAlchemy, httpx, asyncpg, logging).
CMD ["sh", "-c", "alembic upgrade head && opentelemetry-instrument uvicorn src.main:app --host 0.0.0.0 --port 8080"]
