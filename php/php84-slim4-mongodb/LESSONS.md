# OTel Instrumentation Lessons -- Slim 4 Reference for Slim 3

Patterns, conventions, and gotchas extracted from the `php84-slim4-mongodb`
project. Use this as a checklist when updating `php84-slim3-mongodb`.

## A. OTel Semantic Convention Rules

### Span status

- UNSET for success. Do NOT call `setStatus(STATUS_OK)`.
- ERROR only for 5xx / unhandled exceptions.
- Do NOT set ERROR for 4xx (401, 403, 404, 422). These are expected
  application behavior, not system failures.

### Log severity

OTel severity model differs from Monolog:

| Monolog | OTel |
| ------- | ---- |
| DEBUG | DEBUG |
| INFO | INFO |
| NOTICE | INFO |
| WARNING | WARN |
| ERROR | ERROR |
| CRITICAL | ERROR |
| ALERT | ERROR |
| EMERGENCY | FATAL |

Mapping must be applied in two places: stderr formatter and OTel log handler.

### Resource attributes

Use `deployment.environment.name` (not deprecated `deployment.environment`).
Set via `OTEL_RESOURCE_ATTRIBUTES=deployment.environment.name=development`.

### Custom attribute namespace

- All app-specific span attributes use `app.` prefix:
  `app.article.id`, `app.auth.action`, `app.auth.result`, `app.auth.failure_reason`.
- User identification: `enduser.id` (semconv standard, no `app.` prefix).
- Log context keys do NOT need `app.` prefix (e.g. `['article.id' => $id]`).

### Metric naming

- Counters use `app.` prefix: `app.user.logins`, `app.article.creates`.
- No `.total` suffix (the counter type already implies accumulation).
- Use attributes for differentiation: `app.user.logins` with
  `['result' => 'success']` or `['result' => 'failure']` instead of
  separate counter names.
- Meter instrumentation scope name: `'slim-app'`.

## B. Auto-Instrumentation: What NOT to Duplicate

### Do NOT manually create or set

- HTTP span creation or HTTP span attributes (`http.request.method`,
  `http.route`, `http.response.status_code`).
- HTTP server metrics (request duration, request count).
- MongoDB span attributes (`db.system`, `db.operation.name`,
  `db.mongodb.collection`, `db.namespace`).

### Slim 3 difference

`opentelemetry-auto-slim` only supports Slim 4+. Slim 3 needs a manual
`TelemetryMiddleware` for the root HTTP SERVER span. However, the same
rules apply: do NOT duplicate MongoDB auto-instrumented attributes.

## C. Span Scope Activation

```php
$span = $tracer->spanBuilder($name)->setSpanKind($spanKind)->startSpan();
$scope = $span->activate();
try {
    return $callback($span);
} catch (\Exception $e) {
    $span->recordException($e);
    $span->setStatus(StatusCode::STATUS_ERROR, $e->getMessage());
    throw $e;
} finally {
    $scope->detach();
    $span->end();
}
```

Why it matters:

1. Child spans (auto-instrumented MongoDB) parent correctly.
2. OTel Monolog handler attaches `traceId`/`spanId` from current context.
3. `Span::getCurrent()` returns the correct span in nested code.
4. `detach()` must come before `end()` to restore previous context.

### Slim 3 difference: scope activation

The manual `TelemetryMiddleware` in Slim 3 also needs scope activation.
The current Slim 3 code may be missing `$span->activate()` /
`$scope->detach()`. This is the most critical fix.

## D. Log Severity Mapping (Monolog 3 Gotcha)

### The heap corruption problem

Monolog 3's `LogRecord` is immutable. Using a Monolog Processor with
`LogRecord::with(levelName: 'WARN')` triggers `zend_mm_heap corrupted`
when the PHP OTel extension is loaded. This is a memory corruption bug
in the extension's interaction with PHP's memory manager during
immutable object cloning.

### The solution: two components

1. **`OtelLevelFormatter`** (extends `LineFormatter`): For stderr output.
   After `parent::format()`, do `str_replace()` on the level name string.
   Never touches the LogRecord object.

2. **`OtelLogHandler`** (extends stock OTel Monolog Handler): For the OTel
   pipeline. Override `write()` to build a fresh `API\LogRecord` with
   the correct `SeverityText`, reading the original Monolog level from
   `$record['level_name']` (array access on the normalized record).

Both share the same `LEVEL_MAP` constant. Keep them in sync.

## E. Structured Logging Conventions

- Logger name: `'slim-app'` (matches tracer/meter instrumentation scope).
- Handlers: stderr (`OtelLevelFormatter`) + OTel (`OtelLogHandler`).
  OTel handler wrapped in try/catch so app works without OTel.
