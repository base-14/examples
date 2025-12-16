# Celery Demo with base14 Scout

FastAPI + Celery reference application demonstrating **OpenTelemetry
auto-instrumentation** and **unified observability** with base14 Scout.

## Overview

This demo showcases base14 Scout as a **unified observability platform** that collects:

- **Distributed Traces**: End-to-end request flows across FastAPI → Celery → Database
- **Metrics**: Application, infrastructure, and custom business metrics
- **Logs**: Structured application logs with trace correlation

Telemetry is collected via **OpenTelemetry auto-instrumentation** with minimal
code. The only manual step is propagating trace context across async boundaries
(Celery tasks) to enable true end-to-end distributed tracing.

## Stack

- **API**: FastAPI 0.124+ (async web framework)
- **Tasks**: Celery 5.6+ (distributed task queue)
- **Database**: PostgreSQL (data persistence + metrics)
- **Broker**: RabbitMQ (message queue + metrics)
- **Cache/Backend**: Redis (task results + metrics)
- **Collector**: OpenTelemetry Collector (telemetry aggregation)
- **Observability**: base14 Scout (unified traces, metrics, logs)

## Quick Start

```bash
# Set Scout credentials (required)
export SCOUT_ENDPOINT=<your-scout-endpoint>
export SCOUT_CLIENT_ID=<your-client-id>
export SCOUT_CLIENT_SECRET=<your-client-secret>
export SCOUT_TOKEN_URL=<your-token-url>

# Start all services
docker compose up -d --build

# Check service health
docker compose ps

# View logs
docker compose logs -f

# Stop services
docker compose down
```

## Test the Application

```bash
# Health check
curl http://localhost:8000/ping

# Create a task (triggers async Celery processing)
curl -X POST http://localhost:8000/tasks/ \
  -H "Content-Type: application/json" \
  -d '{"title": "My Task"}'

# List all tasks
curl http://localhost:8000/tasks/

# Get specific task
curl http://localhost:8000/tasks/1
```

View the distributed traces and metrics in your **base14 Scout** dashboard.

## OpenTelemetry Instrumentation

This demo uses **auto-instrumentation** for most telemetry, with explicit
context propagation for async boundaries.

### Automatic Instrumentation

- **FastAPI**: HTTP requests, endpoints, middleware
- **Celery**: Task execution, worker operations
- **SQLAlchemy**: Database queries, transactions, connection pooling
- **Redis**: Cache operations, result backend

### Infrastructure Metrics (via OTEL Collector receivers)

- **PostgreSQL**: Database metrics (connections, queries, locks, replication)
- **RabbitMQ**: Message broker metrics (queues, consumers, messages)
- **Redis**: Server metrics (memory, connections, commands)

### Unified Observability with Scout

The OpenTelemetry Collector sends all telemetry to **base14 Scout**:

- **Traces Pipeline**: OTLP → Batch Processor → Scout (distributed tracing)
- **Metrics Pipeline**: OTLP + PostgreSQL/RabbitMQ/Redis receivers → Scout
- **Logs Pipeline**: OTLP → Batch Processor → Scout (trace-correlated logs)

## Development

```bash
# Install dependencies
poetry install

# Run security audit
poetry run pip-audit

# Lint code
poetry run ruff check .

# Fix linting issues
poetry run ruff check --fix .
```

## How It Works

1. **HTTP Request**: POST creates task in PostgreSQL (auto-traced via SQLAlchemy)
2. **Context Propagation**: Trace context injected into Celery headers (`traceparent`)
3. **Message Queue**: Task sent to RabbitMQ (auto-traced via Celery instrumentation)
4. **Worker Processing**: Celery worker extracts trace context, continues trace
5. **Result Storage**: Results stored in Redis (auto-traced via Redis instrumentation)
6. **Unified View**: All spans share same Trace ID for end-to-end visibility

### Distributed Trace Flow

```text
POST /tasks/                                    Trace ID: abc123
├── INSERT task_db (PostgreSQL)
├── apply_async/process_task ─► RabbitMQ ─► run/process_task
                                            ├── process_task
                                            │   └── heavy_processing
                                            └── SETEX (Redis)
```

### Context Propagation Code

The key to distributed tracing across async boundaries is explicit context injection:

```python
from opentelemetry.propagate import inject

# In FastAPI endpoint
headers = {}
inject(headers)  # Adds traceparent header
task.apply_async(args=[task_id], headers=headers)
```

Without this, the Celery worker would start a new trace, losing correlation
with the HTTP request.

## Scout Dashboard Features

In your base14 Scout dashboard, you'll see:

- **Service Map**: Visual representation of service dependencies
- **Distributed Traces**: Complete request flows with timing breakdowns across services
- **Infrastructure Metrics**: PostgreSQL, RabbitMQ, Redis server metrics
- **Correlated Logs**: Application logs linked to traces via Trace ID
- **Custom Dashboards**: Create views combining traces, metrics, and logs
