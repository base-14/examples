# Instrumenting PHP 8.4 + Slim 3 with OpenTelemetry

Step-by-step guide to add distributed tracing, metrics, and logs
to a Slim 3 application. No Docker required.

## 1. Install PHP extensions

```bash
pecl install opentelemetry-1.2.1 mongodb-2.2.1
```

Enable them in your `php.ini`:

```ini
extension=opentelemetry
extension=mongodb
```

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

The `opentelemetry-auto-mongodb` package automatically creates
spans for all MongoDB driver operations. Do not duplicate these
attributes manually in your application code.

Note: `opentelemetry-auto-slim` only supports Slim 4+. HTTP
spans must be created manually via `TelemetryMiddleware`.

## 4. Set environment variables

OTel auto-configures via environment. Set these before your
app starts (e.g. in your shell, `.env`, or process manager):

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

Use `deployment.environment.name` (not the deprecated `deployment.environment`).

## 5. Bootstrap Slim 3

Slim 3 uses a built-in Pimple container. The
`determineRouteBeforeAppMiddleware` setting is required so the
TelemetryMiddleware can read the matched route pattern for span names.

```php
<?php

use OpenTelemetry\API\Trace\Span;
use OpenTelemetry\API\Trace\StatusCode;

require __DIR__ . '/../vendor/autoload.php';

Dotenv\Dotenv::createImmutable(__DIR__ . '/..')->safeLoad();

require __DIR__ . '/../src/telemetry.php';

$displayErrors = ($_ENV['APP_DEBUG'] ?? 'false') === 'true';

$app = new \Slim\App([
    'settings' => [
        'displayErrorDetails' => $displayErrors,
        'addContentLengthHeader' => false,
        'determineRouteBeforeAppMiddleware' => true,
    ],
]);

require __DIR__ . '/../src/dependencies.php';
require __DIR__ . '/../src/middleware.php';
require __DIR__ . '/../src/routes.php';

// Custom error handler with span recording
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

        $displayErrors = $c['settings']['displayErrorDetails'] ?? false;
        $statusCode = 500;
        if (method_exists($exception, 'getCode')
            && $exception->getCode() >= 400
            && $exception->getCode() < 600) {
            $statusCode = $exception->getCode();
        }

        return $response->withJson([
            'error' => $displayErrors
                ? $exception->getMessage()
                : 'Internal server error',
        ], $statusCode);
    };
};

$app->run();
```

Key differences from Slim 4:

- `new \Slim\App($settings)` instead of `AppFactory::create()`
- `determineRouteBeforeAppMiddleware` setting required
- Error handler uses `$container['errorHandler']` closure
- `$response->withJson()` available (Slim 4 requires manual JSON writing)

## 6. Register shutdown handlers

Create `src/Telemetry/Shutdown.php` to flush telemetry on
process exit:

```php
<?php

namespace App\Telemetry;

use OpenTelemetry\API\Globals;

class Shutdown
{
    public static function register(): void
    {
        register_shutdown_function([self::class, 'flush']);

        if (!extension_loaded('pcntl')) {
            return;
        }

        pcntl_async_signals(true);
        $handler = function () {
            self::flush();
            exit(0);
        };

        pcntl_signal(SIGTERM, $handler);
        pcntl_signal(SIGINT, $handler);
    }

    public static function flush(): void
    {
        try {
            $tp = Globals::tracerProvider();
            if (method_exists($tp, 'forceFlush')) {
                $tp->forceFlush();
            }

            $mp = Globals::meterProvider();
            if (method_exists($mp, 'forceFlush')) {
                $mp->forceFlush();
            }

            $lp = Globals::loggerProvider();
            if (method_exists($lp, 'forceFlush')) {
                $lp->forceFlush();
            }
        } catch (\Throwable $e) {
            // swallow
        }
    }
}
```

## 7. Add HTTP tracing middleware

Since `opentelemetry-auto-slim` only supports Slim 4+, HTTP
spans must be created manually. The middleware creates a root
SERVER span with scope activation:

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

            // Update span name to route pattern
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

Important conventions:

- Do **not** set `STATUS_OK` on success. Leave span status as UNSET.
- Do **not** set `STATUS_ERROR` for 4xx responses. Only set it for
  unhandled exceptions (5xx).
- Scope activation is critical: `$span->activate()` makes this span
  "current" so child spans and logs inherit the correct trace context.

## 8. Write Slim 3 callable middleware

Slim 3 uses callable middleware instead of PSR-15
`MiddlewareInterface`:

```php
<?php

namespace App\Middleware;

class SecurityHeadersMiddleware
{
    public function __invoke($request, $response, $next)
    {
        $response = $next($request, $response);

        return $response
            ->withHeader('X-Content-Type-Options', 'nosniff')
            ->withHeader('X-Frame-Options', 'DENY');
    }
}
```

