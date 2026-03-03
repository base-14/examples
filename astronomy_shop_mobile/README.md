# Astronomy Shop Mobile

A production-ready Flutter e-commerce app with comprehensive OpenTelemetry
observability integration. Built to demonstrate mobile observability patterns
with real-world complexity.

## Features

### E-commerce Core

- Product Catalog - Real astronomy equipment from OpenTelemetry Demo backend
- Shopping Cart - Full cart management with backend synchronization
- Multi-Currency - 6 supported currencies (USD, EUR, CAD, GBP, JPY, INR)
- Checkout Flow - Complete purchase process with order confirmation
- Product Search - API search with local fallback and result caching
- Recommendations - Cart-based and session-based product recommendations

### Observability

- Three OTLP Signals - Traces, metrics, and structured logs exported to any OTLP collector
- Crash Analytics - Crash vs error classification, crash-free session tracking, force-flush on fatal errors
- Structured Error Reporting - Stack traces, breadcrumb trails, screen context, and session duration on every error
- Session Tracking - Unique session correlation across all requests
- HTTP Instrumentation - Every API call traced with OTel semantic conventions, error logging, and request duration histograms
- Business Metrics - Conversion funnel and user journey analytics
- Error Boundaries - Widget-level error catching that chains to the global crash handler
- Breadcrumb Trail - Last 20 user actions recorded for crash context
- App Lifecycle - Telemetry flush on background, shutdown on detach, battery refresh on resume

### Mobile Optimizations

- Battery-Aware Telemetry - Adapts sampling rate based on battery level and low-power mode
- Image Caching - Memory (50 MB / 100 items) + disk caching with battery-aware downloads
- Intelligent Batching - 50-event batches, 30s flush intervals
- Offline Support - Graceful fallbacks when APIs unavailable

### User Experience

- Material Design 3 - Deep space blue theme with rounded cards and buttons
- Smooth Animations - Hero transitions, tap-scale effects, shimmer loading states
- Responsive Design - Optimized for mobile and web
- Accessibility - Standard Material widget semantics for screen readers

## Quick Start

### Prerequisites

1. OpenTelemetry Demo running locally:

```bash
git clone https://github.com/open-telemetry/opentelemetry-demo.git
cd opentelemetry-demo
docker compose -f docker-compose.minimal.yml up -d
```

2. Flutter SDK (latest stable version)

3. Chrome browser for web deployment

### Verify Demo Environment

Ensure these services are accessible:

- OpenTelemetry Demo: <http://localhost:8080>
- Demo API: <http://localhost:8080/api>
- OTLP Collector: port 4318 (scout-collector or otel-collector)

### Run the App

```bash
cd astronomy_shop_mobile
cp .env.example .env   # edit if needed
make run               # launches in Chrome at localhost:8090
```

The app will be available at: <http://localhost:8090>

### Make Targets

```
make run             Run in Chrome at localhost:8090 (web security disabled for local dev)
make analyze         Run static analysis (flutter analyze)
make test            Run all tests
make format          Format code (dart format)
make coverage        Generate test coverage report
make clean           Clean build artifacts and dependencies
make web             Run in Chrome (default flags)
make doctor          Check Flutter environment
make outdated        Check for outdated packages
```

Run `make help` for the full list.

## Architecture

