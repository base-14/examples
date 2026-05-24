# Build stage — resolve deps with uv into a project venv.
FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.6.12 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock* ./

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv
RUN uv sync --no-dev

# Runtime stage.
FROM python:3.13-slim

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && adduser --disabled-password --gecos '' --uid 1000 appuser

COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --chown=appuser:appuser . .

ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# opentelemetry-instrument auto-instruments FastAPI + the ASGI server.
CMD ["opentelemetry-instrument", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