Key differences from Slim 4:

- Uses `__invoke($request, $response, $next)` signature
- Calls `$next($request, $response)` instead of `$handler->handle($request)`
- Has access to `$response` parameter directly

## 9. Add business logic spans with scope activation

Create a `TracesOperations` trait to wrap any operation in a
child span. The key detail is **scope activation**: calling
`$span->activate()` makes the span current in context, so child
spans (like auto-instrumented MongoDB operations) properly nest
and logs automatically get trace correlation.

```php
<?php

namespace App\Telemetry;

use OpenTelemetry\API\Globals;
use OpenTelemetry\API\Trace\SpanKind;
use OpenTelemetry\API\Trace\StatusCode;

trait TracesOperations
{
    protected function withSpan(
        string $name,
        callable $callback,
        array $attributes = [],
        int $spanKind = SpanKind::KIND_INTERNAL,
        string $tracerName = 'slim-app'
    ): mixed {
        $tracer = Globals::tracerProvider()->getTracer($tracerName);
        $span = $tracer->spanBuilder($name)
            ->setSpanKind($spanKind)
            ->startSpan();
        $scope = $span->activate();

        foreach ($attributes as $k => $v) {
            $span->setAttribute($k, $v);
        }

        try {
            return $callback($span);
        } catch (\Exception $e) {
            $span->recordException($e);
            $span->setStatus(
                StatusCode::STATUS_ERROR,
                $e->getMessage()
            );
            throw $e;
        } finally {
            $scope->detach();
            $span->end();
        }
    }
}
```

Important conventions:

- Do **not** set `STATUS_OK` on success. OTel convention is to leave
  span status as UNSET for successful operations.
- Only set `STATUS_ERROR` for exceptions (5xx). Do not set it for
  4xx client errors (those are expected application behavior).
- Namespace custom attributes with `app.` prefix (e.g. `app.article.id`).
- Use `enduser.id` for user identification (OTel semantic convention).

Use it in your controllers with structured logging:

```php
use App\Telemetry\Metrics;
use App\Telemetry\TracesOperations;
use Psr\Log\LoggerInterface;

class ArticleController
{
    use TracesOperations;

    private $container;
    private LoggerInterface $logger;

    public function __construct($container)
    {
        $this->container = $container;
        $this->logger = $container['logger'];
    }

    public function create($request, $response)
    {
        return $this->withSpan(
            'article.create',
            function ($span) use ($request, $response) {
                $data = $request->getParsedBody();
                $user = $request->getAttribute('user');

                if (empty($data['title']) || empty($data['body'])) {
                    $this->logger->warning('Article validation failed',
                        ['reason' => 'missing fields']);
                    return $response->withJson(
                        ['error' => 'Title and body are required'], 422);
                }

                $repo = $this->container['articleRepository'];
                $article = $repo->create($data);

                $span->setAttribute('enduser.id', $user['sub']);
                $span->setAttribute('app.article.id', $article['id']);

                Metrics::articleCreated();
                $this->logger->info('Article created',
                    ['article.id' => $article['id'],
                     'user.id' => $user['sub']]);

                return $response->withJson(
                    ['article' => $article], 201);
            }
        );
    }
}
```

## 10. Map log severity to OTel conventions

Monolog uses level names like `WARNING`, `CRITICAL`, and `ALERT`
that don't match OTel's severity model (`WARN`, `ERROR`, `FATAL`).
Two components handle this mapping:

**For stderr output** -- `OtelLevelFormatter` extends Monolog's
`LineFormatter` and replaces level names in the formatted string:

```php
<?php

namespace App\Telemetry;

use Monolog\Formatter\LineFormatter;
use Monolog\LogRecord;

class OtelLevelFormatter extends LineFormatter
{
    private const LEVEL_MAP = [
        'DEBUG' => 'DEBUG', 'INFO' => 'INFO', 'NOTICE' => 'INFO',
        'WARNING' => 'WARN', 'ERROR' => 'ERROR',
        'CRITICAL' => 'ERROR', 'ALERT' => 'ERROR',
        'EMERGENCY' => 'FATAL',
    ];

    public function format(LogRecord $record): string
    {
        $output = parent::format($record);
        $monologLevel = $record->level->getName();
        $otelLevel = self::LEVEL_MAP[$monologLevel] ?? $monologLevel;
        if ($monologLevel !== $otelLevel) {
            $output = str_replace($monologLevel, $otelLevel, $output);
        }
        return $output;
    }
}
```