```plain
lib/
├── main.dart                          # App entry, runZonedGuarded, service init
├── models/
│   ├── product.dart                   # Product data model with hardcoded fallbacks
│   ├── cart_item.dart                 # Cart item with quantity tracking
│   └── checkout.dart                  # Checkout request/response models
├── screens/
│   ├── cart_screen.dart               # Cart view with quantity controls
│   ├── checkout_screen.dart           # Checkout form and order placement
│   ├── order_confirmation_screen.dart # Post-purchase order summary
│   ├── product_detail_screen.dart     # Product detail with add-to-cart
│   ├── search_screen.dart             # Search with suggestions and results
│   └── performance_debug_screen.dart  # Debug-only telemetry dashboard
├── services/
│   ├── telemetry_service.dart         # OTel init, OTLP traces, device info, session
│   ├── metrics_service.dart           # OTLP metrics (counters, histograms, gauges)
│   ├── log_service.dart               # OTLP structured logs (5 severity levels)
│   ├── error_handler_service.dart     # Crash classification, breadcrumbs, force-flush
│   ├── http_service.dart              # HTTP client with trace propagation + metrics
│   ├── config_service.dart            # Environment variable validation
│   ├── app_lifecycle_observer.dart    # Lifecycle tracking (resume/pause/detach)
│   ├── cart_service.dart              # Cart state management (ChangeNotifier)
│   ├── products_api_service.dart      # Product catalog with caching
│   ├── currency_service.dart          # Multi-currency support (ChangeNotifier)
│   ├── search_service.dart            # Search with API + local fallback
│   ├── recommendations_service.dart   # Recommendations with cache + fallback
│   ├── image_cache_service.dart       # Two-tier image cache (memory + disk)
│   ├── funnel_tracking_service.dart   # Conversion funnel analytics
│   └── performance_service.dart       # Operation timing and frame metrics
└── widgets/
    ├── error_boundary.dart            # Error catching with handler chaining
    ├── currency_selector.dart         # Currency picker dialog
    ├── cached_image.dart              # Battery-aware cached image widget
    ├── enhanced_loading.dart          # Shimmer loading placeholders
    └── recommendations_section.dart   # Horizontal recommendation carousel
```

### Service Initialization Order

Services are initialized in `main()` in dependency order:

1. `ConfigService.validateConfiguration()` — validate `.env`
2. `TelemetryService.initialize()` — session, tracer, device info, auth
3. `MetricsService.initialize()` — start 60s flush timer
4. `LogService.initialize()` — start 30s flush timer
5. `FunnelTrackingService.initialize()` — bind to session ID
6. `ErrorHandlerService.initialize()` — install `FlutterError.onError` + `PlatformDispatcher.onError`
7. `CartService`, `CurrencyService`, `PerformanceService`, `ImageCacheService`

After initialization, `runZonedGuarded` wraps `runApp()` to catch unhandled
async exceptions that escape Flutter's error handler. These are classified as
crashes and trigger a force-flush of all pending telemetry.

### App Lifecycle

`AppLifecycleObserver` (registered as a `WidgetsBindingObserver`) handles:

- **resumed** — refresh battery status, record memory usage
- **paused** — flush all pending telemetry
- **detached** — full shutdown (session end metric, flush, close clients)

Each transition emits an `app_lifecycle_change` span.

## Observability

The app exports three OTLP signals to the configured collector. All exports
share the same resource attributes and session ID for correlation.

### Distributed Tracing

W3C Trace Context (`traceparent`, `tracestate`) headers are injected on every
HTTP request to the backend, creating end-to-end distributed traces:

```
Flutter (CLIENT span) → Envoy → Frontend → Product Catalog / Cart / Checkout
```

All spans share the same trace ID. View them in your trace backend
(Jaeger, Base14 Scout, etc.) under service `astronomy-shop-mobile`.

### HTTP Span Attributes (semconv v1.40.0)

Spans follow OTel stable HTTP semantic conventions. Span name is
`$method $path` (e.g. `GET /api/products`).

| Attribute | Requirement | Emitted |
|-----------|-------------|---------|
| `http.request.method` | Required | Always |
| `url.full` | Required | Always |
| `url.scheme` | Required | Always |
| `url.path` | Required | Always |
| `server.address` | Required | Always |
| `server.port` | Required | Always |
| `http.response.status_code` | Cond. Required | On response |
| `http.response.body.size` | Recommended | On response |
| `http.request.duration_ms` | Recommended | Always |
| `error.type` | Cond. Required | On status >= 400 or network error |

### Resource Attributes

Attached to every trace, metric, and log export:

| Attribute | Source |
|-----------|--------|
| `service.name` | `.env` SERVICE_NAME |
| `service.version` | `.env` SERVICE_VERSION |
| `deployment.environment` | `.env` ENVIRONMENT |
| `telemetry.sdk.name` | Hardcoded (`flutter-opentelemetry`) |
| `telemetry.sdk.version` | Hardcoded (`0.18.10`) |
| `session.id` | Generated UUID v4 per session |
| `os.name` | `dart:io` Platform |
| `os.version` | `dart:io` Platform |
| `device.locale` | `dart:io` Platform |
| `device.screen.width` | `dart:ui` PlatformDispatcher |
| `device.screen.height` | `dart:ui` PlatformDispatcher |
| `device.screen.density` | `dart:ui` PlatformDispatcher |

