# Angular Full-Stack OpenTelemetry

A runnable, end-to-end OpenTelemetry example for a modern Angular SPA, emitting all
three signals - **traces, metrics, and logs**. The browser SDK traces page loads,
user interactions, route changes, and `fetch` calls, then propagates W3C trace
context to an Express + Postgres API so a single trace spans the browser, the API,
and the database. It also records Core Web Vitals as metric histograms and errors
as ERROR logs; the backend adds HTTP + runtime metrics and trace-correlated pino
logs.

The frontend is **Angular 22 (zoneless)**. The instrumentation works the same on a
zone.js app; see [Zoneless vs zone.js](#zoneless-vs-zonejs) below.

> [Full Documentation](https://docs.base14.io/docs/instrument/apps/auto-instrumentation/angular)

## Stack Profile

| Component               | Version                              | Notes                                             |
| ----------------------- | ------------------------------------ | ------------------------------------------------- |
| **Angular**             | 22.0.4                               | Standalone, zoneless by default                   |
| **Node.js**             | 24 (Docker)                          | 24.15+ or 26+ to build/run outside Docker         |
| **Express**             | 5.2.1                                | Backend REST API                                  |
| **PostgreSQL**          | 18.2                                 | Alpine variant, seeded `items` table              |
| **pino**                | 10.x                                 | Backend JSON logger, auto-bridged to OTLP         |
| **web-vitals**          | 5.3.0                                | Core Web Vitals source                            |
| **OpenTelemetry (web)** | `sdk-trace-web` 2.8.0 / others 0.219 | Browser SDK: traces + metrics + logs              |
| **OpenTelemetry (Node)**| `sdk-node` 0.219.0                   | Backend SDK, auto-instrumentation                 |
| **Collector**           | contrib 0.153.0                      | OTLP in (CORS), Scout + debug out                 |

## Architecture

Four services wired together by Docker Compose:

- **frontend** - Angular 22 SPA, built to static assets and served by nginx on
  `:8080`. Runs the OpenTelemetry browser SDK.
- **backend** - Express 5 + Postgres API on `:3000`, auto-instrumented with the
  OpenTelemetry Node SDK.
- **otel-collector** - `opentelemetry-collector-contrib`. Receives OTLP over HTTP
  from both the browser (CORS-enabled) and the backend, exports to base14 Scout and
  a local debug log.
- **postgres** - Postgres 18, seeded with an `items` table.

The browser runs on the host, so it reaches the collector (`:4318`) and the API
(`:3000`) through their published host ports. Its origin is `http://localhost:8080`,
which both the collector OTLP receiver and the backend allow via CORS.

## What's Instrumented

### Automatic Instrumentation

- **Browser** (`auto-instrumentations-web`): document load, resource fetch,
  user-interaction clicks, and `fetch`/XHR calls with W3C trace propagation.
- **Backend** (`auto-instrumentations-node`): HTTP server requests, `pg` database
  queries, runtime-node metrics, and pino log bridging.
- Distributed trace propagation browser -> API -> Postgres (W3C Trace Context).

### Custom Instrumentation

- **Traces**: manual `items.load` / `items.load.missing` spans around the HttpClient
  call; a `router.navigation` span per client-side route change.
- **Metrics**: Core Web Vitals as `web_vitals.{lcp,inp,cls,fcp,ttfb}` histograms with
  per-instrument bucket Views (CLS is a ~0-1 score, the rest are milliseconds).
- **Logs**: browser ERROR logs on two paths - an HttpClient error interceptor
  (trace-correlated) and the Angular `ErrorHandler` (best-effort).
- **Attributes**: `web_vital.rating`, `page.path`, `http.response.status_code`,
  `exception.*`.

### Trace Propagation Demo

A single "Load items" click produces one trace:

```text
click (angular-browser)
└─ items.load                                  (manual span around the HttpClient call)
   └─ HTTP GET http://localhost:3000/api/items (browser fetch instrumentation)
      └─ GET /api/items                         (angular-items-api, Express)
         └─ pg.query:SELECT items              (Postgres)
```

## Prerequisites

1. **Docker & Docker Compose** - to run the services.
2. **base14 Scout account** (optional) - to view telemetry in Scout. Without it,
   everything still flows to the collector's local debug exporter.
3. **Node.js 24.15+ or 26+** (optional) - only to build or run the apps outside
   Docker (Angular 22 engines).
4. **Chrome or Chromium + Node.js** (optional) - only for the automated headless
   browser drive in `scripts/verify-scout.sh`.

## Quick Start

### 1. Clone and Navigate

```bash
git clone https://github.com/base-14/examples.git
cd examples/nodejs/angular-fullstack-otel
```

### 2. Set base14 Scout Credentials (optional)

Telemetry always flows to the collector's local debug exporter. To also export to
base14 Scout, create a `.env` file next to `compose.yaml`:

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

- frontend (Angular SPA, nginx) on <http://localhost:8080>
- backend (Express + Postgres API) on <http://localhost:3000>
- otel-collector on ports 4317 (gRPC) and 4318 (HTTP)
- postgres on `5433 -> 5432`

### 4. Test in the Browser

Open <http://localhost:8080/items> and:

1. Click **Load items** - fetches `/api/items` and renders the rows. This is the
   distributed trace browser -> Express -> Postgres.
2. Click **Trigger API error** - a failing request fired inside an active span; the
   HttpClient error interceptor emits a **trace-correlated** ERROR log.
3. Click **Trigger error** - an uncaught throw routed through the Angular
   `ErrorHandler`, emitted as a **best-effort** ERROR log (usually uncorrelated in a
   zoneless app - see [Zoneless vs zone.js](#zoneless-vs-zonejs)).
4. Use the **Items** / **About** nav links - each route change emits a
   `router.navigation` span.
5. Switch tabs or refresh - Core Web Vitals report on page hide, and the SDK
   force-flushes all three signals.

> API-only check (no browser): `curl http://localhost:3000/api/items` exercises the
> backend trace + `http.server.request.duration` metric + a `served items` pino log.

> Automate the whole flow: `./scripts/verify-scout.sh` runs the collector + backend
> checks and drives a headless browser through the same clicks (needs Chrome and
> Node). It prints a pass/fail summary and what to look for in Scout.

### 5. View the Telemetry

Watch the collector's debug exporter:

```bash
docker compose logs -f otel-collector
```

You should see the signals listed under [What's Instrumented](#whats-instrumented):
the browser `HTTP GET`, the Express `GET /api/items`, and `pg.query:SELECT items`
sharing one trace id; `web_vitals.*` and `http.server.request.duration` metrics; and
trace-correlated pino and browser ERROR logs.

### 6. Verify Scout Integration

Generate all three signals from both the backend and a headless browser in one
shot:

```bash
./scripts/verify-scout.sh
```

Then, in Scout:

1. Log into your base14 Scout dashboard.
2. Filter by service: `angular-browser` (browser) or `angular-items-api` (API).
3. Open a "Load items" trace to see browser -> Express -> Postgres propagation.
4. Check **Metrics** for `web_vitals.*` and `http.server.request.duration`, and
   **Logs** for the trace-correlated browser error log.

## Zoneless vs zone.js

Angular 22 ships zoneless by default, so this example registers the OpenTelemetry
`WebTracerProvider` with the default `StackContextManager` (`provider.register()`).
The browser -> API -> database trace links through the injected `traceparent`
header, which does not depend on the context manager, so it is identical on a
zone.js app. The only difference is in-browser parenting of an interaction's async
work; on a zone.js app you can opt into `ZoneContextManager`.

The same context boundary is why an uncaught error reaching the `ErrorHandler` is
usually uncorrelated - the interaction's span has already unwound by the time the
error lands. The HttpClient error interceptor (`error-interceptor.ts`) sidesteps
this by capturing the active context synchronously on the request path and
re-entering it when it emits, so failed-request logs reliably carry the trace id.
See the
[Angular instrumentation guide](https://docs.base14.io/docs/instrument/apps/auto-instrumentation/angular)
for the zone-based variant.

## Project Layout

```text
angular-fullstack-otel/
├── compose.yaml
├── config/otel-config.yaml          # collector: OTLP-in (CORS), Scout + debug out
├── scripts/
│   ├── verify-scout.sh              # health + backend traffic + headless browser drive
│   └── drive-browser.mjs            # CDP driver for the browser leg
├── backend/                         # Express 5 + Postgres, Node OTel SDK
│   ├── src/instrumentation.ts       # NodeSDK: traces + metrics + logs
│   ├── src/server.ts                # API + pino logging
│   └── schema.sql
└── frontend/                        # Angular 22 SPA
    ├── src/app/telemetry/
    │   ├── browser-telemetry.ts     # bootstrap: tracer + meter + logger providers
    │   ├── router-tracing.ts        # NavigationEnd -> span
    │   ├── error-handler.ts         # ErrorHandler -> best-effort ERROR log
    │   ├── error-interceptor.ts     # HttpClient failure -> correlated ERROR log
    │   └── web-vitals.ts            # Core Web Vitals -> metric histograms
    ├── Dockerfile
    └── nginx.conf
```

## Validation log

### 2026-06-30 - initial validation

- `docker compose up --build`, opened <http://localhost:8080/items>, driven with
  headless Chrome. "Load items" produced one trace: browser `HTTP GET`
  (angular-browser) -> `GET /api/items` (angular-items-api) -> `pg.query:SELECT items`.
- Navigation emitted `router.navigation` spans; page load emitted Web Vitals;
  "Trigger error" routed through the Angular `ErrorHandler`.
- Versions: Angular 22.0.4; OTel web `sdk-trace-web` 2.8.0 /
  `auto-instrumentations-web` 0.64.0 / `exporter-trace-otlp-http` 0.219.0;
  `web-vitals` 5.3.0; Node `sdk-node` 0.219.0 / `auto-instrumentations-node` 0.77.0;
  Express 5.2.1; pg 8.22.0; collector-contrib 0.153.0; Postgres 18.2.

### 2026-06-30 - post-review fixes

- Unified the environment label: frontend now emits `development` (was `production`),
  matching the backend `DEPLOY_ENV` and collector `SCOUT_ENVIRONMENT`, so one trace
  carries one environment. Collector `resource` processor now only `insert`s
  `environment` (non-clobbering backfill).
- Added a force-flush on page hide so Web Vitals and last-moment error records
  survive the tab closing.

### 2026-07-06 - three-signal extension (traces + metrics + logs)

- Extended traces-only to all three signals. Browser SDK bootstraps a `MeterProvider`
  and `LoggerProvider` (explicit `setGlobalMeterProvider`/`setGlobalLoggerProvider` -
  no `register()` sugar; without the global set every data point is a silent Noop).
  Backend `NodeSDK` gained `metricReaders` + `logRecordProcessors`; `console.*` ->
  pino; collector gained `metrics` and `logs` pipelines.
- Web Vitals moved from spans to `web_vitals.*` histograms with per-instrument bucket
  Views. Errors moved to ERROR logs on two paths (correlated HttpClient interceptor +
  best-effort `ErrorHandler`); added a "Trigger API error" button. Set
  `OTEL_SEMCONV_STABILITY_OPT_IN=http` for the stable `http.server.request.duration`.
- Validated end-to-end (headless-Chrome drive, freshly recreated collector): traces
  regression intact and unified browser -> API -> `pg.query`; browser `web_vitals.*`
  + backend `http.server.request.duration` + runtime-node metrics; correlated
  interceptor ERROR log (non-zero trace id) and best-effort `ErrorHandler` log (no
  trace id, as designed). INP needs a real interaction, not the synthetic drive.
  Frontend bundle 389 kB raw / 101 kB transfer.