**For the OTel pipeline** -- `OtelLogHandler` extends the stock OTel
Monolog handler and overrides `write()` to set `SeverityText`
correctly before emitting the log record:

```php
<?php

namespace App\Telemetry;

use OpenTelemetry\API\Logs as API;
use OpenTelemetry\Contrib\Logs\Monolog\Handler as OTelHandler;

class OtelLogHandler extends OTelHandler
{
    private const LEVEL_MAP = [
        'DEBUG' => 'DEBUG', 'INFO' => 'INFO', 'NOTICE' => 'INFO',
        'WARNING' => 'WARN', 'ERROR' => 'ERROR',
        'CRITICAL' => 'ERROR', 'ALERT' => 'ERROR',
        'EMERGENCY' => 'FATAL',
    ];

    protected function write($record): void
    {
        $formatted = $record['formatted'];
        $monologLevel = $record['level_name'];
        $otelLevel = self::LEVEL_MAP[$monologLevel] ?? $monologLevel;

        $logRecord = (new API\LogRecord())
            ->setTimestamp(
                (int) $record['datetime']->format('Uu') * 1000)
            ->setSeverityNumber(
                API\Severity::fromPsr3($monologLevel))
            ->setSeverityText($otelLevel)
            ->setBody($formatted['message']);

        foreach (['context', 'extra'] as $key) {
            if (isset($formatted[$key])
                && count($formatted[$key]) > 0) {
                $logRecord->setAttribute($key, $formatted[$key]);
            }
        }

        $this->getLogger($record['channel'])->emit($logRecord);
    }
}
```

Why not use a Monolog Processor? Monolog 3's `LogRecord` is
immutable via ArrayAccess, and using `LogRecord::with(levelName:)`
causes `zend_mm_heap corrupted` due to a memory conflict with
the PHP OTel extension.

## 11. Wire up the logger

Register both handlers in the Slim 3 Pimple container:

```php
use App\Telemetry\OtelLevelFormatter;
use App\Telemetry\OtelLogHandler;
use Monolog\Handler\StreamHandler;
use Monolog\Logger;
use OpenTelemetry\API\Globals;

$container['logger'] = function () {
    $logger = new Logger('slim-app');

    $stderrHandler = new StreamHandler('php://stderr', Logger::DEBUG);
    $stderrHandler->setFormatter(new OtelLevelFormatter());
    $logger->pushHandler($stderrHandler);

    try {
        $loggerProvider = Globals::loggerProvider();
        $logger->pushHandler(
            new OtelLogHandler($loggerProvider, Logger::DEBUG));
    } catch (\Throwable $e) {
        // OTel logger not available, continue with stderr only
    }

    return $logger;
};
```

With span scope activation (steps 7 and 9), the OTel Monolog handler
automatically attaches `traceId` and `spanId` to every log record.
No manual trace context injection needed.

## 12. Define application metrics

Create counters with `app.` namespace prefix. Do not add a `.total`
suffix to counter names (the metric type already implies it).
Use attributes for differentiation instead of separate counters:

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

    public static function authLoginFailed(): void
    {
        self::getCounter('app.user.logins', 'User login attempts')
            ->add(1, ['result' => 'failure']);
    }

    public static function articleCreated(): void
    {
        self::getCounter('app.article.creates', 'Articles created')
            ->add(1);
    }
}
```

## 13. Verify

With TelemetryMiddleware + auto-mongodb + TracesOperations, a
typical request produces this span hierarchy:

```text
POST /api/articles        (SERVER  - TelemetryMiddleware)
  +-- article.create      (INTERNAL - your controller)
       +-- mongodb.insert  (CLIENT  - auto-mongodb)
```

Start an OTel Collector locally and point
`OTEL_EXPORTER_OTLP_ENDPOINT` at it, then hit an endpoint:

```bash
curl -X POST http://localhost:8080/api/articles \
  -H "Content-Type: application/json" \
  -d '{"title":"Hello","body":"World"}'
```

Check the collector output for:

- Spans with your service name and proper parent-child nesting
- Logs with `SeverityText: WARN` (not WARNING) and `traceId`/`spanId` correlation
- Metrics with `app.` prefix (e.g. `app.user.logins`, `app.article.creates`)

## What you get for free

With `OTEL_PHP_AUTOLOAD_ENABLED=true`, the OTel SDK
auto-configures TracerProvider, MeterProvider, and LoggerProvider
from environment variables. No PHP SDK setup code needed.

The `opentelemetry-auto-mongodb` package automatically creates
spans for all MongoDB driver operations with semantic convention
attributes. Do not duplicate these in your application code.

Unlike Slim 4, there is no `opentelemetry-auto-slim` for Slim 3.
HTTP spans and metrics must be created manually via middleware.