### Key Telemetry Events

- `screen_view` - Navigation tracking
- `product_tap` - Product interactions
- `cart_add_item` - Shopping cart operations
- `checkout_initiated` - Purchase funnel
- `funnel_stage_transition` - Conversion funnel progression
- `currency_changed` - Internationalization
- `error_occurred` - All errors with crash severity, breadcrumbs, and screen context

~80 event types total. See [docs/telemetry-signals.md](docs/telemetry-signals.md) for the full inventory.

### OTLP Metrics

- `http.client.request.duration` - Histogram of HTTP request latency (ms)
- `http.client.request.count` - Counter by method and status code
- `app.crash.count` - Counter by error type and screen
- `app.error.count` - Counter by error type and screen
- `app.session.count` - Counter with `crash_free` attribute

### Structured Logs

Errors and crashes are exported as OTLP log records with severity levels
(DEBUG=5, INFO=9, WARN=13, ERROR=17, FATAL=21). Fatal logs include stack
traces (truncated to 4000 chars) and trigger a force-flush of all pending
telemetry. HTTP 4xx responses are logged as WARN, 5xx as ERROR.

### Error Classification

| Error Source | Severity | Fatal | Trigger |
|-------------|----------|-------|---------|
| `FlutterError.onError` (non-silent) | crash | Yes | Unhandled framework error |
| `FlutterError.onError` (silent) | error | No | Known Flutter warning |
| `PlatformDispatcher.onError` | crash | Yes | Unhandled platform exception |
| `runZonedGuarded` catch | crash | Yes | Unhandled async exception |
| `recordCustomError()` | error | No | Handled exception |

Crashes trigger: `app.crash.count` metric increment, `FATAL` log with stack
trace, and `_forceFlushAll()` — parallel flush of traces, metrics, and logs
with a 3-second timeout.

### Breadcrumb Trail

Last 20 user actions are recorded for crash context. On any error, the
breadcrumb trail is included in both the `error_occurred` span and the
structured log record.

| Pattern | Source |
|---------|--------|
| `navigate:ProductList` | main.dart |
| `navigate:ProductDetail:{id}` | product_detail_screen.dart |
| `navigate:Cart` | cart_screen.dart |
| `navigate:Checkout` | checkout_screen.dart |
| `navigate:Search` | search_screen.dart |
| `cart:add:{id}` | cart_service.dart |
| `cart:remove:{id}` | cart_service.dart |
| `cart:clear` | cart_service.dart |
| `checkout:validate` | checkout_screen.dart |
| `checkout:placeOrder` | checkout_screen.dart |
| `search:{query}` | search_screen.dart |
| `currency:change:{code}` | currency_service.dart |

### Battery-Aware Sampling

| Battery State | Sampling Rate | Affected Signals |
|--------------|--------------|-----------------|
| Normal (>= 20%) | 100% | All events, DEBUG/INFO logs |
| Low (10–20%) | 50% | Events sampled, DEBUG/INFO logs sampled |
| Critical (< 10%) | 20% | Events sampled, DEBUG/INFO logs sampled |
| Low Power Mode | 30% | Events sampled, DEBUG/INFO logs sampled |

WARN, ERROR, and FATAL logs are always sent regardless of battery state.
Metrics always accumulate and flush on schedule.

## Configuration

### Environment Variables

Copy `.env.example` to `.env` and edit as needed:

- `OTLP_ENDPOINT` - OTLP HTTP collector (default: `http://localhost:8080/otlp-http` via Envoy, or `http://localhost:4318` for direct collector)
- `OTLP_TRACES_EXPORTER` - Traces path (default: `v1/traces`)
- `OTLP_METRICS_EXPORTER` - Metrics path (default: `v1/metrics`)
- `OTLP_LOGS_EXPORTER` - Logs path (default: `v1/logs`)
- `API_BASE_URL` - OTel Demo frontend-proxy API (default: `http://localhost:8080/api`)
- `SERVICE_NAME` - OTel service name (default: `astronomy-shop-mobile`)
- `SERVICE_VERSION` - App version (default: `0.0.1`)
- `ENVIRONMENT` - Deployment environment (default: `development`)

