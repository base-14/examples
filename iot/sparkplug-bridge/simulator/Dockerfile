# Build context is the example root so the shared proto/ is reachable.
# Build stage - resolve deps and generate the protobuf bindings.
FROM python:3.13-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.6.12 /uv /usr/local/bin/uv

WORKDIR /app
COPY simulator/pyproject.toml simulator/uv.lock* ./

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv
RUN uv sync --no-dev

# Generate sparkplug_b_pb2.py from the vendored proto using the venv's protoc
# (grpcio-tools), so the binding and the protobuf runtime versions match.
COPY proto/sparkplug_b.proto ./proto/
RUN /app/.venv/bin/python -m grpc_tools.protoc -Iproto --python_out=. proto/sparkplug_b.proto

# Runtime stage.
FROM python:3.13-slim

WORKDIR /app
RUN adduser --disabled-password --gecos '' --uid 1000 appuser

COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appuser /app/sparkplug_b_pb2.py ./
COPY --chown=appuser:appuser simulator/tahu_simulator.py ./

ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

USER appuser

CMD ["python", "tahu_simulator.py"]
