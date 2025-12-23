# NestJS + PostgreSQL + OpenTelemetry

A production-ready example demonstrating NestJS REST API with TypeScript,
PostgreSQL, Redis, background jobs, WebSockets, and comprehensive
OpenTelemetry instrumentation for end-to-end observability.

> [Full Documentation](https://docs.base14.io/instrument/apps/auto-instrumentation/nestjs)

## Stack Profile

| Component         | Version  | Status | Notes                           |
| ----------------- | -------- | ------ | ------------------------------- |
| **Node.js**       | 24.x     | Active | Latest                          |
| **TypeScript**    | 5.x      | Latest | Strict mode enabled             |
| **NestJS**        | 11.x     | Latest | Latest stable                   |
| **PostgreSQL**    | 16       | Active | Alpine variant                  |
| **Redis**         | 7.x      | Active | For BullMQ job queue            |
| **TypeORM**       | 0.3.x    | Active | NestJS native integration       |
| **BullMQ**        | 5.x      | Active | Background job processing       |
| **Socket.io**     | 4.x      | Active | Real-time WebSocket events      |
| **OpenTelemetry** | 0.208.0  | Latest | SDK Node + auto-instrumentation |

**Why This Stack**: Demonstrates NestJS with TypeScript for enterprise-grade
architecture, PostgreSQL for relational data, Redis/BullMQ for background
jobs, Socket.io for real-time updates, and OpenTelemetry for complete
observability across all components.

## Architecture

Modular architecture with clear separation of concerns:

- **API Layer**: NestJS controllers with `/api/*` routes, CORS, Helmet
- **Security**: Rate limiting, JWT authentication with Passport, bcrypt
- **Validation**: class-validator for DTO validation with error messages
- **Data**: PostgreSQL with TypeORM, auto-migrations in development
- **Background Jobs**: BullMQ with Redis for async processing
- **Real-time**: WebSocket gateway for live article events
- **Observability**: OpenTelemetry automatic + custom instrumentation

**Graceful Shutdown**: Coordinated shutdown via NestJS lifecycle hooks.

## What's Instrumented

### Automatic Instrumentation

- HTTP requests and responses (NestJS/Express routes)
- PostgreSQL database queries
- Redis commands (IORedis instrumentation)
- Distributed trace propagation (W3C Trace Context)

### Custom Instrumentation

- **Traces**: Business spans for auth, CRUD, favorites, jobs, WebSocket
- **Attributes**: `user.id`, `article.id`, `article.title`, `job.id`
- **Metrics**: Authentication, articles, jobs, queue depth, errors
- **Logs**: Trace-correlated logging for errors and notifications

### Trace Propagation Demo

The publish flow demonstrates end-to-end trace propagation:

```text
article.publish (HTTP endpoint)
  └── job.process (BullMQ worker, linked via trace context)
      ├── article.publish.update (database update)
      ├── notification.send (simulated email)
      └── websocket.emit (real-time event to subscribers)
```

## Prerequisites

1. **Docker & Docker Compose** - For running services
2. **base14 Scout Account** - For viewing traces
3. **Node.js 24+** (optional) - For local development

## Quick Start

### 1. Clone and Navigate

```bash
git clone https://github.com/base-14/examples.git
cd examples/nodejs/nestjs-postgres
```

### 2. Set base14 Scout Credentials

Create a `.env.local` file with your Scout credentials:

```bash
cat > .env.local << EOF
NODE_ENV=development
APP_PORT=3000
APP_VERSION=1.0.0
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/nestjs_app
REDIS_URL=redis://redis:6379
JWT_SECRET=your-secret-key-change-in-production
JWT_EXPIRES_IN=7d
CORS_ORIGIN=*
OTEL_SERVICE_NAME=nestjs-postgres-app
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
PROMETHEUS_PORT=9464
SCOUT_ENDPOINT=https://your-tenant.base14.io:4318
SCOUT_CLIENT_ID=your_client_id
SCOUT_CLIENT_SECRET=your_client_secret
SCOUT_TOKEN_URL=https://your-tenant.base14.io/oauth/token
EOF
```

### 3. Start Services

```bash
docker compose up --build
```

This starts:

- NestJS application on port 3000
- PostgreSQL on port 5432
- Redis on port 6379
- OpenTelemetry Collector on ports 4317/4318
- Prometheus metrics on port 9464

### 4. Test the API

```bash
./scripts/test-api.sh
```

### 5. Verify Scout Integration

```bash
./scripts/verify-scout.sh
```

This script:

- Generates telemetry by exercising all API endpoints
- Triggers the publish flow (HTTP → Queue → Worker → WebSocket)
- Verifies custom metrics are being collected
- Shows expected traces in Scout

### 6. View Traces

1. Log into your base14 Scout dashboard
2. Navigate to TraceX
3. Filter by service: `nestjs-postgres-app`
4. Look for the `article.publish` trace to see propagation

## API Endpoints

### Health

| Method | Endpoint      | Description  | Auth |
| ------ | ------------- | ------------ | ---- |
| `GET`  | `/api/health` | Health check | No   |

### Authentication

| Method | Endpoint             | Description      | Auth |
| ------ | -------------------- | ---------------- | ---- |
| `POST` | `/api/auth/register` | Register user    | No   |
| `POST` | `/api/auth/login`    | Login user       | No   |
| `GET`  | `/api/auth/me`       | Get current user | Yes  |
| `POST` | `/api/auth/logout`   | Logout user      | Yes  |

### Articles

| Method   | Endpoint                    | Description             | Auth |
| -------- | --------------------------- | ----------------------- | ---- |
| `GET`    | `/api/articles`             | List articles           | No   |
| `POST`   | `/api/articles`             | Create new article      | Yes  |
| `GET`    | `/api/articles/:id`         | Get single article      | No   |
| `PUT`    | `/api/articles/:id`         | Update article (owner)  | Yes  |
| `DELETE` | `/api/articles/:id`         | Delete article (owner)  | Yes  |
| `POST`   | `/api/articles/:id/publish` | Publish article (async) | Yes  |

### Favorites

| Method   | Endpoint                     | Description         | Auth |
| -------- | ---------------------------- | ------------------- | ---- |
| `POST`   | `/api/articles/:id/favorite` | Favorite an article | Yes  |
| `DELETE` | `/api/articles/:id/favorite` | Unfavorite article  | Yes  |

## WebSocket Events

Connect to `ws://localhost:3000` with a JWT token for real-time updates:

| Event                | Direction     | Description                |
| -------------------- | ------------- | -------------------------- |
| `subscribe:articles` | Client→Server | Subscribe to updates       |
| `article:created`    | Server→Client | New article created        |
| `article:updated`    | Server→Client | Article updated            |
| `article:published`  | Server→Client | Article published          |
| `article:deleted`    | Server→Client | Article deleted            |

## Error Response Format

All errors return a consistent format with machine-readable error codes:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Validation failed",
    "statusCode": 400,
    "timestamp": "2024-01-15T10:30:00.000Z",
    "path": "/api/articles",
    "traceId": "abc123...",
    "details": {
      "validationErrors": ["Title must be at least 3 characters"]
    }
  }
}
```

Error codes: `RESOURCE_NOT_FOUND`, `UNAUTHORIZED`, `FORBIDDEN`, `CONFLICT`,
`BAD_REQUEST`, `VALIDATION_ERROR`, `INTERNAL_SERVER_ERROR`,
`RATE_LIMIT_EXCEEDED`

## Configuration

### Required Environment Variables

| Variable              | Description                | Required |
| --------------------- | -------------------------- | -------- |
| `SCOUT_ENDPOINT`      | base14 Scout OTLP endpoint | Yes      |
| `SCOUT_CLIENT_ID`     | Scout OAuth2 client ID     | Yes      |
| `SCOUT_CLIENT_SECRET` | Scout OAuth2 client secret | Yes      |
| `SCOUT_TOKEN_URL`     | Scout OAuth2 token URL     | Yes      |

### Application Environment Variables

| Variable             | Description            | Default                 |
| -------------------- | ---------------------- | ----------------------- |
| `NODE_ENV`           | Environment            | `development`           |
| `APP_PORT`           | Application port       | `3000`                  |
| `DATABASE_URL`       | PostgreSQL connection  | (required)              |
| `REDIS_URL`          | Redis connection       | `redis://localhost:6379`|
| `JWT_SECRET`         | JWT signing secret     | (required)              |
| `JWT_EXPIRES_IN`     | JWT token expiration   | `7d`                    |
| `OTEL_SERVICE_NAME`  | Service name in traces | `nestjs-postgres-app`   |
| `OTEL_EXPORTER_*`    | OTLP collector         | `http://collector:4318` |
| `PROMETHEUS_PORT`    | Prometheus port        | `9464`                  |

