# Elysia + PostgreSQL + OpenTelemetry

Full-stack observability example using Elysia 1.4, Drizzle ORM, and the OTel Node SDK on Bun.

## Stack

| Component | Version |
| --- | --- |
| Bun | 1.3 |
| TypeScript | 6.0 |
| Elysia | 1.4 |
| Drizzle ORM | 0.45 |
| PostgreSQL | 18 |
| OTel Node SDK | 0.214.0 |
| OTel Collector | 0.148.0 |

## Architecture

```
┌─────────────────────────────────────────┐
│  Elysia Articles API (port 8080)        │
│  ┌─────────┐  ┌────────┐  ┌─────────┐  │
│  │ Elysia  │→ │Drizzle │→ │Postgres │  │
│  │ Routes  │  │  + pg   │  │ 18      │  │
│  └────┬────┘  └────────┘  └─────────┘  │
│       │ fetch() + traceparent           │
│       ▼                                 │
│  ┌─────────────────┐                    │
│  │  Notify Service  │ (port 8081)       │
│  └─────────────────┘                    │
└──────────────┬──────────────────────────┘
               │ OTLP HTTP (:4318)
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

## Observability

**Traces** — `@opentelemetry/sdk-node` preloaded via `bun run --preload`.
Route handlers wrapped with `startActiveSpan()` for full context propagation.
`@opentelemetry/instrumentation-pg` auto-instruments DB queries. Distributed
traces propagate to the notify service via manual `propagation.inject()` on
fetch headers.

**Logs** — `@opentelemetry/api-logs` exports structured logs to the collector
with LogRecord-level Trace ID/Span ID correlation. Stdout JSON mirror for local
dev. WARN-level logs for 400/404/422 errors.

**Metrics** — `articles.created` counter via OTel Meter API.

## Testing

```bash
# API + observability tests
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
