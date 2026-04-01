# tRPC + PostgreSQL + OpenTelemetry

> [Full Documentation](https://docs.base14.io/instrument/apps/auto-instrumentation/trpc/)

Full-stack observability example using tRPC 11, Prisma 7, and the OTel Node SDK.

## Stack

| Component | Version |
| --- | --- |
| Node.js | 24 |
| TypeScript | 6.0 |
| tRPC | 11.16 |
| Prisma | 7.6 |
| Zod | 4.3 |
| PostgreSQL | 18 |
| OTel Node SDK | 0.214.0 |
| OTel Collector | 0.148.0 |

## Architecture

```
┌─────────────────────────────────────────┐
│  tRPC Articles API (port 8080)          │
│  ┌─────────┐  ┌────────┐  ┌─────────┐  │
│  │ tRPC    │→ │ Prisma │→ │ Postgres│  │
│  │ Router  │  │ 7.6    │  │ 18      │  │
│  └────┬────┘  └────────┘  └─────────┘  │
│       │ fetch()                         │
│       ▼                                 │
│  ┌─────────────────┐                    │
│  │  Notify Service  │ (port 8081)       │
│  └─────────────────┘                    │
└──────────────┬──────────────────────────┘
               │ OTLP gRPC (:4317)
               ▼
        ┌──────────────┐
        │ OTel Collector│ → Scout / Debug
        └──────────────┘
```

## Quick Start

```bash
docker compose up -d --build
# Wait for services to be healthy
curl http://localhost:8080/api/health
```

## API Endpoints

| Method | Path | Description |
| --- | --- | --- |
| GET | /api/health | Health check |
| GET | /api/articles | List articles (paginated) |
| GET | /api/articles/:id | Get article by ID |
| POST | /api/articles | Create article |
| PUT | /api/articles/:id | Update article |
| DELETE | /api/articles/:id | Delete article |

## tRPC + REST Bridge

This example demonstrates how tRPC procedures serve as the business logic layer
while REST endpoints provide the HTTP interface. The Node.js HTTP server maps
REST paths to tRPC `createCallerFactory` calls:

```
GET  /api/articles     → caller.article.list()
GET  /api/articles/:id → caller.article.getById()
POST /api/articles     → caller.article.create()
PUT  /api/articles/:id → caller.article.update()
DELETE /api/articles/:id → caller.article.delete()
```

## Observability

**Traces** — OTel Node SDK with auto-instrumentations covers HTTP server/client
and Prisma DB spans. Distributed traces propagate from app to notify service via
`fetch()`.

**Logs** — Pino structured JSON logs with `trace_id` and `span_id` injected via
OTel context. WARN-level logs for 400/404/422 errors.

**Metrics** — `articles.created` counter via OTel Meter API.

## Testing

```bash
# API + observability tests (15 checks)
bash scripts/test-api.sh

# Scout export verification (requires credentials)
bash scripts/verify-scout.sh
```

## Scout Configuration

Copy `.env.example` to `.env` and set your Scout credentials:

```bash
cp .env.example .env
# Edit .env with your credentials
```