## Telemetry Data

### Traces

**HTTP Spans** (automatic):

- Span name: `GET /api/articles`, `POST /api/auth/login`, etc.
- Attributes: `http.method`, `http.route`, `http.status_code`

**Database Spans** (automatic):

- Span name: `pg.query`, etc.
- Attributes: `db.system=postgresql`, `db.statement`

**Redis Spans** (automatic):

- Span name: `redis-GET`, `redis-SET`, etc.
- Attributes: `db.system=redis`, `db.statement`

**Custom Business Spans**:

| Span Name               | Description                          |
| ----------------------- | ------------------------------------ |
| `auth.register`         | User registration                    |
| `auth.login`            | User login                           |
| `auth.getProfile`       | Get user profile                     |
| `article.create`        | Create article                       |
| `article.findAll`       | List articles                        |
| `article.findOne`       | Get single article                   |
| `article.update`        | Update article                       |
| `article.delete`        | Delete article                       |
| `article.publish`       | Initiate publish (HTTP)              |
| `job.process`           | Background job processing (Consumer) |
| `article.publish.update`| Update article in database           |
| `notification.send`     | Send notification                    |
| `websocket.emit`        | Emit WebSocket event                 |
| `article.favorite`      | Favorite article                     |
| `article.unfavorite`    | Unfavorite article                   |

