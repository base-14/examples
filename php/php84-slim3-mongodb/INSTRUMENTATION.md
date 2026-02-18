# Instrumenting PHP 8.4 + Slim 3 with OpenTelemetry

Step-by-step guide to add distributed tracing, metrics, and logs
to a Slim 3 application. No Docker required.

## 1. Install PHP extensions

```bash
pecl install opentelemetry mongodb
```

Enable them in your `php.ini`:

```ini
extension=opentelemetry
extension=mongodb
```

The `opentelemetry` extension is required for auto-instrumentation
to hook into PHP's internals.

## 2. Suppress Slim 3 deprecation warnings

Slim 3 is EOL and triggers deprecation warnings on PHP 8.4.
Add to your `php.ini`:

```ini
error_reporting = E_ALL & ~E_DEPRECATED & ~E_NOTICE
```

## 3. Install composer dependencies

```bash
composer require \
  slim/slim:~3.12 \
  mongodb/mongodb:^2.0 \
  firebase/php-jwt:^7.0 \
  vlucas/phpdotenv:^5.6 \
  monolog/monolog:^3.7 \
  open-telemetry/sdk:^1.13 \
  open-telemetry/exporter-otlp:^1.4 \
  open-telemetry/opentelemetry-auto-mongodb:^0.2 \
  open-telemetry/opentelemetry-logger-monolog:^1.1 \
  php-http/guzzle7-adapter:^1.0 \
  guzzlehttp/psr7:^2.7
```

Note: `opentelemetry-auto-slim` only supports Slim 4+. HTTP
spans must be created manually via `TelemetryMiddleware` (step 7).

## 4. Set environment variables

```bash
export OTEL_PHP_AUTOLOAD_ENABLED=true
export OTEL_SERVICE_NAME=my-slim-app
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OTEL_TRACES_EXPORTER=otlp
export OTEL_METRICS_EXPORTER=otlp
export OTEL_LOGS_EXPORTER=otlp
export OTEL_RESOURCE_ATTRIBUTES=deployment.environment.name=development
```

`OTEL_PHP_AUTOLOAD_ENABLED=true` activates auto-instrumentation
(MongoDB spans). Use `deployment.environment.name` (not the
deprecated `deployment.environment`).

## 5. Bootstrap Slim 3 with exception recording

The `determineRouteBeforeAppMiddleware` setting is required so the
`TelemetryMiddleware` can read the matched route pattern for span names.

```php
<?php

use OpenTelemetry\API\Trace\Span;
use OpenTelemetry\API\Trace\StatusCode;

require __DIR__ . '/../vendor/autoload.php';

Dotenv\Dotenv::createImmutable(__DIR__ . '/..')->safeLoad();

require __DIR__ . '/../src/telemetry.php';

$app = new \Slim\App([
    'settings' => [
        'displayErrorDetails' => ($_ENV['APP_DEBUG'] ?? 'false') === 'true',
        'addContentLengthHeader' => false,
        'determineRouteBeforeAppMiddleware' => true,
    ],
]);

require __DIR__ . '/../src/dependencies.php';
require __DIR__ . '/../src/middleware.php';
require __DIR__ . '/../src/routes.php';

$container = $app->getContainer();
$container['errorHandler'] = function ($c) {
    return function ($request, $response, $exception) use ($c) {
        $span = Span::getCurrent();
        $span->recordException($exception);
        $span->setStatus(StatusCode::STATUS_ERROR, $exception->getMessage());

        $c['logger']->error('Unhandled exception', [
            'exception' => $exception,
            'uri' => (string) $request->getUri(),
            'method' => $request->getMethod(),
        ]);

        $statusCode = 500;
        if (method_exists($exception, 'getCode')
            && $exception->getCode() >= 400
            && $exception->getCode() < 600) {
            $statusCode = $exception->getCode();
        }

        return $response->withJson([
            'error' => ($c['settings']['displayErrorDetails'] ?? false)
                ? $exception->getMessage()
                : 'Internal server error',
        ], $statusCode);
    };
};

$app->run();
```

## 6. Register shutdown handlers

Flush telemetry before php-fpm workers exit:

```php
<?php
// src/telemetry.php
use App\Telemetry\Shutdown;
Shutdown::register();
```

See `src/Telemetry/Shutdown.php` for the full implementation —
it calls `forceFlush()` on TracerProvider, MeterProvider, and
LoggerProvider, and handles SIGTERM/SIGINT signals.

## 7. Add HTTP tracing middleware

Since `opentelemetry-auto-slim` doesn't support Slim 3, create
a `TelemetryMiddleware` that produces the root SERVER span:

