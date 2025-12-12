# Celery Demo with Base14 Scout

FastAPI + Celery reference application demonstrating **OpenTelemetry auto-instrumentation** and **unified observability** with Base14 Scout.

## Overview

This demo showcases Base14 Scout as a **unified observability platform** that collects:
- **Distributed Traces**: End-to-end request flows across FastAPI → Celery → Database
- **Metrics**: Application, infrastructure, and custom business metrics
- **Logs**: Structured application logs with trace correlation

All telemetry is automatically collected via **OpenTelemetry auto-instrumentation** with zero code changes required.

## Stack

- **API**: FastAPI 0.124+ (async web framework)
- **Tasks**: Celery 5.6+ (distributed task queue)
- **Database**: PostgreSQL (data persistence + metrics)
- **Broker**: RabbitMQ (message queue + metrics)
- **Cache/Backend**: Redis (task results + metrics)
- **Collector**: OpenTelemetry Collector (telemetry aggregation)
- **Observability**: Base14 Scout (unified traces, metrics, logs)

## Quick Start

```bash
# Set Scout credentials (required)
export SCOUT_ENDPOINT=<your-scout-endpoint>
export SCOUT_CLIENT_ID=<your-client-id>
export SCOUT_CLIENT_SECRET=<your-client-secret>
export SCOUT_TOKEN_URL=<your-token-url>

# Start all services
docker-compose up -d --build

# Check service health
docker-compose ps

# View logs
docker-compose logs -f

# Stop services
docker-compose down
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

View the distributed traces and metrics in your **Base14 Scout** dashboard.

## OpenTelemetry Auto-Instrumentation

This demo uses **zero-code auto-instrumentation** for all telemetry:

### Automatic Instrumentation
- **FastAPI**: HTTP requests, endpoints, middleware
- **Celery**: Task execution, worker operations, message queue interactions
- **SQLAlchemy**: Database queries, transactions, connection pooling
- **Redis**: Cache operations, pub/sub, result backend
- **PostgreSQL**: Database metrics (connections, queries, locks)
- **RabbitMQ**: Message broker metrics (queues, consumers, messages)
- **Docker**: Container metrics (CPU, memory, network, disk)

### Unified Observability with Scout
The OpenTelemetry Collector sends all telemetry to **Base14 Scout**:
- **Traces Pipeline**: OTLP → Batch Processor → Scout (distributed tracing)
- **Metrics Pipeline**: Multiple receivers → Batch Processor → Scout (infrastructure + app metrics)
- **Logs Pipeline**: File logs + OTLP → Batch Processor → Scout (correlated logs)

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

1. POST request creates a task in PostgreSQL (auto-traced via SQLAlchemy instrumentation)
2. Task ID is sent to Celery via RabbitMQ (auto-traced via Celery instrumentation)
3. Celery worker processes task asynchronously with 10s delay (auto-traced)
4. Results stored in Redis (auto-traced via Redis instrumentation)
5. All traces, metrics, and logs automatically collected by OpenTelemetry and visualized in Base14 Scout

## Scout Dashboard Features

In your Base14 Scout dashboard, you'll see:
- **Service Map**: Visual representation of service dependencies (FastAPI → Celery → PostgreSQL/Redis)
- **Distributed Traces**: Complete request flows with timing breakdowns
- **Infrastructure Metrics**: PostgreSQL, RabbitMQ, Redis, Docker container metrics
- **Correlated Logs**: Application logs linked to traces for faster debugging
- **Custom Dashboards**: Create views combining traces, metrics, and logs
