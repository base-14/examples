# Logs Verification

## Log Levels & Components

**Levels**: INFO (successful ops), WARN (auth failures, validation),
ERROR (unhandled exceptions)

**Components**: telemetry, database, redis, auth-controller,
auth-middleware, socket-emitter, error-handler

## Common Log Patterns

**Successful Operations (INFO)**:

```json
[info] [socket-emitter][trace_id=42f42b42]: Article event emitted
{
  "event": "article:created",
  "articleId": "693424f523bf2349948546ea",
  "articleTitle": "Test Article"
}
```

**Authentication Failures (WARN)**:

```json
[warn] [auth-middleware][trace_id=bc3fb601]: Authentication failed - missing token
{
  "path": "/api/v1/articles",
  "method": "POST",
  "reason": "missing_token"
}
```

**Validation Errors (WARN)**:

```json
[warn] [error-handler][trace_id=3f19548b]: Request error
{
  "path": "/api/v1/articles/invalid123",
  "statusCode": 404,
  "error": "Article not found"
}
```

## Trace Correlation ✅

All logs include `trace_id` for correlation:

```text
Application Log: [info] [socket-emitter][trace_id=f650edf6]:
  Article event emitted
OTel Collector:  Trace ID: f650edf660f5c3df685a6ffda7aba95e
                          ↑ First 8 chars match
```

## Verification Commands

```bash
# View application logs
docker logs express-mongodb-app 2>&1 | tail -50

# Filter by level
docker logs express-mongodb-app 2>&1 | grep "\[warn\]"

# Filter by component
docker logs express-mongodb-app 2>&1 | grep "\[auth-middleware\]"

# Find logs for trace
docker logs express-mongodb-app 2>&1 | grep "trace_id=f650edf6"

# View OTel collector logs
docker logs otel-collector 2>&1 | grep "LogRecord #" -A 15 | head -50
```

## Base14 Scout Queries

```promql
# Authentication failures
component = "auth-middleware" AND level = "WARN"

# Article events
component = "socket-emitter" AND event CONTAINS "article:"

# Trace request lifecycle
trace_id = "<trace-id>"
```

**Key Attributes**: `user.id`, `article.id`, `event`, `path`, `method`,
`statusCode`, `component`, `deployment.environment`

For detailed scenario-based verification, see
[telemetry-verification.md](./telemetry-verification.md)