```php
<?php

namespace App\Middleware;

use OpenTelemetry\API\Globals;
use OpenTelemetry\API\Trace\SpanKind;
use OpenTelemetry\API\Trace\StatusCode;

class TelemetryMiddleware
{
    public function __invoke($request, $response, $next)
    {
        $tracer = Globals::tracerProvider()->getTracer('slim-app');
        $method = $request->getMethod();
        $path = (string) $request->getUri()->getPath();

        $span = $tracer->spanBuilder("$method $path")
            ->setSpanKind(SpanKind::KIND_SERVER)
            ->startSpan();
        $scope = $span->activate();

        $span->setAttribute('http.method', $method);
        $span->setAttribute('http.url', (string) $request->getUri());
        $span->setAttribute('http.target', $path);
        $span->setAttribute('http.scheme',
            $request->getUri()->getScheme() ?: 'http');

        try {
            $response = $next($request, $response);

            $route = $request->getAttribute('route');
            if ($route instanceof \Slim\Route) {
                $pattern = $route->getPattern();
                $span->updateName("$method $pattern");
                $span->setAttribute('http.route', $pattern);
            }

            $span->setAttribute('http.status_code',
                $response->getStatusCode());

            return $response;
        } catch (\Exception $e) {
            $span->recordException($e);
            $span->setStatus(
                StatusCode::STATUS_ERROR, $e->getMessage());
            throw $e;
        } finally {
            $scope->detach();
            $span->end();
        }
    }
}
```

Key details:

- **Scope activation** (`$span->activate()`) makes this span
  current so MongoDB auto-spans and logs inherit the trace context.
- Span name updates from `/api/articles/abc123` to
  `/api/articles/{id}` after route matching (low cardinality).
- Do **not** set `STATUS_OK` on success — leave as UNSET.
- Do **not** set `STATUS_ERROR` for 4xx — only for exceptions.

## 8. Wire up the logger with OTel correlation

```php
use Monolog\Handler\StreamHandler;
use Monolog\Logger;
use OpenTelemetry\API\Globals;
use OpenTelemetry\Contrib\Logs\Monolog\Handler as OtelLogHandler;

$container['logger'] = function () {
    $logger = new Logger('slim-app');
    $logger->pushHandler(new StreamHandler('php://stderr', Logger::DEBUG));

    try {
        $loggerProvider = Globals::loggerProvider();
        $logger->pushHandler(new OtelLogHandler($loggerProvider, Logger::DEBUG));
    } catch (\Throwable $e) {
        // OTel logger not available, continue with stderr only
    }

    return $logger;
};
```

The stock OTel Monolog handler automatically attaches `traceId`
and `spanId` to every log record via the active span context.

## 9. Add business metrics

```php
<?php

namespace App\Telemetry;

use OpenTelemetry\API\Globals;

class Metrics
{
    private static function getCounter(string $name, string $desc)
    {
        return Globals::meterProvider()
            ->getMeter('slim-app')
            ->createCounter($name, '', $desc);
    }

    public static function authLoginSuccess(): void
    {
        self::getCounter('app.user.logins', 'User login attempts')
            ->add(1, ['result' => 'success']);
    }

    public static function articleCreated(): void
    {
        self::getCounter('app.article.creates', 'Articles created')
            ->add(1);
    }
}
```

Call as one-liners in controllers: `Metrics::articleCreated()`.

## 10. Write clean controllers

Controllers contain business logic, logging, and metric calls.
No span wrapping or trace context management:

```php
use App\Telemetry\Metrics;

class ArticleController
{
    public function create($request, $response)
    {
        $data = $request->getParsedBody();
        $user = $request->getAttribute('user');

        if (empty($data['title']) || empty($data['body'])) {
            $this->logger->warning('Article validation failed',
                ['reason' => 'missing fields']);
            return $response->withJson(
                ['error' => 'Title and body are required'], 422);
        }

        $data['author_id'] = $user['sub'];
        $article = $this->container['articleRepository']->create($data);
        Metrics::articleCreated();

        $this->logger->info('Article created',
            ['article.id' => $article['id'],
             'user.id' => $user['sub']]);

        return $response->withJson(['article' => $article], 201);
    }
}
```

## 11. Verify

A typical request produces this span hierarchy:

```text
POST /api/articles              (SERVER - TelemetryMiddleware)
  +-- MongoDB articles.insert   (CLIENT - auto-mongodb)
```

Check the collector output for:

- Spans with proper parent-child nesting
- Logs with `traceId`/`spanId` correlation
- Metrics with `app.` prefix

## What you get for free

The only manual OTel code in this example:

1. **`TelemetryMiddleware`** for HTTP spans (Slim 3 only — Slim 4
   gets this from `opentelemetry-auto-slim`)
2. **3 lines** in the error handler to record exceptions on spans
3. **Stock OTel Monolog handler** for log-trace correlation
4. **Metrics class** with static counter methods
5. **Shutdown handler** to flush telemetry in php-fpm

MongoDB spans are fully automatic via `opentelemetry-auto-mongodb`.
