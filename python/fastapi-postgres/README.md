# FastAPI + Python 3.x + PostgreSQL + OpenTelemetry

FastAPI application with automatic OpenTelemetry instrumentation,
JWT authentication, and PostgreSQL integration with base14 Scout.

> 📚 [Full Documentation](
> <https://docs.base14.io/instrument/apps/custom-instrumentation/python>)

## Stack Profile

| Component | Version | EOL Status | Current Version |
| --------- | ------- | ---------- | --------------- |
| **Python** | 3.13 | Active | 3.13.9 |
| **FastAPI** | 0.128.0 | Stable | 0.128.0 |
| **PostgreSQL** | 18 | Active | 18.1 |
| **OpenTelemetry** | 1.39.1 | N/A | 1.39.1 |
| **SQLAlchemy** | 2.0.45 | Stable | 2.0.45 |

**Why This Matters:** Modern Python stack with FastAPI's high performance
and automatic OpenTelemetry instrumentation for comprehensive observability.

## What's Instrumented

### Automatic Instrumentation

- ✅ HTTP requests and responses (FastAPI automatic instrumentation)
- ✅ Database queries (SQLAlchemy automatic instrumentation)
- ✅ Distributed trace propagation (W3C Trace Context)
- ✅ Error tracking with automatic exception capture

### Custom Instrumentation

- **Traces**: Post and user CRUD operations with custom spans
- **Attributes**: User data, post metadata, SQL operations
- **Logs**: Structured logs with trace correlation
- **Metrics**: Custom HTTP metrics middleware (request count, duration, errors)

### What Requires Manual Work

- Business-specific custom spans and attributes
- Advanced metrics beyond HTTP basics
- Custom log correlation patterns

## Technology Stack

| Component | Package | Version |
| --------- | ------- | ------- |
| Python | python | 3.13 |
| FastAPI | fastapi[all] | 0.128.0 |
| PostgreSQL Driver | psycopg2-binary | 2.9.10 |
| SQLAlchemy | SQLAlchemy | 2.0.45 |
| Pydantic | pydantic | 2.12.5 |
| Authentication | PyJWT, passlib, bcrypt | 2.10.1, 1.7.4, 4.2.1 |
| OTel SDK | opentelemetry-sdk | 1.39.1 |
| OTel Instrumentation | opentelemetry-instrumentation-fastapi | 0.60b0 |
| OTel Exporter | opentelemetry-exporter-otlp | 1.39.1 |
| Database Migrations | alembic | 1.14.0 |

## Prerequisites

1. **Docker & Docker Compose** - [Install Docker](https://docs.docker.com/get-docker/)
2. **base14 Scout Account** - [Sign up](https://base14.io)
3. **Python 3.13+** (for local development)

## Quick Start

```bash
# Clone and navigate
git clone https://github.com/base-14/examples.git
cd examples/python/fastapi-postgres

# Copy environment template
cp .env.example .env
```

### 1. Configure Environment Variables

Edit `.env` and update the required values:

```bash
# Generate a secure SECRET_KEY
SECRET_KEY=$(openssl rand -hex 32)

# Set database password
DB_PASSWORD=your_database_password

# Configure CORS (comma-separated origins)
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8080
```

### 2. Set base14 Scout Credentials

Add these to your `.env` file:

```bash
SCOUT_ENDPOINT=https://your-tenant.base14.io:4318
SCOUT_CLIENT_ID=your_client_id
SCOUT_CLIENT_SECRET=your_client_secret
SCOUT_TOKEN_URL=https://your-tenant.base14.io/oauth/token
```

See the [base14 Collector Setup Guide](
<https://docs.base14.io/category/opentelemetry-collector-setup>)
for obtaining credentials.

### 3. Start Services

```bash
docker compose up --build
```

This starts:

- **app**: FastAPI application on port 8000
- **postgres**: PostgreSQL 18 database
- **otel-collector**: OpenTelemetry Collector 0.140.0

### 4. Run Database Migrations

```bash
docker compose exec app alembic upgrade head
```

### 5. Test the API

```bash
./scripts/test-api.sh
```

The test script exercises all endpoints and verifies telemetry.

### 6. View Traces

Navigate to your Scout dashboard to view traces and metrics:

```text
https://your-tenant.base14.io
```

## Configuration

### Required Environment Variables

The OpenTelemetry Collector requires base14 Scout credentials to export
telemetry data:

| Variable | Required | Description |
| -------- | -------- | ----------- |
| `SCOUT_ENDPOINT` | Yes | base14 Scout OTLP endpoint |
| `SCOUT_CLIENT_ID` | Yes | OAuth2 client ID from base14 Scout |
| `SCOUT_CLIENT_SECRET` | Yes | OAuth2 client secret from base14 Scout |
| `SCOUT_TOKEN_URL` | Yes | OAuth2 token endpoint |

### Application Environment Variables

See `.env.example` for all available configuration options:

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `DB_HOSTNAME` | `postgres` | PostgreSQL hostname |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DB_PASSWORD` | Required | PostgreSQL password |
| `DB_NAME` | `fastapi` | Database name |
| `DB_USERNAME` | `postgres` | Database username |
| `SECRET_KEY` | Required | JWT secret key (`openssl rand -hex 32`) |
| `ALGORITHM` | `HS256` | JWT algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | JWT token expiration |
| `ALLOWED_ORIGINS` | `http://localhost:3000` | CORS allowed origins |
| `OTEL_SERVICE_NAME` | `fastapi-postgres-app` | Service name |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://otel-collector:4318` | Collector |

### Resource Attributes

Automatically included in telemetry:

```properties
service.name=fastapi-postgres-app
service.version=1.0.0
deployment.environment=development
```

## API Endpoints

### Application Endpoints

| Method | Endpoint | Description | Auth Required |
| ------ | -------- | ----------- | ------------- |
| `GET` | `/` | Root endpoint | No |
| `POST` | `/users` | Create user | No |
| `GET` | `/users/{id}` | Get user by ID | Yes |
| `POST` | `/login` | User login | No |
| `GET` | `/posts` | List all posts | Yes |
| `GET` | `/posts/{id}` | Get post by ID | Yes |
| `POST` | `/posts` | Create post | Yes |
| `PUT` | `/posts/{id}` | Update post | Yes |
| `DELETE` | `/posts/{id}` | Delete post | Yes |
| `POST` | `/vote` | Vote on post | Yes |
| `DELETE` | `/vote` | Remove vote | Yes |

### Example Requests

```bash
# Create a user
curl -X POST http://localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@example.com", "password": "securepass123"}'

# Login
curl -X POST http://localhost:8000/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=alice@example.com&password=securepass123"

# Create a post (with JWT token)
curl -X POST http://localhost:8000/posts \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{"title": "My First Post", "content": "This is the content", "published": true}'

# List posts
curl http://localhost:8000/posts \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# Vote on a post
curl -X POST http://localhost:8000/vote \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{"post_id": 1, "dir": 1}'
```

## Telemetry Data

### Traces

- **HTTP requests**: Method, path, status code, duration
- **Database queries**: Full SQL statements with parameters
- **Authentication**: Login and token validation spans
- **Business operations**: Post CRUD, user registration, voting
- **Span hierarchy**: HTTP → Route Handler → Database operations
- **Attributes**: User IDs, post IDs, SQL table names
- **Errors**: Automatic exception capture with stack traces

### Logs

Structured logs with automatic trace correlation (to be implemented):

```json
{
  "timestamp": "2025-12-02T14:20:42Z",
  "severity": "info",
  "message": "Post created successfully",
  "trace_id": "6ec1f6ce672d342770671880fbf89ab9",
  "span_id": "cc5e4bb6c023c846",
  "service.name": "fastapi-postgres-app",
  "post.id": 42,
  "user.id": 1
}
```

### Metrics

Custom metrics via MetricsMiddleware:

- **http.server.request.count**: Total HTTP requests by method, route, and status
- **http.server.request.duration**: Request duration histogram
- **http.server.request.errors**: Error count by route

## OpenTelemetry Configuration

### Dependencies (requirements.txt)

```python
fastapi[all]
opentelemetry-instrumentation-fastapi
opentelemetry-sdk
opentelemetry-instrumentation-requests
opentelemetry-exporter-otlp
opentelemetry-api
```

### Implementation

See `app/telemetry.py` for complete implementation.

Key aspects:

- Automatic FastAPI instrumentation
- OTLP HTTP exporter to collector
- Resource attributes configuration
- Batch span processor for efficient export
- Custom metrics middleware

### Custom Instrumentation Example

FastAPI endpoints automatically create spans. Custom metrics are added via middleware.

See `app/MetricsMiddleware.py` for custom metrics implementation:

```python
from opentelemetry import metrics

class MetricsMiddleware:
    def __init__(self, app):
        self.app = app
        meter = metrics.get_meter(__name__)
        self.request_counter = meter.create_counter(
            "http.server.request.count",
            description="Total HTTP requests"
        )
        self.duration_histogram = meter.create_histogram(
            "http.server.request.duration",
            description="HTTP request duration"
        )
```

See `app/routers/post.py` for automatic span creation examples.

## Database Schema

### Users Table

```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR NOT NULL UNIQUE,
    password VARCHAR NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    phone_number VARCHAR
);
```

### Posts Table

```sql
CREATE TABLE posts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR NOT NULL,
    content VARCHAR NOT NULL,
    published BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### Votes Table

```sql
CREATE TABLE votes (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, post_id)
);
```

## Development

### Local Build

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export DB_HOSTNAME=localhost
export DB_PASSWORD=your_password
# ... other variables from .env.example

# Run migrations
alembic upgrade head

# Start server
uvicorn app.main:app --reload
```

### Docker Commands

```bash
# Build and start
docker compose up --build

# Start in background
docker compose up -d

# View logs
docker compose logs -f app
docker compose logs -f otel-collector

# Stop services
docker compose down

# Rebuild
docker compose build
```

### Access Services

```bash
# Application logs
docker compose logs -f app

# API documentation (Swagger UI)
open http://localhost:8000/docs

# Database access
docker exec -it fastapi-postgres psql -U postgres -d fastapi

# OTel collector zpages
open http://localhost:55679/debug/servicez
```

## Troubleshooting

### No traces appearing in Scout

1. Check OTel collector logs:

   ```bash
   docker compose logs otel-collector
   ```

2. Verify Scout credentials in environment variables

3. Test collector health:

   ```bash
   curl http://localhost:55679/debug/servicez
   ```

4. Verify telemetry setup in application logs

### Database connection errors

1. Verify PostgreSQL is running:

   ```bash
   docker compose ps postgres
   ```

2. Check database credentials in `.env` or environment variables

3. Test connection:

   ```bash
   docker exec fastapi-postgres pg_isready -U postgres
   ```

### Authentication errors

1. Ensure JWT secret is set in environment:

   ```bash
   echo $SECRET_KEY
   ```

2. Verify token format in Authorization header:

   ```text
   Authorization: Bearer YOUR_JWT_TOKEN
   ```

3. Check token expiration (default 60 minutes)

## Resources

- [OpenTelemetry Python Documentation](
  <https://opentelemetry.io/docs/languages/python/>) - Python SDK reference
- [FastAPI Documentation](https://fastapi.tiangolo.com/) - FastAPI framework
- [SQLAlchemy](https://www.sqlalchemy.org/) - Python SQL toolkit and ORM
- [base14 Scout](https://base14.io/scout) - Observability platform
- [base14 Documentation](https://docs.base14.io) - Full instrumentation guides
