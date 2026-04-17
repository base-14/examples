# Litestar + PostgreSQL — OpenTelemetry walkthrough

A two-service Python example that shows what end-to-end observability looks
like in practice. The point is not the CRUD app — it's *what you see in your
collector* when traffic flows through it.

## What this example demonstrates

| OpenTelemetry concept             | How it appears here                                                                 |
| --------------------------------- | ----------------------------------------------------------------------------------- |
| HTTP server spans                 | `litestar.contrib.opentelemetry` plugin (Litestar's custom router needs this)        |
| Database spans                    | `opentelemetry-instrumentation-asyncpg` patches asyncpg automatically                |
| Outbound HTTP / context propagation | `opentelemetry-instrumentation-httpx` puts `traceparent` on the wire                 |
| Distributed traces                | `litestar-postgres-app` → httpx → `litestar-postgres-notify` share one `trace_id`                |
| Custom metrics                    | `articles.created` counter via the OTel Meter API in `src/telemetry.py`              |
| Trace-correlated structured logs  | `python-json-logger` + `OTEL_PYTHON_LOG_CORRELATION=true` injects IDs on every record |
| Auto-init via wrapper             | `opentelemetry-instrument uvicorn …` in the Dockerfile CMD — no manual SDK setup     |

## Architecture

```
┌──────────────┐  POST /api/articles   ┌────────────────────┐
│              │ ────────────────────► │  litestar-postgres-app │
│   Client     │                       │   (port 8080)      │
│              │ ◄──── 201 ──────────  └────────────────────┘
└──────────────┘                                │
                                                │ asyncpg          httpx
                                                ▼                  ▼
                                       ┌────────────┐   ┌────────────────────┐
                                       │  Postgres  │   │  litestar-postgres-notify   │
                                       └────────────┘   │   (port 8081)      │
                                                        └────────────────────┘
                                                                │
   All four services emit OTLP → ┌────────────────────┐ ◄──────┘
                                 │  OTel Collector    │
                                 │   (4317/4318)      │
                                 └────────────────────┘
                                          │
                                          ▼
                                debug stdout  +  base14 Scout
```

## Tech stack

| Component                              | Version  |
| -------------------------------------- | -------- |
| Python                                 | 3.14     |
| Litestar                               | 2.21.1   |
| SQLAlchemy (async)                     | 2.0.49   |
| asyncpg                                | 0.31.0   |
| advanced-alchemy                       | 1.9.3    |
| Alembic                                | 1.18.4   |
| httpx                                  | 0.28.1   |
| python-json-logger                     | 4.1.0    |
| OpenTelemetry SDK / API / Exporter     | 1.41.0   |
| OpenTelemetry contrib (instrumentations) | 0.62b0  |
| OpenTelemetry Collector contrib        | 0.148.0  |
| Postgres                               | 18-alpine |
| uv (package manager)                   | 0.6.12   |

## Layout

```
litestar-postgres/
├── app/                  # litestar-postgres-app service
│   ├── src/
│   │   ├── main.py            # create_app() factory + module-level `app`
│   │   ├── config.py          # env-driven Settings
│   │   ├── models.py          # Article ORM + Base
│   │   ├── repository.py      # SQLAlchemyAsyncRepository[Article]
│   │   ├── telemetry.py       # OTel Meter + articles.created counter
│   │   ├── logging_config.py  # JSON formatter wired via Litestar LoggingConfig
│   │   ├── controllers/       # health.py, article.py
│   │   └── services/          # notification.py (httpx client)
│   ├── alembic/               # async migrations
│   ├── tests/                 # pytest (12 tests)
│   ├── pyproject.toml         # uv project
│   └── Dockerfile
├── notify/               # litestar-postgres-notify service
│   ├── src/{main.py,logging_config.py}
│   ├── tests/                 # pytest (2 tests)
│   ├── pyproject.toml
│   └── Dockerfile
├── config/otel-config.yaml    # collector pipeline (debug + Scout)
├── compose.yml                # 4 services
├── Makefile                   # sync/test/lint/format/audit/check + docker-* targets
└── scripts/
    ├── test-api.sh            # CRUD smoke against running stack
    └── verify-scout.sh        # end-to-end OTel pipeline verification
```

## Quickstart

```bash
cp .env.example .env
# edit .env to set DB_PASSWORD; SCOUT_* vars are optional

make docker-up                 # build + start all 4 services
./scripts/test-api.sh          # CRUD smoke
make docker-down
```

## Endpoints

`litestar-postgres-app` (`http://localhost:8080`)

| Method | Path                    | Notes                              |
| ------ | ----------------------- | ---------------------------------- |
| GET    | `/api/health`           | Liveness — filtered out of traces  |
| POST   | `/api/articles`         | Create; bumps `articles.created`; calls notify |
| GET    | `/api/articles`         | List; query `?limit=&offset=`      |
| GET    | `/api/articles/{id}`    | Read one; 404 if missing           |
| PUT    | `/api/articles/{id}`    | Replace title+body                 |
| DELETE | `/api/articles/{id}`    | 204 on success                     |

`litestar-postgres-notify` (`http://localhost:8081`)

| Method | Path        | Notes                                  |
| ------ | ----------- | -------------------------------------- |
| GET    | `/health`   | Liveness                               |
| POST   | `/notify`   | Receives `{article_id,title}` from articles |

## What you should see in the collector

Tail the collector to watch telemetry land:

```bash
docker compose logs -f otel-collector
```

After one `POST /api/articles` you should see:

1. **A single trace ID** appearing in spans from both `litestar-postgres-app` (Server, asyncpg INSERT/SELECT, httpx Client) and `litestar-postgres-notify` (Server). The notify service's parent span ID is the httpx Client span ID — that's distributed tracing working. asyncpg `BEGIN`/`COMMIT`/`ROLLBACK` transaction-lifecycle spans are dropped by the collector's `filter/noisy` processor — they add volume without insight.
2. **`articles.created` Sum metric** (cumulative monotonic) with a value matching how many articles you've POSTed since startup.
3. **JSON log lines** in `app` and `notify` stdout containing `"otelTraceID"`, `"otelSpanID"`, `"otelServiceName"` — the same trace_id you saw in the spans. This is what powers the "jump from span to logs" UI flow in Scout.

## Development workflow

```bash
make help            # list all targets
make sync            # uv sync both services
make test            # run pytest in both services (~0.4s total)
make lint            # ruff check + format check
make format          # ruff fix + format
make audit           # pip-audit each venv for known CVEs
make check           # lint + audit + test (run before commits)

make docker-build
make docker-up
make docker-logs
make docker-down

make test-api        # ./scripts/test-api.sh
make verify-scout    # ./scripts/verify-scout.sh — full OTel pipeline check
```

Tests run against an in-memory SQLite database (the SQLAlchemy models are
portable). Compose runtime uses Postgres. Migrations are applied on container
boot via the Dockerfile CMD.

## Trace-log correlation cheat sheet

The auto-instrumentation injects four attributes onto every Python `LogRecord`
when `OTEL_PYTHON_LOG_CORRELATION=true`:

```text
otelTraceID         otelSpanID         otelTraceSampled         otelServiceName
```

`logging_config.py` includes those in the JSON format string — that's the
entire wiring for "click a span, jump to its logs" in Scout.

## Custom metrics in 6 lines

```python
# src/telemetry.py
from opentelemetry import metrics
_meter = metrics.get_meter("litestar-postgres-app")
articles_created = _meter.create_counter(
    name="articles.created",
    description="Number of articles successfully created",
    unit="1",
)

# src/controllers/article.py
articles_created.add(1)
```

The `MeterProvider` is initialised by `opentelemetry-instrument` from `OTEL_*`
env vars — this module just *uses* it.

## Production gotchas (this is an example, not a template)

A few things that work in compose but you would change for a real deployment:

- **Migrations in `CMD`.** `alembic upgrade head` runs in the app container's CMD. Fine for one replica; at >1 replica you race. Run migrations as a Kubernetes Job (or equivalent) instead.
- **No retries / circuit breaker on the notify call.** A flapping notify service adds the full 5 s httpx timeout to every create. Add tenacity / a backoff library, or move to async messaging (SNS/Kafka) for genuinely fire-and-forget.
- **Update path is read-modify-write, not atomic.** Two concurrent `PUT /api/articles/{id}` requests can lose one write. For real concurrency, either `SELECT … FOR UPDATE` or use optimistic locking with a `version` column.
- **TLS verification disabled.** `tls.insecure_skip_verify: true` appears twice in `config/otel-config.yaml`. That is for local trust of the Scout endpoint during development — never ship it.
- **Aggressive flush intervals.** `OTEL_BSP_SCHEDULE_DELAY=2000` and `OTEL_METRIC_EXPORT_INTERVAL=10000` are tuned so `verify-scout.sh` finishes in under a minute. Production defaults (5 s / 60 s) reduce egress and cost.
- **Postgres port published to host.** `5432:5432` in compose is a development convenience. Drop it in production compose / k8s.
- **`expire_on_commit=False`.** Required for async SQLAlchemy so we can read `.id` after `auto_commit=True`. The trade-off: detached objects keep their last-loaded values; mutate-then-re-read across the same session needs an explicit `await session.refresh(obj)`.

## OTel env vars referenced by this project

| Variable                          | Set in           | Purpose                                       |
| --------------------------------- | ---------------- | --------------------------------------------- |
| `OTEL_SERVICE_NAME`               | `compose.yml`    | One per service                               |
| `OTEL_EXPORTER_OTLP_ENDPOINT`     | `compose.yml`    | Points to the collector                       |
| `OTEL_EXPORTER_OTLP_PROTOCOL`     | `compose.yml`    | `http/protobuf`                                |
| `OTEL_RESOURCE_ATTRIBUTES`        | `compose.yml`    | `deployment.environment`, `service.version`   |
| `OTEL_PYTHON_LOG_CORRELATION`     | `compose.yml`    | Inject trace IDs onto LogRecords              |
| `OTEL_METRIC_EXPORT_INTERVAL`     | `compose.yml`    | 10 s — fast feedback for dev                   |
| `OTEL_BSP_SCHEDULE_DELAY`         | `compose.yml`    | 2 s span batch flush                          |
| `SCOUT_*`                         | `.env`           | Read by collector for the `otlphttp/b14` exporter |
