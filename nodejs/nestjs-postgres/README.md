# NestJS + PostgreSQL + OpenTelemetry

A production-ready example demonstrating NestJS REST API with TypeScript, PostgreSQL, and comprehensive OpenTelemetry instrumentation for end-to-end observability.

> [Full Documentation](https://docs.base14.io/instrument/apps/auto-instrumentation/nestjs)

## Stack Profile

| Component         | Version  | Status | Notes                             |
| ----------------- | -------- | ------ | --------------------------------- |
| **Node.js**       | 22.x LTS | Active | Active LTS                        |
| **TypeScript**    | 5.x      | Latest | Strict mode enabled               |
| **NestJS**        | 11.x     | Latest | Latest stable                     |
| **PostgreSQL**    | 16       | Active | Alpine variant                    |
| **TypeORM**       | 0.3.x    | Active | NestJS native integration         |
| **OpenTelemetry** | 0.208.0  | Latest | SDK Node + auto-instrumentation   |

**Why This Stack**: Demonstrates NestJS with TypeScript for enterprise-grade architecture, PostgreSQL for relational data, and OpenTelemetry for complete observability from HTTP requests through database operations.

## Architecture

Modular architecture with clear separation of concerns:

- **API Layer**: NestJS controllers with `/api/*` routes, CORS, Helmet security
- **Security**: Rate limiting, JWT authentication with Passport, bcrypt password hashing
- **Validation**: class-validator for DTO validation, Zod for configuration
- **Data**: PostgreSQL with TypeORM, auto-migrations in development
- **Observability**: OpenTelemetry automatic + custom instrumentation

**Graceful Shutdown**: Coordinated shutdown via NestJS lifecycle hooks.

## What's Instrumented

### Automatic Instrumentation

- HTTP requests and responses (NestJS/Express routes)
- PostgreSQL database queries
- Distributed trace propagation (W3C Trace Context)

### Custom Instrumentation

- **Traces**: Business operation spans for auth, CRUD, favorites
- **Attributes**: `user.id`, `user.email`, `article.id`, `article.title`, pagination
- **Metrics**: `auth.login.attempts`, `auth.login.success`, `auth.registration.total`, `articles.created`, `articles.favorited`
- **Logs**: Trace correlation ready

## Prerequisites

1. **Docker & Docker Compose** - For running services
2. **base14 Scout Account** - For viewing traces
3. **Node.js 22+** (optional) - For local development

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
JWT_SECRET=your-secret-key-change-in-production
JWT_EXPIRES_IN=7d
CORS_ORIGIN=*
OTEL_SERVICE_NAME=nestjs-postgres-app
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
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
- OpenTelemetry Collector on ports 4317/4318

### 4. Test the API

```bash
./scripts/test-api.sh
```

Expected output:

```text
Testing NestJS + PostgreSQL API
================================

Testing health endpoint... PASS
Testing register endpoint... PASS
Testing login endpoint... PASS
Testing me endpoint... PASS
Testing create article endpoint... PASS
Testing list articles endpoint... PASS
Testing get article endpoint... PASS
Testing update article endpoint... PASS
Testing favorite endpoint... PASS
Testing favorites count... PASS
Testing unfavorite endpoint... PASS
Testing delete article endpoint... PASS
Testing logout endpoint... PASS

All tests passed!
```

### 5. View Traces

1. Log into your base14 Scout dashboard
2. Navigate to TraceX
3. You should see traces for:
   - HTTP requests (`GET /api/articles`, `POST /api/auth/register`)
   - Custom business operations (`auth.register`, `auth.login`, `article.create`)
   - PostgreSQL queries (automatic instrumentation)

## API Endpoints

### Health

| Method | Endpoint      | Description  | Auth Required |
| ------ | ------------- | ------------ | ------------- |
| `GET`  | `/api/health` | Health check | No            |

### Authentication

| Method | Endpoint             | Description      | Auth Required |
| ------ | -------------------- | ---------------- | ------------- |
| `POST` | `/api/auth/register` | Register user    | No            |
| `POST` | `/api/auth/login`    | Login user       | No            |
| `GET`  | `/api/auth/me`       | Get current user | Yes           |
| `POST` | `/api/auth/logout`   | Logout user      | Yes           |

### Articles

| Method   | Endpoint           | Description                   | Auth Required |
| -------- | ------------------ | ----------------------------- | ------------- |
| `GET`    | `/api/articles`    | List all articles (paginated) | No            |
| `POST`   | `/api/articles`    | Create new article            | Yes           |
| `GET`    | `/api/articles/:id`| Get single article            | No            |
| `PUT`    | `/api/articles/:id`| Update article (owner only)   | Yes           |
| `DELETE` | `/api/articles/:id`| Delete article (owner only)   | Yes           |

### Favorites

| Method   | Endpoint                     | Description         | Auth Required |
| -------- | ---------------------------- | ------------------- | ------------- |
| `POST`   | `/api/articles/:id/favorite` | Favorite an article | Yes           |
| `DELETE` | `/api/articles/:id/favorite` | Unfavorite article  | Yes           |

## Configuration

### Required Environment Variables

| Variable              | Description                | Required |
| --------------------- | -------------------------- | -------- |
| `SCOUT_ENDPOINT`      | base14 Scout OTLP endpoint | Yes      |
| `SCOUT_CLIENT_ID`     | Scout OAuth2 client ID     | Yes      |
| `SCOUT_CLIENT_SECRET` | Scout OAuth2 client secret | Yes      |
| `SCOUT_TOKEN_URL`     | Scout OAuth2 token URL     | Yes      |

### Application Environment Variables

| Variable                      | Description                          | Default                           |
| ----------------------------- | ------------------------------------ | --------------------------------- |
| `NODE_ENV`                    | Environment (development/production) | `development`                     |
| `APP_PORT`                    | Application port                     | `3000`                            |
| `DATABASE_URL`                | PostgreSQL connection string         | (required)                        |
| `JWT_SECRET`                  | JWT signing secret                   | (required)                        |
| `JWT_EXPIRES_IN`              | JWT token expiration                 | `7d`                              |
| `OTEL_SERVICE_NAME`           | Service name in traces               | `nestjs-postgres-app`             |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP collector endpoint              | `http://otel-collector:4318`      |

## Telemetry Data

### Traces

**HTTP Spans** (automatic):
- Span name: `GET /api/articles`, `POST /api/auth/login`, etc.
- Attributes: `http.method`, `http.route`, `http.status_code`

**NestJS Spans** (automatic):
- Span name: `AuthController.register`, `ArticlesController.findAll`, etc.
- Attributes: `nestjs.controller`, `nestjs.callback`

**Database Spans** (automatic):
- Span name: `pg.query`, etc.
- Attributes: `db.system=postgresql`, `db.statement`

**Custom Business Spans**:
- `auth.register` - User registration
- `auth.login` - User login
- `auth.getProfile` - Get user profile
- `article.create` - Create article
- `article.findAll` - List articles
- `article.findOne` - Get single article
- `article.update` - Update article
- `article.delete` - Delete article
- `article.favorite` - Favorite article
- `article.unfavorite` - Unfavorite article

**Custom Attributes**:
- `user.id` - User UUID
- `user.email` - User email
- `article.id` - Article UUID
- `article.title` - Article title
- `pagination.page` - Current page
- `pagination.limit` - Page size

### Metrics

- `auth.login.attempts` - Login attempt counter
- `auth.login.success` - Successful login counter
- `auth.registration.total` - Registration counter
- `articles.created` - Article creation counter
- `articles.favorited` - Favorite counter

## Example Trace

A typical `POST /api/articles` trace includes:

```text
HTTP POST /api/articles                    [Auto-instrumented]
 └─ ArticlesController.create              [Auto-instrumented]
     └─ article.create                     [Custom span]
         └─ pg.query INSERT                [Auto-instrumented]
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

| Service               | URL                              | Purpose             |
| --------------------- | -------------------------------- | ------------------- |
| NestJS API            | http://localhost:3000            | Main application    |
| Health Check          | http://localhost:3000/api/health | Service health      |
| PostgreSQL            | localhost:5432                   | Database            |
| OTel Collector (gRPC) | http://localhost:4317            | Telemetry ingestion |
| OTel Collector (HTTP) | http://localhost:4318            | Telemetry ingestion |
| OTel Health Check     | http://localhost:13133           | Collector health    |

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

- [OpenTelemetry JavaScript Documentation](https://opentelemetry.io/docs/languages/js/)
- [NestJS Documentation](https://docs.nestjs.com/)
- [TypeORM Documentation](https://typeorm.io/)
- [base14 Scout Documentation](https://docs.base14.io/)

## License

MIT
