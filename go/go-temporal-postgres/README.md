# Go Temporal + PostgreSQL + OpenTelemetry Example

A comprehensive Go example demonstrating business-level decision making with Temporal workflows and full OpenTelemetry instrumentation. This example showcases Base14 Scout's value for workflow observability - enabling teams to trace business decisions, identify bottlenecks, and perform root cause analysis on order processing failures.

> [Full Documentation](https://docs.base14.io/instrument/apps/auto-instrumentation/go)

> **Note:** This is a demonstration application optimized for learning and telemetry exploration. See [Production Considerations](#production-considerations) for guidance on hardening for real-world use.

## Business Use Case: Order Fulfillment Decision Engine

This example implements an order fulfillment workflow with:

- **Fraud Detection** - Risk scoring based on customer tier, order amount, and history
- **Inventory Management** - Real-time stock checking with backorder handling
- **Payment Processing** - Mock payment with success/failure scenarios
- **Shipping Reservation** - Carrier selection and tracking
- **Notifications** - Order confirmation delivery

## Architecture

Microservices architecture with each domain running as an independent Temporal worker:

```text
┌─────────┐     ┌──────────────┐     ┌─────────────────────┐
│   API   │────▶│  Temporal    │────▶│  Order Workflow     │
└─────────┘     │  Server      │     │  (orchestration)    │
                └──────────────┘     └──────────┬──────────┘
                                                │
        ┌───────────────┬───────────────┬───────┴───────┬───────────────┐
        ▼               ▼               ▼               ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ fraud-worker │ │  inventory-  │ │   payment-   │ │  shipping-   │ │ notification │
│              │ │   worker     │ │   worker     │ │   worker     │ │   -worker    │
└──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘
```

📊 **[Business Overview](docs/business-overview.md)** - Simplified view for business stakeholders
🔧 **[Technical Architecture](docs/architecture.md)** - Detailed system diagrams and telemetry flow

## Decision Paths

| Path | Trigger | Outcome |
|------|---------|---------|
| Auto-Approve | Risk score ≤ 80, stock available, payment success | Order completed |
| Manual Review | Risk score > 80 | Awaits human signal |
| Backorder | Insufficient stock | Order placed on hold |
| Payment Failed | Payment declined | Order cancelled |

## Quick Start

### Prerequisites

- Go 1.23+
- Docker and Docker Compose

### Run with Docker Compose

```bash
# Start all services
docker compose up -d

# View logs
docker compose logs -f

# Stop services
docker compose down
```

### Local Development

```bash
# Install dependencies
go mod download

# Run API server
make run-api

# Run Temporal worker (in another terminal)
make run-worker
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/health | Health check |
| GET | /api/products | List products |
| GET | /api/products/:id | Get product |
| GET | /api/orders | List orders |
| GET | /api/orders/:id | Get order |
| POST | /api/orders | Create order (starts workflow) |

### Create Order Example

```bash
# Auto-approve path (premium customer, low amount)
curl -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "premium-customer",
    "customer_tier": "premium",
    "items": [{"product_id": "prod-1", "quantity": 1, "price": 50}]
  }'

# Manual review path (new customer, high amount)
curl -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "new-customer",
    "customer_tier": "new",
    "items": [{"product_id": "prod-1", "quantity": 100, "price": 5000}]
  }'

# Backorder path (out of stock item)
curl -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "test-customer",
    "items": [{"product_id": "out-of-stock-item", "quantity": 1000}]
  }'

# Payment failure path
curl -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{
    "customer_id": "test-customer",
    "items": [{"product_id": "prod-1", "quantity": 1}],
    "payment_method": "test_decline"
  }'
```

## Load Generator

Generate realistic order traffic for testing and demos:

```bash
# Run 50 orders at 2 requests/second
docker compose run --rm loadgen --count 50 --rps 2

# Run for 60 seconds at 5 requests/second
docker compose run --rm loadgen --duration 60s --rps 5

# High throughput with more workers
docker compose run --rm loadgen --count 100 --rps 10 --workers 10
```

## Simulation Configuration

Each worker supports configurable failure rates and latency for realistic testing:

| Worker | Env Vars | Defaults |
|--------|----------|----------|
| fraud-worker | `FRAUD_FAILURE_RATE`, `FRAUD_LATENCY_MIN_MS`, `FRAUD_LATENCY_MAX_MS` | 1%, 10-100ms |
| inventory-worker | `INVENTORY_FAILURE_RATE`, `INVENTORY_OUT_OF_STOCK_FAILURE_RATE`, `INVENTORY_LATENCY_*` | 1%, 5% OOS, 5-50ms |
| payment-worker | `PAYMENT_FAILURE_RATE`, `PAYMENT_DECLINE_FAILURE_RATE`, `PAYMENT_LATENCY_*` | 2%, 5% decline, 50-200ms |
| shipping-worker | `SHIPPING_FAILURE_RATE`, `SHIPPING_LATENCY_*` | 2%, 20-100ms |
| notification-worker | `NOTIFICATION_FAILURE_RATE`, `NOTIFICATION_LATENCY_*` | 1%, 5-30ms |

Adjust in `compose.yml` or override with environment variables.

## Testing

```bash
# Run all tests
make test

# Run workflow tests only
make test-workflow

# Run API integration tests
make test-api