### Telemetry Settings

- Trace Batch: 50 events, 30s flush
- Metrics: 60s flush (counters, histograms, gauges)
- Logs: 100-record buffer, 30s flush (fatal triggers immediate flush)
- Breadcrumbs: Last 20 user actions retained for crash context

### API Endpoints

- Products: `GET /api/products?currencyCode=USD`
- Cart: `POST /api/cart`
- Checkout: `POST /api/checkout`
- Currency: `GET /api/currency`
- Recommendations: `GET /api/recommendations`
- Search: `POST /api/search/products`

## Telemetry Backend

### Option 1: OTel Demo Collector (development)

The OTel Demo ships with an otel-collector on port 4318. Route the Flutter app
through the Envoy frontend-proxy:

```
OTLP_ENDPOINT=http://localhost:8080/otlp-http
```

### Option 2: Base14 Scout (recommended)

Run a Scout collector alongside the OTel Demo to forward all telemetry to
Base14 Scout. The collector handles OAuth2 authentication so the Flutter app
sends plain OTLP.

> **Docs**: [OpenTelemetry Collector Setup](https://docs.base14.io/category/opentelemetry-collector-setup)

1. Add a Scout collector to your docker-compose:

```yaml
scout-collector:
  image: otel/opentelemetry-collector-contrib:0.130.0
  command: ["--config=/etc/otel-collector-config.yaml"]
  volumes:
    - ./otel-collector-config.yaml:/etc/otel-collector-config.yaml:ro
  ports:
    - "4318:4318"
  environment:
    - SCOUT_CLIENT_ID=${SCOUT_CLIENT_ID}
    - SCOUT_CLIENT_SECRET=${SCOUT_CLIENT_SECRET}
    - SCOUT_TOKEN_URL=${SCOUT_TOKEN_URL}
    - SCOUT_ENDPOINT=${SCOUT_ENDPOINT}
    - ENVIRONMENT=${ENVIRONMENT}
```

2. Configure Scout credentials in `.env`:

```bash
SCOUT_ENDPOINT=https://otel.play.base14.io/<your-org-id>/otlp
SCOUT_CLIENT_ID=your_client_id
SCOUT_CLIENT_SECRET=your_client_secret
SCOUT_TOKEN_URL=https://id.b14.dev/realms/<your-org-id>/protocol/openid-connect/token
```

3. Point the Flutter app at the Scout collector:

```
OTLP_ENDPOINT=http://localhost:4318
```

4. Route the OTel Demo's otel-collector to Scout as well by adding to
`otelcol-config-extras.yml`:

```yaml
exporters:
  otlphttp/scout:
    endpoint: http://scout-collector:4318
    tls:
      insecure: true

service:
  pipelines:
    traces:
      exporters: [debug, spanmetrics, otlphttp/scout]
    metrics:
      exporters: [debug, otlphttp/scout]
    logs:
      exporters: [debug, otlphttp/scout]
```

This gives you distributed traces across the Flutter app and all OTel Demo
backend services in a single Base14 Scout dashboard.

## CORS

The OTel Demo's Envoy frontend-proxy needs CORS configured to allow the Flutter
web app (port 8090) to call the API (port 8080) with `traceparent` headers.
Add `envoy.filters.http.cors` to `envoy.tmpl.yaml` allowing `http://localhost`
origins and `traceparent, tracestate, content-type` headers.

Note: `make run` launches Chrome with `--disable-web-security` for local
development. For production, configure CORS properly on the backend.

## Security Notes

- All endpoints configured via environment variables
- Debug logs and performance screen gated behind `kDebugMode`
- `.env` is gitignored, never commit credentials
- Stack traces truncated to 4000 chars in log exports
- Scout OIDC tokens auto-refresh 1 minute before expiry
- Run `make analyze` to check code quality
