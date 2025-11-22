# Load Generator

Standalone load testing tool with OpenTelemetry instrumentation.

## Quick Start

```bash
# Start your target app first
cd ../rails/rails8-sqlite
docker-compose up -d

# Run load test with defaults
cd ../../loadgen
./run-loadtest.sh
```

## Configuration

```bash
# Custom settings
./run-loadtest.sh <target_url> <otel_endpoint> <rps> <duration>

# Example: 5 RPS for 2 minutes
./run-loadtest.sh http://host.docker.internal:3000 \
  http://host.docker.internal:4317 5 120

# Or just use defaults (recommended)
./run-loadtest.sh
```

**Note**: When running in Docker, use `host.docker.internal` instead of
`localhost` to access services on the host machine.

### Environment Variables

| Variable                      | Default          | Description        |
| ----------------------------- | ---------------- | ------------------ |
| `TARGET_URL`                  | `host....:3000`  | App to test        |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `host....:4317`  | Collector endpoint |
| `OTEL_SERVICE_NAME`           | `loadgen`        | Service name       |
| `REQUESTS_PER_SECOND`         | `2`              | Request rate       |
| `DURATION_SECONDS`            | `300`            | Test duration      |

Default URLs use `http://host.docker.internal` prefix.

### Docker Compose

```bash
export TARGET_URL=http://localhost:3000
export REQUESTS_PER_SECOND=10
docker-compose up --build
```

## Load Patterns

| Pattern | RPS | Duration | Use Case       |
| ------- | --- | -------- | -------------- |
| Light   | 1   | 180s     | Basic testing  |
| Normal  | 2   | 300s     | Sustained load |
| Peak    | 5   | 120s     | Traffic spikes |
| Stress  | 10  | 60s      | Breaking point |

## User Scenarios

Currently configured for hotel food ordering app:

- Browse hotels (30%)
- View hotel foods (25%)
- User signup/login (10%)
- Place orders (20%)
- View order history (15%)

**To adapt for your app:** Edit `loadgen.py` scenario methods to match
your endpoints.

## Metrics

- `loadgen_requests_total` - Total requests
- `loadgen_response_time_seconds` - Response time histogram
- `loadgen_errors_total` - Error count