# Run workflow E2E tests
make test-workflows-e2e
```

## Scout Integration

### Configure Scout

Add these to your `.env` file:

```bash
SCOUT_ENDPOINT=https://your-tenant.base14.io:4318
SCOUT_CLIENT_ID=your-client-id
SCOUT_CLIENT_SECRET=your-client-secret
SCOUT_TOKEN_URL=https://your-tenant.base14.io/oauth/token
```

### Verify Integration

```bash
make verify-scout
```

### Import Dashboards

Import the pre-built Grafana dashboards into Scout (uses ClickHouse datasource):

1. Go to Scout Grafana → Dashboards → Import
2. Upload or paste the JSON from:
   - `dashboards/order-fulfillment-overview.json` - Order metrics, decision paths, latency
   - `dashboards/service-performance.json` - Service health, trace metrics, errors
   - `dashboards/revenue-analytics.json` - Revenue tracking, order values, customer tier analysis
3. Select your ClickHouse datasource when prompted

**Dashboard Panels:**

| Dashboard | Panels |
|-----------|--------|
| Order Fulfillment Overview | Total Orders, Approved/Backordered/Failed stats, Order Throughput, Decision Path Distribution, Orders by Customer Tier, Processing Latency (p50/p90/p99), Fraud Risk Score Distribution, Payment/Rejection Failures by Reason |
| Service Performance | Service Health (API + 5 services), Span Rate by Service, Span Latency p95, Activity Latency, Errors by Service, Error Rate |
| Revenue Analytics | Total Revenue, Average Order Value, Lost Revenue (Failed), Revenue Over Time, Avg Order Value Over Time, Revenue by Customer Tier, Order Value Distribution, High Value Orders stats, Orders by Value Range |

## Service URLs

| Service | URL |
|---------|-----|
| API | <http://localhost:8080> |
| Temporal UI | <http://localhost:8088> |
| OTel Collector Health | <http://localhost:13133> |

## Project Structure

```text
├── cmd/
│   ├── api/           # HTTP API server
│   ├── worker/        # Main Temporal worker (orchestration)
│   └── loadgen/       # Load generator CLI
├── config/            # Configuration
├── dashboards/        # Grafana dashboard JSON files
├── internal/
│   ├── database/      # GORM setup
│   ├── handlers/      # HTTP handlers
│   ├── models/        # Data models
│   └── workflows/     # Temporal workflows
├── pkg/
│   ├── simulation/    # Failure/latency simulation
│   ├── telemetry/     # OTel setup
│   └── temporal/      # Temporal client/worker helpers
├── services/          # Microservice workers
│   ├── fraud-worker/
│   ├── inventory-worker/
│   ├── payment-worker/
│   ├── shipping-worker/
│   └── notification-worker/
├── scripts/           # Test scripts
└── tests/             # Unit and integration tests
```

## Stack

| Component | Version |
|-----------|---------|
| Go | 1.25 |
| Temporal SDK | 1.38.0 |
| Echo | 4.15.0 |
| GORM | 1.31.1 |
| PostgreSQL | 18 |
| OTel SDK | 1.39.0 |

## Production Considerations

This example prioritizes **clarity and observability** over production hardening. Before deploying similar patterns to production, consider the following:

### Security

| Area | Current State | Production Recommendation |
|------|---------------|---------------------------|
| Authentication | None | Add JWT/OAuth2 with proper validation |
| Input validation | Basic | Add comprehensive validation (e.g., `go-playground/validator`) |
| Rate limiting | None | Add per-client rate limiting |
| Security headers | None | Add CSP, HSTS, X-Frame-Options, etc. |
| Secrets management | Environment variables | Use a secrets manager (Vault, AWS Secrets Manager) |

### Database

| Area | Current State | Production Recommendation |
|------|---------------|---------------------------|
| Migrations | GORM AutoMigrate | Use versioned migrations (`golang-migrate`) |
| Connection pooling | Default settings | Configure pool size, timeouts, and idle connections |
| Money fields | `float64` | Use `decimal` type for monetary precision |
| Indexes | Basic | Add compound indexes for query patterns |

### Observability

| Area | Current State | Production Recommendation |
|------|---------------|---------------------------|
| Metric cardinality | Some high-cardinality attributes | Move `order_id`, `trace_id` to exemplars only |
| Error handling | Basic | Add structured domain errors with retry classification |

### Temporal

| Area | Current State | Production Recommendation |
|------|---------------|---------------------------|
| Activity heartbeats | Not configured | Add `HeartbeatTimeout` for long-running activities |
| Workflow versioning | Not used | Add versioning for safe workflow updates |
| Timeouts | Basic | Configure `WorkflowExecutionTimeout`, `WorkflowRunTimeout` |

### Infrastructure

| Area | Current State | Production Recommendation |
|------|---------------|---------------------------|
| Health checks | Basic liveness | Add readiness probes with dependency checks |
| Graceful shutdown | Basic | Ensure proper drain of in-flight requests |
| Circuit breakers | None | Add for external service calls |

These simplifications are intentional to keep the example focused on demonstrating Temporal workflow patterns and OpenTelemetry instrumentation.

## Resources

- [Temporal Documentation](https://docs.temporal.io/)
- [Temporal Go SDK](https://github.com/temporalio/sdk-go)
- [Echo Framework Documentation](https://echo.labstack.com/)
- [GORM Documentation](https://gorm.io/docs/)
- [OpenTelemetry Go](https://opentelemetry.io/docs/languages/go/)
- [base14 Scout Documentation](https://docs.base14.io)

