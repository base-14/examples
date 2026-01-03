# Go Parking Lot + OpenTelemetry

Go-based parking lot management system with OpenTelemetry instrumentation.
Features both CLI and HTTP REST API interfaces with custom metrics and
distributed tracing via base14 Scout.

> 📚 [Full Documentation](https://docs.base14.io/instrument/apps/custom-instrumentation/go)

## What's Instrumented

This example demonstrates comprehensive OpenTelemetry instrumentation in Go:

### Automatic Instrumentation

- HTTP requests (method, path, status code, duration)
- Request/response tracing with span context propagation
- Metrics endpoint at `/metrics` (Prometheus format)
- Graceful shutdown handling

### Custom Instrumentation

- **Traces**: All parking operations (park, leave, status, find)
- **Metrics**: Operation counters, duration histograms, occupancy gauges
- **Attributes**: Vehicle details, slot numbers, operation status
- **Events**: Operation lifecycle events (slot_allocated, vehicle_found)

**Observability**: All telemetry (traces and metrics) is exported to
base14 Scout via OTLP for full-stack observability.

**Storage**: In-memory implementation - data is not persisted between restarts.

Service name: `go-parking-lot-otel` (configurable)

## Stack

- **Language**: Go 1.25
- **HTTP Router**: go-chi/chi v5
- **Storage**: In-memory (no database)
- **OTel Collector**: opentelemetry-collector-contrib 0.115.1
- **Observability**: base14 Scout (traces + metrics via OTLP)
- **Container**: Docker + Docker Compose

## Dependencies

| Package | Purpose |
| ------- | ------- |
| go.opentelemetry.io/otel | Core OpenTelemetry SDK |
| go.opentelemetry.io/otel/exporters/otlp/otlptracehttp | OTLP trace exporter |
| go.opentelemetry.io/otel/exporters/otlp/otlpmetrichttp | OTLP metric exporter |
| github.com/go-chi/chi/v5 | HTTP router and middleware |
| github.com/prometheus/client_golang | Metrics exposition format |

## Prerequisites

1. **Docker & Docker Compose** - [Install Docker](https://docs.docker.com/get-docker/)
2. **base14 Scout Account** - [Sign up](https://base14.io)
3. **Go 1.25+** (for local development)

## Quick Start

```bash
# Clone and navigate
git clone https://github.com/base-14/examples.git
cd examples/go/chi-inmemory
```

### 1. Configure Scout Credentials

Copy the example environment file and add your Scout credentials:

```bash
cp .env.example .env
```

Edit `.env` and set:

```bash
SCOUT_ENDPOINT=https://your-tenant.base14.io:4318
SCOUT_CLIENT_ID=your_client_id
SCOUT_CLIENT_SECRET=your_client_secret
SCOUT_TOKEN_URL=https://your-tenant.base14.io/oauth/token
```

### 2. Start Services

```bash
docker compose up --build
```

This starts:

- **app**: Go HTTP server on port 8080
- **otel-collector**: OTel collector with Scout export

### 3. Test the API

```bash
./scripts/test-api.sh
```

The test script exercises all API endpoints and verifies telemetry.

### 4. View Traces

Navigate to your Scout dashboard to view traces and metrics:

```text
https://your-tenant.base14.io
```

## Configuration

### Environment Variables

| Variable | Description | Default |
| -------- | ----------- | ------- |
| `APP_ENV` | Application environment | `development` |
| `APP_PORT` | HTTP server port | `8080` |
| `OTEL_SERVICE_NAME` | Service name | `go-parking-lot-otel` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP endpoint | `http://otel-collector:4318` |
| `OTEL_RESOURCE_ATTRIBUTES` | Resource attrs | `deployment.environment=dev` |
| `SCOUT_ENDPOINT` | Scout OTLP endpoint | Required |
| `SCOUT_CLIENT_ID` | Scout OAuth client ID | Required |
| `SCOUT_CLIENT_SECRET` | Scout OAuth secret | Required |
| `SCOUT_TOKEN_URL` | Scout OAuth token URL | Required |

## API Endpoints

### Health & Metrics

```bash
GET /health          # Health check
GET /metrics         # Prometheus metrics
```

### Parking Operations

```bash
POST /api/parking-lot
Content-Type: application/json
{"capacity": 6}

POST /api/parking-lot/park
Content-Type: application/json
{"registration": "KA-01-HH-1234", "color": "White"}

POST /api/parking-lot/leave
Content-Type: application/json
{"slot_number": 2}

GET /api/parking-lot/status

GET /api/parking-lot/find/:registration
```

### Example Requests

```bash
# Create parking lot
curl -X POST http://localhost:8080/api/parking-lot \
  -H "Content-Type: application/json" \
  -d '{"capacity": 6}'

# Park vehicle
curl -X POST http://localhost:8080/api/parking-lot/park \
  -H "Content-Type: application/json" \
  -d '{"registration": "KA-01-HH-1234", "color": "White"}'

# Get status
curl http://localhost:8080/api/parking-lot/status

# Find vehicle
curl http://localhost:8080/api/parking-lot/find/KA-01-HH-1234

# Leave slot
curl -X POST http://localhost:8080/api/parking-lot/leave \
  -H "Content-Type: application/json" \
  -d '{"slot_number": 1}'
```

## OpenTelemetry Setup

### Telemetry Provider Initialization

```go
package parking

import (
    "go.opentelemetry.io/otel"
    "go.opentelemetry.io/otel/exporters/otlp/otlptracehttp"
    sdktrace "go.opentelemetry.io/otel/sdk/trace"
)

func NewTelemetryProvider() (*TelemetryProvider, error) {
    // Create OTLP trace exporter
    traceExporter, err := otlptracehttp.New(ctx,
        otlptracehttp.WithEndpointURL(otlpEndpoint+"/v1/traces"),
        otlptracehttp.WithInsecure(),
    )

    // Create tracer provider
    tracerProvider := sdktrace.NewTracerProvider(
        sdktrace.WithBatcher(traceExporter),
        sdktrace.WithResource(resource),
        sdktrace.WithSampler(sdktrace.AlwaysSample()),
    )

    otel.SetTracerProvider(tracerProvider)
    return &TelemetryProvider{tracerProvider: tracerProvider}
}
```

### Custom Spans

```go
func (ipl *InstrumentedParkingLot) Park(
    ctx context.Context, registration, color string) (int, error) {
    tracer := ipl.telemetry.Tracer()
    ctx, span := tracer.Start(ctx, "parking_lot.park",
        trace.WithAttributes(
            attribute.String("vehicle.registration_number", registration),
            attribute.String("vehicle.color", color),
        ))
    defer span.End()

    slotNumber, err := ipl.ParkingLot.Park(registration, color)

    if err != nil {
        span.RecordError(err)
        span.SetStatus(codes.Error, err.Error())
    } else {
        span.SetAttributes(attribute.Int("allocated_slot_number", slotNumber))
        span.AddEvent("slot_allocated")
    }

    return slotNumber, err
}
```

### Custom Metrics

```go
// Counter for parking operations
parkingOperations, _ := meter.Int64Counter("parking_operations_total",
    metric.WithDescription("Total number of parking operations"),
    metric.WithUnit("1"))

// Gauge for occupancy
occupancyGauge, _ := meter.Int64UpDownCounter("parking_lot_occupancy",
    metric.WithDescription("Current number of occupied parking slots"))

// Histogram for operation duration
operationDuration, _ := meter.Float64Histogram("operation_duration_seconds",
    metric.WithDescription("Duration of parking lot operations"),
    metric.WithUnit("s"))

// Record metrics
parkingOperations.Add(ctx, 1, metric.WithAttributes(
    attribute.String("operation", "park"),
    attribute.String("status", "success"),
))
occupancyGauge.Add(ctx, 1)
operationDuration.Record(ctx, duration)
```

## CLI Usage

The application supports three modes:

### CLI Mode (Default)

Interactive command-line interface:

```bash
# Using Docker
docker run -it parking-lot --mode=cli

# Using Make
make run-cli

# Using binary
./parking-lot --mode=cli
```

**Commands:**

- `create_parking_lot <capacity>` - Create parking lot
- `park <registration> <color>` - Park vehicle
- `leave <slot_number>` - Leave slot
- `status` - Show parking status
- `slot_number_for_registration_number <registration>` - Find vehicle
- `exit` - Exit program

### Server Mode

HTTP REST API server:

```bash
# Using Docker Compose
docker compose up

# Using Make
make run-server

# Using binary
./parking-lot --mode=server --port=8080
```

### Both Mode

Run CLI and HTTP server concurrently:

```bash
./parking-lot --mode=both --port=8080
```

## Development

### Local Build

```bash
# Build binary
make build

# Run tests
make test

# Run linter
make lint

# Format code
make format

# Build + lint + test
make build-lint
```

### Docker Commands

```bash
# Build and start
docker compose up --build

# Start in background
docker compose up -d

# View logs
docker compose logs -f app
docker compose logs -f otel-collector

# Stop services
docker compose down

# Rebuild
docker compose build
```

### Access Services

```bash
# Application shell
docker exec -it go-parking-lot sh

# OTel collector zpages
open http://localhost:55679/debug/servicez
```

## Telemetry Data

### Traces

View in Scout dashboard:

- Operation spans (park, leave, status, find)
- HTTP request spans with method, path, status
- Nested spans showing operation flow
- Error traces with stack information

### Metrics

Available via Prometheus format at `/metrics`:

```prometheus
# Operation counters
parking_operations_total{operation="park",status="success"} 5
leaving_operations_total{operation="leave",status="success"} 2

# Occupancy gauge
parking_lot_occupancy 3
parking_lot_total_slots 6

# Duration histogram
operation_duration_seconds_bucket{operation="park",le="0.1"} 5
```

## Troubleshooting

### No traces appearing in Scout

1. Check OTel collector logs:

   ```bash
   docker compose logs otel-collector
   ```

2. Verify Scout credentials in `.env`

3. Test collector health:

   ```bash
   curl http://localhost:55679/debug/servicez
   ```

### HTTP server not starting

1. Check if port 8080 is available:

   ```bash
   lsof -i :8080
   ```

2. View application logs:

   ```bash
   docker compose logs app
   ```

3. Verify environment variables:

   ```bash
   docker exec go-parking-lot env | grep OTEL
   ```

### Build errors

1. Clear Go cache:

   ```bash
   go clean -cache -modcache
   ```

2. Re-download dependencies:

   ```bash
   go mod download
   go mod tidy
   ```

## Resources

- [OpenTelemetry Go Documentation](https://opentelemetry.io/docs/languages/go/)
- [Base14 Documentation](https://docs.base14.io)
- [OpenTelemetry Specification](https://opentelemetry.io/docs/specs/otel/)
- [Go OpenTelemetry SDK](https://pkg.go.dev/go.opentelemetry.io/otel)
- [OTLP Protocol](https://opentelemetry.io/docs/specs/otlp/)

## License

This example is open-source software provided for educational purposes.