- Warning level: validation failures (422), not-found (404), forbidden (403),
  auth failures (401).
- Error level: unhandled exceptions only (in the error handler).
- Info level: successful business operations (user registered, article created).
- Context keys: `['article.id' => $id, 'user.id' => $userId]`,
  `['reason' => 'missing fields']`, `['exception' => $exception]`.

## F. Custom Error Handler

Records unhandled exceptions on the active span and logs with trace context:

```php
$span = Span::getCurrent();
$span->recordException($exception);
$span->setStatus(StatusCode::STATUS_ERROR, $exception->getMessage());
$logger->error('Unhandled exception', [
    'exception' => $exception,
    'uri' => (string) $request->getUri(),
    'method' => $request->getMethod(),
]);
```

### Slim 3 difference: error handler

Slim 3 uses `$container['errorHandler']` instead of
`$errorMiddleware->setDefaultErrorHandler()`.

## G. JWT / Security Patterns

- Fail-fast: DI container throws `RuntimeException` if `JWT_SECRET`
  is missing or empty. No silent empty-string fallback.
- DI injection: both `JwtMiddleware` and `AuthController` receive the
  secret via constructor parameter, not `$_ENV` access.
- JWT payload: only `sub` (user ID), `iat`, `exp`. No PII (name, email).
- Auth failure recording: set `app.auth.result=failed` and
  `app.auth.failure_reason` on the span, but do NOT set `STATUS_ERROR`
  (401 is not a server error).
- `APP_DEBUG` env var controls error detail exposure in responses.

## H. Documentation Structure

### README.md sections

1. Title + one-line description + docs link
2. Stack Profile table
3. What's Instrumented (auto vs manual, span hierarchy, semconv compliance)
4. Technology Stack table
5. Prerequisites
6. Quick Start (credentials, docker compose, test script, verify script)
7. Viewing Traces in Scout
8. Configuration (required env vars, application env vars with defaults)
9. API Endpoints (grouped, with auth column)
10. Example Requests
11. Docker Architecture (ASCII diagram)
12. Development (docker commands, service URLs)
13. Troubleshooting (numbered steps for common issues)
14. Resources (external links)

### INSTRUMENTATION.md sections

1. Install PHP extensions
2. Install composer dependencies (matching `composer.json` versions)
3. Set environment variables (with `deployment.environment.name`)
4. Bootstrap the framework (with custom error handler)
5. Register shutdown handlers
6. What auto-instrumentation provides (what NOT to do)
7. Framework-specific middleware patterns
8. Business logic spans with scope activation
9. Log severity mapping (with heap corruption explanation)
10. Logger wiring (DI container setup)
11. Application metrics (naming conventions)
12. Verify (what to check in collector output)
13. What you get for free

## I. Slim 3 Specific Differences to Address

| Concern | Slim 4 | Slim 3 |
| ------- | ------ | ------ |
| HTTP auto-instrumentation | `opentelemetry-auto-slim` | Manual `TelemetryMiddleware` |
| Middleware interface | PSR-15 `MiddlewareInterface` | Callable `($request, $response, $next)` |
| Container | PHP-DI via `AppFactory::setContainer()` | Built-in Pimple `$app->getContainer()` |
| Body parsing | `addBodyParsingMiddleware()` | Built-in |
| Error handler | `addErrorMiddleware()->setDefaultErrorHandler()` | `$container['errorHandler']` |
| JSON response | Manual `$response->getBody()->write()` | `$response->withJson()` |
| Route groups | `RouteCollectorProxy` | `$app->group()` with closure |
| PHP 8.4 compat | Clean, no warnings | Deprecation warnings, needs `error_reporting` suppression |
| HTTP span status | Auto-slim handles it | Manual: set in `TelemetryMiddleware` |
| HTTP metrics | Auto-slim handles it | Must be manual if needed |

### Critical Slim 3 fixes needed

1. Add scope activation to `TracesOperations::withSpan()` and `TelemetryMiddleware`
2. Remove `STATUS_OK` from success paths (leave UNSET)
3. Remove `STATUS_ERROR` from 4xx paths in middleware
4. Add `OtelLevelFormatter` + `OtelLogHandler` for severity mapping
5. Namespace custom attributes with `app.` prefix
6. Use `enduser.id` instead of `user.id`
7. Add structured logging to all controllers
8. Add custom error handler with span recording
9. Fix metric naming (`app.` prefix, no `.total`, attribute-based differentiation)
10. Fix `deployment.environment` -> `deployment.environment.name`
11. Do NOT duplicate `opentelemetry-auto-mongodb` attributes
12. JWT fail-fast + DI injection
