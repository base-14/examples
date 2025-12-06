# Traces Verification

## Instrumentation Scopes

**Auto-instrumentation**: HTTP, MongoDB, Redis, Socket.IO, DNS, Network

**Custom spans**: article-controller, auth-controller, job-processor,
socket-emitter

## Common Span Patterns

**HTTP Request**:

```text
POST (root) → mongodb.find (auth) → controller span →
mongodb operation → socket.emit → send /
```

**Background Job** (with trace propagation):

```text
job.publishArticle.process (same trace ID as HTTP) →
mongodb.find → mongodb.update → socket.emit
```

## Key Span Attributes

- **HTTP**: `http.method`, `http.status_code`, `user.id`, `user.email`
- **Controller**: `article.id`, `article.title`, `user.id`, span events
  (article_created, job_enqueued, etc.)
- **MongoDB**: `db.operation`, `db.mongodb.collection`
  (query params sanitized with `?`)
- **Jobs**: `job.id`, `job.attempt`, `job.duration_ms`

## Verification Commands

```bash
# Find trace by ID
docker logs otel-collector 2>&1 | grep "Trace ID : <trace-id>" -A 30

# Get trace ID from app logs
docker logs express-mongodb-app 2>&1 | grep "trace_id=" | tail -5

# List all span names
docker logs otel-collector 2>&1 | grep "Name :" | sort -u

# Find error spans
docker logs otel-collector 2>&1 | grep -B 5 "Status code    : Error"
```

## Base14 Scout Queries

```promql
# Slow requests
http.server.duration > 100ms

# Authentication failures
span.event.name = "auth_failed"

# Article lifecycle
article.id = "<article-id>"
```

**Critical Feature**: Background jobs maintain trace context
(same trace ID as HTTP request that enqueued them) ✅

For detailed scenario-based verification, see
[telemetry-verification.md](./telemetry-verification.md)
