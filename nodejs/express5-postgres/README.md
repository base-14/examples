# Express 5 + PostgreSQL + OpenTelemetry

A production-ready example demonstrating Express 5 REST API with TypeScript, PostgreSQL, Redis,
background jobs, WebSockets, and comprehensive OpenTelemetry instrumentation for end-to-end observability.

> [Full Documentation](https://docs.base14.io/instrument/apps/auto-instrumentation/nodejs)

## Stack Profile

| Component         | Version  | EOL Status | Notes                          |
| ----------------- | -------- | ---------- | ------------------------------ |
| **Node.js**       | 24.x     | Apr 2027   | LTS release                    |
| **TypeScript**    | 5.x      | Current    | Strict mode enabled            |
| **Express**       | 5.x      | Active     | Latest major version           |
| **PostgreSQL**    | 18       | Nov 2029   | Alpine variant                 |
| **Redis**         | 8.x      | Active     | For BullMQ job queue           |
| **Drizzle ORM**   | 0.38.x   | Active     | Type-safe ORM with migrations  |
| **BullMQ**        | 5.x      | Active     | Background job processing      |
| **Socket.io**     | 4.x      | Active     | Real-time WebSocket events     |
| **OpenTelemetry** | 0.57.x   | Latest     | SDK Node + auto-instrumentation|

**Why This Stack**: Demonstrates Express 5 with TypeScript for modern Node.js development, PostgreSQL for relational data,
Redis/BullMQ for background jobs, Socket.io for real-time updates, and OpenTelemetry for complete observability across all components.

## What's Instrumented

### Automatic Instrumentation

- HTTP requests and responses (Express routes)
- PostgreSQL database queries (pg driver)
- Redis commands (ioredis instrumentation)
- Distributed trace propagation (W3C Trace Context)

### Custom Instrumentation

- **Traces**: Business spans for auth, CRUD, favorites, background jobs, WebSocket events
- **Attributes**: `user.id`, `user.email`, `article.id`, `article.slug`, `job.id`
- **Metrics**: Authentication attempts, article operations, job metrics, favorites, errors
- **Logs**: Trace-correlated logging for errors and important events

### Trace Propagation Demo

The notification flow demonstrates end-to-end trace propagation:

```text
article.favorite (HTTP endpoint)
  └── job.enqueue (BullMQ task, linked via trace context)
      ├── job.process (background worker)
      ├── notification.send (simulated notification)
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
cd examples/nodejs/express5-postgres
```

### 2. Set base14 Scout Credentials

Create a `.env` file with your Scout credentials:

```bash
cat > .env << EOF
NODE_ENV=development
PORT=8000
LOG_LEVEL=debug
JWT_SECRET=your-secret-key-change-in-production-must-be-32-chars
JWT_EXPIRES_IN=7d
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/express_app
REDIS_URL=redis://redis:6379
OTEL_SERVICE_NAME=express5-postgres-app
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
SCOUT_ENDPOINT=https://your-tenant.base14.io:4318
SCOUT_CLIENT_ID=your_client_id
SCOUT_CLIENT_SECRET=your_client_secret
SCOUT_TOKEN_URL=https://your-tenant.base14.io/oauth/token
SCOUT_ENVIRONMENT=development
EOF
```

### 3. Start Services

```bash
docker compose up --build
```

This starts:

- Express 5 application on port 8000
- PostgreSQL on port 5432
- Redis on port 6379
- BullMQ worker for background jobs
- OpenTelemetry Collector on ports 4317/4318

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
- Triggers the notification flow (HTTP → Queue → Worker → WebSocket)
- Verifies custom metrics are being collected
- Shows expected traces in Scout

### 6. View Traces

1. Log into your base14 Scout dashboard
2. Navigate to TraceX
3. Filter by service: `express5-postgres-app`
4. Look for the `article.favorite` trace to see propagation

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

| Method   | Endpoint                      | Description              | Auth |
| -------- | ----------------------------- | ------------------------ | ---- |
| `GET`    | `/api/articles`               | List articles            | No   |
| `POST`   | `/api/articles`               | Create new article       | Yes  |
| `GET`    | `/api/articles/:slug`         | Get single article       | No   |
| `PUT`    | `/api/articles/:slug`         | Update article (owner)   | Yes  |
| `DELETE` | `/api/articles/:slug`         | Delete article (owner)   | Yes  |

### Favorites

| Method   | Endpoint                         | Description         | Auth |
| -------- | -------------------------------- | ------------------- | ---- |
| `POST`   | `/api/articles/:slug/favorite`   | Favorite an article | Yes  |
| `DELETE` | `/api/articles/:slug/favorite`   | Unfavorite article  | Yes  |

## WebSocket Events

Connect to `ws://localhost:8000` with a JWT token for real-time updates:

| Event                | Direction     | Description                |
| -------------------- | ------------- | -------------------------- |
| `subscribe:articles` | Client→Server | Subscribe to updates       |
| `article:created`    | Server→Client | New article created        |
| `article:updated`    | Server→Client | Article updated            |
| `article:deleted`    | Server→Client | Article deleted            |
| `article:favorited`  | Server→Client | Article favorited          |

## Error Response Format

All errors return a consistent format with machine-readable error codes:

```json
{
  "error": "Email already exists",
  "trace_id": "abc123..."
}
```

Error messages include trace IDs for correlation with telemetry data.

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
| `PORT`               | Application port       | `8000`                  |
| `LOG_LEVEL`          | Logging level          | `info`                  |
| `DATABASE_URL`       | PostgreSQL connection  | (required)              |
| `REDIS_URL`          | Redis connection       | `redis://localhost:6379`|
| `JWT_SECRET`         | JWT signing secret     | (required)              |
| `JWT_EXPIRES_IN`     | JWT token expiration   | `7d`                    |
| `OTEL_SERVICE_NAME`  | Service name in traces | `express5-postgres-app` |
| `OTEL_EXPORTER_*`    | OTLP collector         | `http://collector:4318` |

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
| `article.findBySlug`    | Get single article                   |
| `article.update`        | Update article                       |
| `article.delete`        | Delete article                       |
| `article.favorite`      | Favorite article                     |
| `article.unfavorite`    | Unfavorite article                   |
| `job.enqueue`           | Enqueue background job               |
| `job.process`           | Process background job (worker)      |
| `notification.send`     | Send notification                    |
| `websocket.emit`        | Emit WebSocket event                 |

**Custom Attributes**:

- `user.id` - User ID
- `user.email` - User email
- `article.id` - Article ID
- `article.slug` - Article slug
- `job.id` - Background job ID
- `job.queue` - Queue name
- `pagination.page` - Current page
- `pagination.limit` - Page size

### Metrics

**Authentication**:

- `auth.login.attempts` - Login attempt counter
- `auth.login.success` - Successful login counter
- `auth.registration.total` - Registration counter

**Articles**:

- `articles.created` - Article creation counter
- `articles.updated` - Article update counter
- `articles.deleted` - Article deletion counter
- `articles.favorited` - Favorite counter

**Background Jobs**:

- `jobs.enqueued` - Jobs added to queue
- `jobs.completed` - Successfully processed jobs
- `jobs.failed` - Failed jobs
- `jobs.duration` - Job processing duration histogram

**HTTP Errors**:

- `http_errors_total` - Error counter by status code and route

**WebSocket**:

- `websocket_connections` - Active connection gauge
- `websocket_events_total` - Events emitted by type

### Logs

Trace-correlated logs are emitted for:

- HTTP 5xx errors (ERROR level)
- HTTP 4xx errors (WARN level)
- Important business events (INFO level)

Log attributes include `trace.id` and `span.id` for correlation.

## Database Schema

### Users Table

| Column        | Type         | Description         |
| ------------- | ------------ | ------------------- |
| id            | SERIAL       | Primary key         |
| email         | VARCHAR(255) | Unique email        |
| password_hash | VARCHAR(255) | Hashed password     |
| name          | VARCHAR(255) | Display name        |
| bio           | TEXT         | User bio            |
| image         | VARCHAR(500) | Avatar URL          |
| created_at    | TIMESTAMP    | Creation time       |
| updated_at    | TIMESTAMP    | Last update         |

### Articles Table

| Column          | Type         | Description         |
| --------------- | ------------ | ------------------- |
| id              | SERIAL       | Primary key         |
| slug            | VARCHAR(255) | Unique URL slug     |
| title           | VARCHAR(255) | Article title       |
| description     | TEXT         | Brief description   |
| body            | TEXT         | Article content     |
| author_id       | INTEGER      | FK to users         |
| favorites_count | INTEGER      | Cached favorite cnt |
| created_at      | TIMESTAMP    | Creation time       |
| updated_at      | TIMESTAMP    | Last update         |

### Favorites Table

| Column     | Type      | Description         |
| ---------- | --------- | ------------------- |
| id         | SERIAL    | Primary key         |
| user_id    | INTEGER   | FK to users         |
| article_id | INTEGER   | FK to articles      |
| created_at | TIMESTAMP | Creation time       |

## Project Structure

```text
express5-postgres/
├── config/
│   └── otel-config.yaml    # OTel Collector config
├── src/
│   ├── config/             # Application config
│   │   └── index.ts
│   ├── db/                 # Database layer
│   │   ├── index.ts        # Drizzle client
│   │   ├── schema.ts       # Database schema
│   │   └── migrate.ts      # Migration runner
│   ├── jobs/               # Background jobs
│   │   ├── queue.ts        # BullMQ queue setup
│   │   └── worker.ts       # Job worker
│   ├── middleware/         # Express middleware
│   │   ├── auth.ts         # JWT auth middleware
│   │   ├── error.ts        # Error handling
│   │   └── metrics.ts      # Metrics collection
│   ├── routes/             # API routes
│   │   ├── index.ts        # Route registration
│   │   ├── health.ts       # Health check
│   │   ├── auth.ts         # Auth endpoints
│   │   └── articles.ts     # Article endpoints
│   ├── services/           # Business logic
│   │   ├── auth.ts         # Auth service
│   │   └── article.ts      # Article service
│   ├── types/              # TypeScript types
│   ├── app.ts              # Express app setup
│   ├── index.ts            # Entry point
│   ├── socket.ts           # WebSocket setup
│   ├── telemetry.ts        # OTel setup
│   └── logger.ts           # Logger config
├── scripts/
│   └── test-api.sh         # API test script
├── tests/
│   └── setup.ts            # Test configuration
├── compose.yml             # Docker Compose
├── Dockerfile              # Multi-stage build
├── drizzle.config.ts       # Drizzle ORM config
└── package.json            # Dependencies
```

## Development

### Local Setup

```bash
npm install
npm run db:generate    # Generate migrations
npm run db:migrate     # Run migrations
npm run dev            # Start dev server
```

### Testing

```bash
npm test                  # Unit tests
./scripts/test-api.sh     # API smoke test
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
| Express API    | <http://localhost:8000>        | Main application    |
| Health Check   | <http://localhost:8000/api/health> | Service health  |
| PostgreSQL     | `localhost:5432`               | Database            |
| Redis          | `localhost:6379`               | Job queue backend   |
| OTel Collector | <http://localhost:4318>        | Telemetry ingestion |
| OTel Health    | <http://localhost:13133>       | Collector health    |

## Troubleshooting

### No traces appearing in Scout

1. **Check collector logs**:

   ```bash
   docker logs otel-collector
   ```

2. **Verify Scout credentials** in `.env` file

3. **Check local traces** in collector debug output:

   ```bash
   docker logs otel-collector 2>&1 | grep "Span"
   ```

### Background jobs not processing

1. **Check Redis connection**:

   ```bash
   docker exec redis redis-cli ping
   ```

2. **View worker logs**:

   ```bash
   docker compose logs worker
   ```

3. **Verify job queue status** via application logs

### Database connection errors

1. **Check PostgreSQL health**:

   ```bash
   docker logs postgres
   ```

2. **Verify PostgreSQL is ready**:

   ```bash
   docker exec postgres pg_isready -U postgres
   ```

3. **Check database exists**:

   ```bash
   docker exec postgres psql -U postgres -l
   ```

### Application won't start

1. **Check TypeScript compilation**:

   ```bash
   npm run build
   ```

2. **View application logs**:

   ```bash
   docker logs express5-postgres-app
   ```

3. **Verify environment variables**:

   ```bash
   docker exec express5-postgres-app env | grep -E '(DATABASE|REDIS|OTEL)'
   ```

## Resources

- [OpenTelemetry JavaScript](https://opentelemetry.io/docs/languages/js/)
- [Express 5 Documentation](https://expressjs.com/en/5x/api.html)
- [Drizzle ORM Documentation](https://orm.drizzle.team/)
- [BullMQ Documentation](https://docs.bullmq.io/)
- [Socket.io Documentation](https://socket.io/docs/)
- [base14 Scout Documentation](https://docs.base14.io/)

