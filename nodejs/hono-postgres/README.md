# Hono + PostgreSQL + OpenTelemetry

A production-ready example demonstrating Hono REST API with TypeScript,
PostgreSQL, Redis, background jobs (BullMQ), and comprehensive OpenTelemetry
instrumentation for end-to-end observability.

> [Full Documentation](https://docs.base14.io/instrument/apps/auto-instrumentation/hono)

## Stack Profile

| Component         | Version  | Status | Notes                           |
| ----------------- | -------- | ------ | ------------------------------- |
| **Node.js**       | 24.x     | Active | Latest LTS                      |
| **TypeScript**    | 5.x      | Latest | Strict mode enabled             |
| **Hono**          | 4.x      | Latest | Ultrafast web framework         |
| **PostgreSQL**    | 18       | Active | Alpine variant                  |
| **Redis**         | 8.x      | Active | For BullMQ job queue            |
| **Drizzle ORM**   | 0.45.x   | Latest | Type-safe SQL                   |
| **BullMQ**        | 5.x      | Active | Background job processing       |
| **Pino**          | 10.x     | Active | Fast JSON logging               |
| **OpenTelemetry** | 0.212.0  | Latest | SDK Node + auto-instrumentation |

**Why This Stack**: Demonstrates Hono with TypeScript for ultrafast, edge-ready
APIs, PostgreSQL with Drizzle ORM for type-safe database access, Redis/BullMQ
for background jobs, Pino for structured logging, and OpenTelemetry for complete
observability across all components.

## Architecture

Modular architecture with clear separation of concerns:

- **API Layer**: Hono routes with `/api/*` prefix, CORS, secure headers
- **Security**: In-memory rate limiting, JWT authentication, bcrypt password hashing
- **Validation**: Zod schemas via `@hono/zod-validator`
- **Data**: PostgreSQL with Drizzle ORM, migration support
- **Background Jobs**: BullMQ with Redis for async notification processing
- **Observability**: OpenTelemetry automatic + custom instrumentation via `@hono/otel`

**Graceful Shutdown**: Coordinated shutdown via Node.js signal handlers.

## What's Instrumented

### Automatic Instrumentation

- HTTP requests and responses (`@hono/otel` for route-parameterized spans)
- PostgreSQL database queries (pg instrumentation)
- Redis commands (IORedis instrumentation)
- Distributed trace propagation (W3C Trace Context)

### Custom Instrumentation

- **Traces**: Business spans for auth, CRUD, favorites, background jobs
- **Attributes**: `user.id`, `user.email_domain`, `article.id`, `article.slug`
- **Metrics**: Prometheus metrics at `/metrics` endpoint
- **Logs**: Pino structured logging with trace correlation

### Trace Propagation Demo

The article creation flow demonstrates end-to-end trace propagation:

```text
POST /api/articles (HTTP endpoint)
  └── article.create (custom span)
      ├── pg.query INSERT (database)
      └── job.enqueue.article-created (PRODUCER span)
          └── job.article-created (CONSUMER span, worker service)
```

## Prerequisites

1. **Docker & Docker Compose** - For running services
2. **base14 Scout Account** - For viewing traces
3. **Node.js 24+** (optional) - For local development

## Quick Start

### 1. Clone and Navigate

```bash
git clone https://github.com/base-14/examples.git
cd examples/nodejs/hono-postgres
```

### 2. Set base14 Scout Credentials

Create a `.env` file with your Scout credentials:

```bash
cat > .env << EOF
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

- Hono application on port 3000
- BullMQ worker for background jobs
- PostgreSQL on port 5433 (mapped from 5432)
- Redis on port 6379
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
- Triggers background jobs (article-created, article-favorited)
- Verifies Prometheus metrics are being collected
- Shows expected traces in Scout

### 6. View Traces

1. Log into your base14 Scout dashboard
2. Navigate to TraceX
3. Filter by service: `hono-postgres-app`
4. Look for the `article.create` trace to see propagation to worker

## API Endpoints

### Health & Metrics

| Method | Endpoint   | Description        | Auth |
| ------ | ---------- | ------------------ | ---- |
| `GET`  | `/health`  | Health check       | No   |
| `GET`  | `/metrics` | Prometheus metrics | No   |

### Authentication

| Method | Endpoint        | Description   | Auth |
| ------ | --------------- | ------------- | ---- |
| `POST` | `/api/register` | Register user | No   |
| `POST` | `/api/login`    | Login user    | No   |
| `GET`  | `/api/user`     | Get profile   | Yes  |
| `PUT`  | `/api/user`     | Update profile| Yes  |

### Articles

| Method   | Endpoint                       | Description        | Auth     |
| -------- | ------------------------------ | ------------------ | -------- |
| `GET`    | `/api/articles`                | List articles      | Optional |
| `POST`   | `/api/articles`                | Create article     | Yes      |
| `GET`    | `/api/articles/:slug`          | Get article        | Optional |
| `PUT`    | `/api/articles/:slug`          | Update (owner)     | Yes      |
| `DELETE` | `/api/articles/:slug`          | Delete (owner)     | Yes      |
| `POST`   | `/api/articles/:slug/favorite` | Favorite article   | Yes      |
| `DELETE` | `/api/articles/:slug/favorite` | Unfavorite article | Yes      |

## Configuration

### Required Environment Variables

| Variable              | Description                | Required |
| --------------------- | -------------------------- | -------- |
| `SCOUT_ENDPOINT`      | base14 Scout OTLP endpoint | Yes      |
| `SCOUT_CLIENT_ID`     | Scout OAuth2 client ID     | Yes      |
| `SCOUT_CLIENT_SECRET` | Scout OAuth2 client secret | Yes      |
| `SCOUT_TOKEN_URL`     | Scout OAuth2 token URL     | Yes      |

### Application Environment Variables

| Variable                     | Description            | Default                     |
| ---------------------------- | ---------------------- | --------------------------- |
| `NODE_ENV`                   | Environment            | `development`               |
| `PORT`                       | Application port       | `3000`                      |
| `DATABASE_URL`               | PostgreSQL connection  | (required)                  |
| `REDIS_URL`                  | Redis connection       | `redis://localhost:6379`    |
| `JWT_SECRET`                 | JWT signing secret     | (required)                  |
| `JWT_EXPIRES_IN`             | JWT token expiration   | `7d`                        |
| `OTEL_SERVICE_NAME`          | Service name in traces | `hono-postgres-app`         |
| `OTEL_EXPORTER_OTLP_ENDPOINT`| OTLP collector         | `http://localhost:4318`     |

## Telemetry Data

### Traces

**HTTP Spans** (automatic via `@hono/otel`):

- Span name: `GET /api/articles`, `POST /api/register`, etc.
- Attributes: `http.method`, `http.route`, `http.status_code`

**Database Spans** (automatic):

- Span name: `pg.query`
- Attributes: `db.system=postgresql`, `db.statement`

**Redis Spans** (automatic):

- Span name: `redis-GET`, `redis-SET`, etc.
- Attributes: `db.system=redis`

**Custom Business Spans**:

| Span Name                  | Description                    |
| -------------------------- | ------------------------------ |
| `user.register`            | User registration              |
| `user.login`               | User login                     |
| `article.create`           | Create article                 |
| `article.update`           | Update article                 |
| `article.delete`           | Delete article                 |
| `article.favorite`         | Favorite article               |
| `article.unfavorite`       | Unfavorite article             |
| `job.enqueue.*`            | Enqueue background job         |
| `job.article-created`      | Process article-created job    |
| `job.article-favorited`    | Process article-favorited job  |

**Custom Attributes**:

- `user.id` - User ID
- `user.email_domain` - Email domain (privacy-safe)
- `article.id` - Article ID
- `article.slug` - Article slug

### Metrics

Prometheus metrics available at `/metrics`:

- `http_requests_total` - HTTP request counter by method, route, status
- `http_request_duration_seconds` - Request duration histogram
- `process_*` - Node.js process metrics

### Logs

Pino structured logging with trace correlation:

```json
{
  "level": 30,
  "time": 1706371200000,
  "traceId": "abc123...",
  "spanId": "def456...",
  "msg": "Article created",
  "articleId": 1
}
```

## Development

### Local Build

```bash
npm install
npm run build
npm run start
```

### Testing

```bash
npm test                  # Unit tests (Vitest)
npm run test:watch        # Watch mode
npm run test:coverage     # Coverage report
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
docker compose logs -f worker

# Rebuild after code changes
docker compose up --build app worker
```

### Access Services

| Service        | URL                         | Purpose             |
| -------------- | --------------------------- | ------------------- |
| Hono API       | <http://localhost:3000>     | Main application    |
| Health Check   | <http://localhost:3000/health> | Service health   |
| Metrics        | <http://localhost:3000/metrics> | Prometheus metrics |
| PostgreSQL     | `localhost:5433`            | Database            |
| Redis          | `localhost:6379`            | Job queue backend   |
| OTel Collector | <http://localhost:4318>     | Telemetry ingestion |
| OTel Health    | <http://localhost:13133>    | Collector health    |

## OpenTelemetry Configuration

### Dependencies

```json
"@opentelemetry/api": "^1.9.0",
"@opentelemetry/sdk-node": "^0.212.0",
"@opentelemetry/auto-instrumentations-node": "^0.69.0",
"@opentelemetry/exporter-trace-otlp-http": "^0.212.0",
"@opentelemetry/exporter-metrics-otlp-http": "^0.212.0",
"@opentelemetry/exporter-logs-otlp-http": "^0.212.0",
"@opentelemetry/resources": "^2.5.1",
"@opentelemetry/semantic-conventions": "^1.39.0",
"@hono/otel": "^1.1.0"
```

### Implementation

Telemetry is initialized in `src/telemetry.ts` and must be imported before all other modules:

- NodeSDK with OTLP HTTP exporters for traces, metrics, and logs
- `@hono/otel` middleware for Hono-specific span enrichment
- Auto-instrumentations with health/metrics endpoint filtering; filesystem, net, DNS disabled
- Graceful shutdown on SIGTERM

## Troubleshooting

### No traces appearing in Scout

1. **Check collector logs**:

   ```bash
   docker compose logs otel-collector
   ```

2. **Verify Scout credentials** in `.env`

3. **Check collector health**:

   ```bash
   curl http://localhost:13133/health
   ```

### Background jobs not processing

1. **Check worker logs**:

   ```bash
   docker compose logs worker
   ```

2. **Check Redis connection**:

   ```bash
   docker exec hono-postgres-redis-1 redis-cli ping
   ```

### Database connection errors

1. **Check PostgreSQL health**:

   ```bash
   docker compose logs postgres
   ```

2. **Verify PostgreSQL is ready**:

   ```bash
   docker exec hono-postgres-postgres-1 pg_isready -U postgres
   ```

### Application won't start

1. **Check TypeScript compilation**:

   ```bash
   npm run build
   ```

2. **View application logs**:

   ```bash
   docker compose logs app
   ```

## Resources

- [OpenTelemetry JavaScript](https://opentelemetry.io/docs/languages/js/)
- [Hono Documentation](https://hono.dev/docs/)
- [Drizzle ORM Documentation](https://orm.drizzle.team/)
- [BullMQ Documentation](https://docs.bullmq.io/)
- [Pino Documentation](https://getpino.io/)
- [base14 Scout Documentation](https://docs.base14.io/)
