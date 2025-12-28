# Flask + PostgreSQL + OpenTelemetry

Production-ready Flask REST API with full OpenTelemetry instrumentation for distributed tracing, metrics, and structured logging.

## Stack

| Component | Version |
|-----------|---------|
| Python | 3.14 |
| Flask | 3.1.2 |
| SQLAlchemy | 2.0.45 |
| PostgreSQL | 17 |
| Celery | 5.6.0 |
| Redis | 8 |
| OpenTelemetry SDK | 1.39.1 |

## Quick Start

```bash
# Start all services
docker compose up -d

# Run API tests (28 test cases)
./scripts/test-api.sh

# View logs
docker compose logs -f app

# View OTel collector output
docker compose logs -f otel-collector
```

## API Endpoints

### Health
- `GET /api/health` - Health check (database, redis, celery status)

### Authentication
- `POST /api/register` - Register new user
- `POST /api/login` - Login and get JWT token
- `GET /api/user` - Get current user (requires auth)
- `POST /api/logout` - Logout

### Articles
- `GET /api/articles/` - List articles (with search, pagination)
- `POST /api/articles/` - Create article (requires auth)
- `GET /api/articles/{slug}` - Get article by slug
- `PUT /api/articles/{slug}` - Update article (owner only)
- `DELETE /api/articles/{slug}` - Delete article (owner only)
- `POST /api/articles/{slug}/favorite` - Favorite article
- `DELETE /api/articles/{slug}/favorite` - Unfavorite article

## Telemetry

### Traces
Auto-instrumented spans for:
- HTTP requests (Flask)
- Database queries (SQLAlchemy/psycopg)
- Redis operations
- Celery tasks

### Metrics
- `http_requests_total` - Request count by method, endpoint, status
- `http_request_duration_seconds` - Request latency histogram
- `celery_tasks_total` - Task count by name and status

### Logs
Structured logs with trace correlation:
- `trace_id` and `span_id` for distributed tracing
- `code.file.path`, `code.function.name`, `code.line.number`
- PII masking at collector level (email addresses)

## Project Structure

```
flask-postgres/
├── app/
│   ├── __init__.py          # App factory
│   ├── config.py             # Configuration
│   ├── extensions.py         # Flask extensions
│   ├── telemetry.py          # OpenTelemetry setup
│   ├── errors.py             # Error handlers
│   ├── models/               # SQLAlchemy models
│   ├── schemas/              # Marshmallow schemas
│   ├── routes/               # Flask blueprints
│   ├── middleware/           # Auth and metrics
│   ├── services/             # Business logic
│   └── jobs/                 # Celery tasks
├── config/
│   └── otel-config.yaml      # OTel Collector config
├── scripts/
│   └── test-api.sh           # API test script
├── compose.yml               # Docker Compose
├── Dockerfile                # Multi-stage build
└── requirements.txt          # Python dependencies
```

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | dev-secret | Flask secret key |
| `DATABASE_URL` | postgresql+psycopg://... | Database connection |
| `REDIS_URL` | redis://localhost:6379/0 | Redis connection |
| `OTEL_SERVICE_NAME` | flask-postgres-app | Service name for telemetry |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | http://localhost:4318 | OTLP HTTP endpoint |

## Development

```bash
# Local development (without Docker)
cp .env.example .env
pip install -r requirements.txt

# Start PostgreSQL and Redis locally
# Then:
flask db upgrade
flask run --port 8000
```

## Celery Worker

The Celery worker has its own telemetry initialization to handle fork-based process model:

```python
@worker_process_init.connect
def init_worker_telemetry(**kwargs):
    setup_telemetry()
```

This ensures each worker process has its own OTel providers.
