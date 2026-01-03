# Django + PostgreSQL + OpenTelemetry

Django REST API with automatic OpenTelemetry instrumentation, JWT authentication, Celery background tasks, and PostgreSQL integration with base14 Scout.

> 📚 [Full Documentation](https://docs.base14.io/instrument/apps/custom-instrumentation/python)

## Stack Profile

| Component | Version | EOL Status | Current Version |
|-----------|---------|------------|-----------------|
| **Python** | 3.14 | Oct 2030 | 3.14.2 |
| **Django** | 5.2 LTS | Apr 2028 | 5.2.9 |
| **Django REST Framework** | 3.16 | Stable | 3.16.1 |
| **PostgreSQL** | 18 | Nov 2029 | 18.1 |
| **Celery** | 5.6 | Stable | 5.6.0 |
| **Redis** | 8 | Active | 8.0 |
| **OpenTelemetry SDK** | 1.39 | N/A | 1.39.1 |

**Why This Matters:** Production-ready Django stack with LTS support, background task processing via Celery,
and comprehensive OpenTelemetry instrumentation for full observability.

## What's Instrumented

### Automatic Instrumentation

- ✅ HTTP requests and responses (Django automatic instrumentation)
- ✅ Database queries (psycopg automatic instrumentation)
- ✅ Redis operations (Redis automatic instrumentation)
- ✅ Celery task execution (Celery automatic instrumentation)
- ✅ Distributed trace propagation (W3C Trace Context)
- ✅ Log export with trace correlation (OTLP logs)
- ✅ Error tracking with automatic exception capture
- ✅ PII masking at collector level (emails redacted)

### Custom Instrumentation

- **Traces**: User authentication, article CRUD, favorites with custom spans
- **Attributes**: User ID, article slug, job metadata, error context
- **Logs**: Structured logs with trace correlation (trace_id, span_id)
- **Metrics**: HTTP metrics, auth attempts, article counts, job metrics

### What Requires Manual Work

- Business-specific custom spans and attributes
- Advanced metrics beyond HTTP and job basics
- Custom log correlation patterns
- WebSocket instrumentation (if needed)

## Technology Stack

| Component | Package | Version |
|-----------|---------|---------|
| Python | python | 3.14 |
| Django | django | 5.2.9 |
| REST Framework | djangorestframework | 3.16.1 |
| PostgreSQL Driver | psycopg[binary] | 3.2+ |
| Background Tasks | celery | 5.6.0 |
| Redis Client | redis | 5.2+ |
| Authentication | PyJWT | 2.10+ |
| OTel SDK | opentelemetry-sdk | 1.39.1 |
| OTel Django | opentelemetry-instrumentation-django | 0.60b1 |
| OTel Celery | opentelemetry-instrumentation-celery | 0.60b1 |
| OTel Psycopg | opentelemetry-instrumentation-psycopg | 0.60b1 |
| OTel Logging | opentelemetry-instrumentation-logging | 0.60b1 |
| OTel Exporter | opentelemetry-exporter-otlp | 1.39.1 |
| WSGI Server | gunicorn | 23.0+ |

## Prerequisites

1. **Docker & Docker Compose** - [Install Docker](https://docs.docker.com/get-docker/)
2. **base14 Scout Account** - [Sign up](https://base14.io)
3. **Python 3.14+** (for local development)

## Quick Start

### 1. Clone and Navigate

```bash
git clone https://github.com/base-14/examples.git
cd examples/python/django-postgres
```

### 2. Configure Environment Variables

```bash
# Copy environment template
cp .env.example .env

# Generate a secure SECRET_KEY
openssl rand -hex 32
```

Edit `.env` and update the required values.

### 3. Set base14 Scout Credentials

Add these to your environment or `.env` file:

```bash
export SCOUT_ENDPOINT=https://your-tenant.base14.io:4318
export SCOUT_CLIENT_ID=your_client_id
export SCOUT_CLIENT_SECRET=your_client_secret
export SCOUT_TOKEN_URL=https://your-tenant.base14.io/oauth/token
```

### 4. Start Services

```bash
docker compose up -d
```

### 5. Verify Health

```bash
# Check all services are running
docker compose ps

# Test health endpoint
curl http://localhost:8000/api/health
```

### 6. Run API Tests

```bash
./scripts/test-api.sh
```

## API Endpoints

### Authentication

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| POST | `/api/register` | Register new user | No |
| POST | `/api/login` | Login and get JWT token | No |
| GET | `/api/user` | Get current user profile | Yes |
| POST | `/api/logout` | Logout | Yes |

### Articles

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/articles/` | List articles (paginated) | No |
| POST | `/api/articles/` | Create article | Yes |
| GET | `/api/articles/{slug}` | Get single article | No |
| PUT | `/api/articles/{slug}` | Update article | Yes (owner) |
| DELETE | `/api/articles/{slug}` | Delete article | Yes (owner) |
| POST | `/api/articles/{slug}/favorite` | Favorite article | Yes |
| DELETE | `/api/articles/{slug}/favorite` | Unfavorite article | Yes |

### System

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check (db, redis) |

## API Examples

### Register User

```bash
curl -X POST http://localhost:8000/api/register \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@example.com", "name": "Alice", "password": "password123"}'
```

Response:

```json
{
  "user": {
    "id": 1,
    "email": "alice@example.com",
    "name": "Alice",
    "bio": "",
    "image": "",
    "created_at": "2025-12-27T06:42:13Z"
  },
  "token": {
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "Bearer"
  }
}
```

### Create Article

```bash
curl -X POST http://localhost:8000/api/articles/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"title": "My Article", "body": "Article content here", "description": "A brief description"}'
```

Response:

```json
{
  "slug": "my-article-1735284134081",
  "title": "My Article",
  "description": "A brief description",
  "body": "Article content here",
  "author": {"id": 1, "email": "alice@example.com", "name": "Alice"},
  "favorites_count": 0,
  "favorited": false,
  "created_at": "2025-12-27T06:42:14Z"
}
```

### Health Check

```bash
curl http://localhost:8000/api/health
```

Response:

```json
{
  "status": "healthy",
  "components": {
    "database": "healthy",
    "redis": "healthy"
  },
  "service": {
    "name": "django-postgres-celery-app",
    "version": "1.0.0"
  }
}
```

## Telemetry Data

### Traces

Distributed traces capture the full request lifecycle:

- ✅ HTTP request handling with route attributes
- ✅ Database queries with SQL statements
- ✅ Redis operations
- ✅ Celery task execution with job context
- ✅ Custom business spans (auth, CRUD, favorites)

**Distributed Tracing Example** - `POST /api/articles/` creates an article and triggers a Celery task, all correlated by the same trace ID:

```text
App (django-postgres-celery-app):
  → HTTP POST /api/articles/
  → article.create span
  → apply_async/send_article_notification span

Worker (django-postgres-celery-worker):
  → run/send_article_notification span
  → job.send_article_notification span

All spans share: otelTraceID: 59e443df8f7614a5b21c11d8c8f83a8d
```

### Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `http_requests_total` | Counter | Total HTTP requests by method, route, status |
| `http_request_duration_ms` | Histogram | Request latency in milliseconds |
| `auth.login.attempts` | Counter | Login attempts by status (success/failed) |
| `articles.created` | Counter | Articles created by author |
| `jobs.completed` | Counter | Completed background jobs |
| `jobs.failed` | Counter | Failed background jobs |
| `jobs.duration_ms` | Histogram | Job execution time |

### Logs

All logs are exported via OTLP with trace correlation:

```text
LogRecord:
  SeverityText: INFO
  Body: "User registered: al***@example.com"
  Attributes:
    → otelTraceID: "59e443df8f7614a5b21c11d8c8f83a8d"
    → otelSpanID: "867d079fdf8865b7"
    → code.file.path: "/app/apps/users/views.py"
    → code.function.name: "register"
    → code.line.number: 40
```

**Log messages from app and worker are correlated by trace ID**, enabling end-to-end debugging across services.

## OpenTelemetry Configuration

### Instrumentation Setup

The telemetry is initialized in `apps/core/telemetry.py`:

```python
from opentelemetry import trace, metrics, _logs
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.instrumentation.django import DjangoInstrumentor
from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor

# Auto-instrument frameworks
DjangoInstrumentor().instrument()
PsycopgInstrumentor().instrument()
CeleryInstrumentor().instrument()
LoggingInstrumentor().instrument(set_logging_format=True)
```

For Celery workers, telemetry is initialized per-worker process via `worker_process_init` signal in `config/celery.py`.

### Custom Spans

```python
from apps.core.telemetry import get_tracer

tracer = get_tracer(__name__)

with tracer.start_as_current_span("article.create") as span:
    span.set_attribute("user.id", user.id)
    span.set_attribute("article.slug", article.slug)
    # ... business logic
```

### Custom Metrics

```python
from apps.core.telemetry import get_meter

meter = get_meter(__name__)
articles_created = meter.create_counter("articles.created")

articles_created.add(1, {"author_id": str(user.id)})
```

### PII Masking

Email addresses are automatically masked at the collector level using the `transform` processor:

```yaml
# config/otel-config.yaml
processors:
  transform/pii:
    error_mode: ignore
    log_statements:
      - context: log
        statements:
          # alice@example.com → al***@example.com
          - replace_pattern(body, "([a-zA-Z0-9._%+-]{2})[a-zA-Z0-9._%+-]*@...", "$$1***@$$2")
    trace_statements:
      - context: span
        statements:
          - replace_pattern(attributes["user.email"], "...", "$$1***@$$2")
```

This ensures PII is redacted before data leaves the collector, without requiring application code changes.

## Database Schema

### Users Table

| Column | Type | Description |
|--------|------|-------------|
| id | BIGSERIAL | Primary key |
| email | VARCHAR(255) | Unique email |
| password | VARCHAR(128) | Hashed password |
| name | VARCHAR(255) | Display name |
| bio | TEXT | User bio |
| image | VARCHAR(200) | Avatar URL |
| created_at | TIMESTAMP | Creation time |
| updated_at | TIMESTAMP | Last update |

### Articles Table

| Column | Type | Description |
|--------|------|-------------|
| id | BIGSERIAL | Primary key |
| slug | VARCHAR(255) | Unique URL slug |
| title | VARCHAR(255) | Article title |
| description | TEXT | Brief description |
| body | TEXT | Article content |
| author_id | BIGINT | FK to users |
| favorites_count | INTEGER | Cached favorite count |
| created_at | TIMESTAMP | Creation time |
| updated_at | TIMESTAMP | Last update |

### Favorites Table

| Column | Type | Description |
|--------|------|-------------|
| id | BIGSERIAL | Primary key |
| user_id | BIGINT | FK to users |
| article_id | BIGINT | FK to articles |
| created_at | TIMESTAMP | Creation time |

## Project Structure

```text
django-postgres/
├── config/
│   ├── settings.py        # Django settings
│   ├── celery.py          # Celery configuration
│   ├── urls.py            # URL routing
│   ├── wsgi.py            # WSGI application
│   └── otel-config.yaml   # OTel Collector config
├── apps/
│   ├── core/
│   │   ├── telemetry.py   # OpenTelemetry setup
│   │   ├── middleware.py  # Metrics middleware
│   │   ├── exceptions.py  # Exception handlers
│   │   └── views.py       # Health endpoint
│   ├── users/
│   │   ├── models.py      # User model
│   │   ├── views.py       # Auth endpoints
│   │   ├── serializers.py # DRF serializers
│   │   └── authentication.py # JWT auth
│   ├── articles/
│   │   ├── models.py      # Article, Favorite models
│   │   ├── views.py       # CRUD endpoints
│   │   └── serializers.py # DRF serializers
│   └── jobs/
│       └── tasks.py       # Celery tasks
├── scripts/
│   └── test-api.sh        # API test script
├── tests/
│   └── conftest.py        # Pytest fixtures
├── compose.yml            # Docker Compose
├── Dockerfile             # Multi-stage build
└── requirements.txt       # Dependencies
```

## Development

### Local Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start infrastructure services
docker compose up -d postgres redis otel-collector

# Run migrations
python manage.py migrate

# Start development server
python manage.py runserver

# Start Celery worker (separate terminal)
celery -A config worker --loglevel=info
```

### Running Tests

```bash
# API integration tests
./scripts/test-api.sh

# Unit tests with pytest
pytest tests/ -v

# With coverage
pytest tests/ --cov=apps --cov-report=html
```

## Docker Commands

```bash
# Build and start all services
docker compose up -d --build

# View logs
docker compose logs -f app celery

# Execute Django commands
docker compose exec app python manage.py migrate
docker compose exec app python manage.py createsuperuser

# Stop services
docker compose down

# Clean up volumes
docker compose down -v
```

## View in Scout

After starting the application and generating some traffic:

1. Log in to [base14 Scout](https://app.base14.io)
2. Navigate to **Services** → **django-postgres-celery-app**
3. View distributed traces, metrics, and logs
4. Explore the service map to see dependencies

## Troubleshooting

### Services not starting

```bash
# Check health status
docker compose ps
docker compose logs postgres
docker compose logs redis
```

### Database connection errors

```bash
# Verify PostgreSQL is ready
docker compose exec postgres pg_isready -U postgres

# Check connection from app
docker compose exec app python -c "from django.db import connection; connection.ensure_connection()"
```

### Celery tasks not executing

```bash
# Check worker logs
docker compose logs celery

# Verify Redis connection
docker compose exec redis redis-cli ping
```

### No telemetry data in Scout

```bash
# Check collector health
curl http://localhost:13133/health

# View collector logs
docker compose logs otel-collector

# Verify credentials are set
echo $SCOUT_CLIENT_ID
```

## Resources

- [Django Documentation](https://docs.djangoproject.com/en/5.2/)
- [Django REST Framework](https://www.django-rest-framework.org/)
- [OpenTelemetry Python](https://opentelemetry.io/docs/languages/python/)
- [Celery Documentation](https://docs.celeryq.dev/)
- [base14 Scout Documentation](https://docs.base14.io)
