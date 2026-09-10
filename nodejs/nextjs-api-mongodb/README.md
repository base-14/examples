# Next.js API with MongoDB

> [Full Documentation](https://docs.base14.io/instrument/apps/auto-instrumentation/nextjs/)

A production-ready REST API built with Next.js 16, MongoDB, and OpenTelemetry.

## How to instrument Next.js with OpenTelemetry

1. Install `@opentelemetry/sdk-node`, `@opentelemetry/auto-instrumentations-node`,
   `@opentelemetry/exporter-trace-otlp-http`, `@opentelemetry/exporter-metrics-otlp-http`,
   `@opentelemetry/exporter-prometheus`, `@opentelemetry/sdk-metrics`, `@opentelemetry/resources`,
   `@opentelemetry/semantic-conventions` and `@opentelemetry/api`.
2. Add `instrumentation.ts` at the project root with a `register()` hook that imports
   `src/lib/telemetry.ts` when `NEXT_RUNTIME === 'nodejs'`; that file builds a `NodeSDK` with
   `getNodeAutoInstrumentations()` and calls `sdk.start()`.
3. Set `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318` and
   `OTEL_SERVICE_NAME=nextjs-api-mongodb` in `.env`.

This example adds OTLP log export, a Prometheus metric reader next to the OTLP one, a `withSpan()`
helper for custom spans, and a separately instrumented BullMQ worker process. The full guide is
[Next.js OpenTelemetry Instrumentation](https://docs.base14.io/instrument/apps/auto-instrumentation/nextjs/).

## Stack

- **Framework**: Next.js 16.1.2 (Turbopack)
- **Runtime**: Node.js 22
- **Database**: MongoDB 8 with Mongoose 9
- **Cache/Queue**: Redis 7 with BullMQ
- **Validation**: Zod 4
- **Authentication**: JWT (jsonwebtoken)
- **Observability**: OpenTelemetry SDK 0.211.0

## Getting Started

### Prerequisites

- Node.js 22+
- MongoDB (replica set required for transactions)
- Redis (for background jobs)

### Installation

```bash
npm install
cp .env.example .env
# Edit .env with your configuration
```

### Development

```bash
npm run dev
```

### Production Build

```bash
npm run build
npm start
```

### Background Worker

```bash
npm run worker
```

## Docker Deployment

```bash
docker compose up -d
```

## API Endpoints

### Health

- `GET /api/health` - Health check

### Authentication

- `POST /api/auth/register` - Register a new user
- `POST /api/auth/login` - Login user

### User

- `GET /api/user` - Get current user profile (auth required)
- `PUT /api/user` - Update current user profile (auth required)

### Articles

- `GET /api/articles` - List articles (supports `?page=`, `?limit=`, `?tag=`, `?author=`)
- `POST /api/articles` - Create article (auth required)
- `GET /api/articles/:slug` - Get article by slug
- `PUT /api/articles/:slug` - Update article (auth required, owner only)
- `DELETE /api/articles/:slug` - Delete article (auth required, owner only)

### Favorites

- `POST /api/articles/:slug/favorite` - Favorite article (auth required)
- `DELETE /api/articles/:slug/favorite` - Unfavorite article (auth required)

### Jobs

- `GET /api/jobs` - Get background job queue statistics

## Testing

```bash
# Run API tests (requires running server)
npm run test:api

# Or specify a different base URL
./scripts/test-api.sh http://localhost:3000
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `NODE_ENV` | Environment | `development` |
| `PORT` | Server port | `3000` |
| `MONGODB_URI` | MongoDB connection string | - |
| `JWT_SECRET` | JWT signing secret (min 32 chars) | - |
| `JWT_EXPIRES_IN` | JWT expiration | `7d` |
| `REDIS_HOST` | Redis host | `localhost` |
| `REDIS_PORT` | Redis port | `6379` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OpenTelemetry collector | `http://localhost:4318` |
| `OTEL_SERVICE_NAME` | Service name for telemetry | `nextjs-api-mongodb` |

## Project Structure

```plain
├── src/
│   ├── app/
│   │   └── api/           # API routes
│   ├── lib/               # Shared utilities
│   │   ├── auth.ts        # JWT authentication
│   │   ├── config.ts      # Environment config
│   │   ├── db.ts          # MongoDB connection
│   │   ├── errors.ts      # Custom error classes
│   │   ├── queue.ts       # BullMQ setup
│   │   ├── telemetry.ts   # OpenTelemetry setup
│   │   └── validators.ts  # Zod schemas
│   ├── models/            # Mongoose models
│   ├── types/             # TypeScript types
│   └── jobs/              # Background workers
├── scripts/               # Utility scripts
├── instrumentation.ts     # Next.js instrumentation
└── compose.yaml            # Docker Compose
```