**Custom Attributes**:

- `user.id` - User UUID
- `user.email_domain` - Email domain (privacy-safe)
- `article.id` - Article UUID
- `article.title` - Article title
- `job.id` - Background job ID
- `job.queue` - Queue name
- `pagination.page` - Current page
- `pagination.limit` - Page size

### Metrics

**Authentication**:

- `auth.login.attempts` - Login attempt counter
- `auth.login.success` - Successful login counter
- `auth.registration.total` - Registration counter (with status label)

**Articles**:

- `articles.created` - Article creation counter
- `articles.favorited` - Favorite counter
- `articles.published` - Publish counter (from background job)

**Background Jobs**:

- `jobs.enqueued` - Jobs added to queue
- `jobs.completed` - Successfully processed jobs
- `jobs.failed` - Failed jobs
- `jobs.duration` - Job processing duration histogram

**Queue Depth** (observable gauges):

- `job_queue_waiting` - Jobs waiting to be processed
- `job_queue_active` - Jobs currently being processed
- `job_queue_delayed` - Delayed jobs
- `job_queue_failed` - Failed jobs in queue
- `job_queue_completed` - Completed jobs (last 24h)

**HTTP Errors**:

- `http_errors_total` - Error counter by status code, route, and error code

**WebSocket**:

- `websocket_connections` - Active connection gauge
- `websocket_events_total` - Events emitted by type

### Logs

Trace-correlated logs are emitted for:

- HTTP 5xx errors (ERROR level)
- HTTP 4xx errors (WARN level)
- Article published notifications (INFO level)

Log attributes include `trace.id` and `span.id` for correlation.

## Example Traces

### Simple CRUD Operation

```text
HTTP POST /api/articles                    [Auto-instrumented]
 └─ article.create                         [Custom span]
     └─ pg.query INSERT                    [Auto-instrumented]
```

### Publish Flow (Trace Propagation)

```text
HTTP POST /api/articles/:id/publish        [Auto-instrumented]
 └─ article.publish                        [Custom span - enqueues job]
     │
     └─ job.process                        [Custom span - Consumer]
         ├─ article.publish.update         [Custom span]
         │   └─ pg.query UPDATE            [Auto-instrumented]
         ├─ notification.send              [Custom span]
         └─ websocket.emit                 [Custom span]
```

## Development

### Local Build

```bash
npm install
npm run build
npm run start:prod
```

### Testing

```bash
npm test                 # Unit tests
npm run test:e2e         # E2E tests
./scripts/test-api.sh    # API smoke test
./scripts/verify-scout.sh # Scout integration test
```

### Docker Commands

```bash
# Build and start all services
docker compose up --build

# Stop services
docker compose down

# View logs
docker compose logs -f app

# Rebuild after code changes
docker compose up --build app
```

### Access Services

| Service        | URL                            | Purpose             |
| -------------- | ------------------------------ | ------------------- |
| NestJS API     | <http://localhost:3000>        | Main application    |
| Health Check   | <http://localhost:3000/health> | Service health      |
| PostgreSQL     | `localhost:5432`               | Database            |
| Redis          | `localhost:6379`               | Job queue backend   |
| Prometheus     | <http://localhost:9464>        | Application metrics |
| OTel Collector | <http://localhost:4318>        | Telemetry ingestion |
| OTel Health    | <http://localhost:13133>       | Collector health    |

## Troubleshooting

### No traces appearing in Scout

1. **Check collector logs**:

   ```bash
   docker logs otel-collector
   ```

2. **Verify Scout credentials** in `.env.local`

3. **Check local traces** in collector debug output:

   ```bash
   docker logs otel-collector 2>&1 | grep "Span"
   ```

### Background jobs not processing

1. **Check Redis connection**:

   ```bash
   docker exec redis redis-cli ping
   ```

2. **View job queue status** via the application logs

### Database connection errors

1. **Check PostgreSQL health**:

   ```bash
   docker logs nestjs-postgres-db
   ```

2. **Verify PostgreSQL is ready**:

   ```bash
   docker exec nestjs-postgres-db pg_isready -U postgres
   ```

### Application won't start

1. **Check TypeScript compilation**:

   ```bash
   npm run build
   ```

2. **View application logs**:

   ```bash
   docker logs nestjs-postgres-app
   ```

## Resources

- [OpenTelemetry JavaScript](https://opentelemetry.io/docs/languages/js/)
- [NestJS Documentation](https://docs.nestjs.com/)
- [TypeORM Documentation](https://typeorm.io/)
- [BullMQ Documentation](https://docs.bullmq.io/)
- [Socket.io Documentation](https://socket.io/docs/)
- [base14 Scout Documentation](https://docs.base14.io/)

## License

MIT
