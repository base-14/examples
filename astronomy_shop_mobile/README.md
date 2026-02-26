# 🔭 Astronomy Shop Mobile

A production-ready Flutter e-commerce app with comprehensive OpenTelemetry
observability integration. Built to demonstrate mobile observability patterns
with real-world complexity.

## Features

### E-commerce Core

- Product Catalog - Real astronomy equipment from OpenTelemetry Demo backend
- Shopping Cart - Full cart management with backend synchronization
- Multi-Currency - 6 supported currencies (USD, EUR, CAD, GBP, JPY, INR)
- Checkout Flow - Complete purchase process with order confirmation
- Product Search - Search with intelligent fallbacks

### Observability & Performance

- OpenTelemetry Integration - Complete traces, metrics, and events
- Session Tracking - Unique session correlation across all requests
- HTTP Instrumentation - Every API call traced with rich context
- Business Metrics - Conversion funnel and user journey analytics
- Performance Monitoring - Real-time performance tracking
- Error Boundaries - Comprehensive error handling with telemetry

### Mobile Optimizations

- Battery-Aware Telemetry - Adapts behavior based on battery level
- Image Caching - Memory + disk caching with battery optimization
- Intelligent Batching - 50-event batches, 30s flush intervals
- Offline Support - Graceful fallbacks when APIs unavailable

### User Experience

- Material Design 3 - Modern, professional astronomy theme
- Smooth Animations - Hero transitions, loading states, micro-interactions
- Responsive Design - Optimized for mobile and web
- Accessibility - Screen reader support, proper contrast ratios

## Quick Start

### Prerequisites

1. OpenTelemetry Demo running locally:

```bash
git clone https://github.com/open-telemetry/opentelemetry-demo.git
cd opentelemetry-demo
docker compose -f docker-compose.minimal.yml up -d
```

1. Flutter SDK (latest stable version)

1. Chrome browser for web deployment

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

## Distributed Tracing

The app injects W3C Trace Context (`traceparent`, `tracestate`) headers on every
HTTP request to the backend, creating end-to-end distributed traces:

```
Flutter (CLIENT span) → Envoy → Frontend → Product Catalog / Cart / Checkout
```

All spans share the same trace ID. View them in your trace backend
(Jaeger, Base14 Scout, etc.) under service `astronomy-shop-mobile`.

### HTTP Span Attributes (semconv v1.40.0)

Spans follow OTel stable HTTP semantic conventions. Span name is just the
HTTP method (`GET`, `POST`).

| Attribute | Requirement | Emitted |
|-----------|-------------|---------|
| `http.request.method` | Required | Always |
| `url.full` | Required | Always |
| `server.address` | Required | Always |
| `server.port` | Required | Always |
| `http.response.status_code` | Cond. Required | On response |
| `error.type` | Cond. Required | On status >= 400 or network error |

### Key Telemetry Events

- `screen_view` - Navigation tracking
- `product_tap` - Product interactions
- `cart_add_item` - Shopping cart operations
- `checkout_initiated` - Purchase funnel
- `funnel_stage_transition` - Conversion funnel progression
- `currency_changed` - Internationalization

## Architecture

```plain
lib/
├── main.dart                        # App entry point with providers
├── models/                          # Data models (Product, CartItem, Checkout)
├── screens/                         # UI screens with telemetry integration
├── services/                        # Core services
│   ├── telemetry_service.dart       # OTel init, OTLP export, batching
│   ├── http_service.dart            # HTTP client with trace propagation
│   ├── cart_service.dart            # Cart state management
│   ├── products_api_service.dart    # Product catalog with caching
│   ├── currency_service.dart        # Multi-currency support
│   ├── funnel_tracking_service.dart # Conversion funnel analytics
│   └── performance_service.dart     # Performance monitoring
└── widgets/                         # Reusable UI components
```

## Configuration

### Environment Variables

Copy `.env.example` to `.env` and edit as needed:

- `OTLP_ENDPOINT` - OTLP HTTP collector (default: `http://localhost:8080/otlp-http` via Envoy, or `http://localhost:4318` for direct collector)
- `API_BASE_URL` - OTel Demo frontend-proxy API (default: `http://localhost:8080/api`)
- `SERVICE_NAME` - OTel service name (default: `astronomy-shop-mobile`)
- `SERVICE_VERSION` - App version (default: `0.0.1`)
- `ENVIRONMENT` - Deployment environment (default: `development`)

### Telemetry Settings

- Batch Size: 50 events
- Flush Interval: 30 seconds

### API Endpoints

- Products: `GET /api/products?currencyCode=USD`
- Cart: `POST /api/cart`
- Checkout: `POST /api/checkout`
- Currency: `GET /api/currency`
- Recommendations: `GET /api/recommendations`

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

## Security Notes

- All endpoints configured via environment variables
- Debug logs gated behind `kDebugMode`
- `.env` is gitignored, never commit credentials
- Run `flutter analyze` to check code quality
