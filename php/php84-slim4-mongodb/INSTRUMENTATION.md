# Instrumenting PHP 8.4 + Slim 4 with OpenTelemetry

Step-by-step guide to add distributed tracing, metrics, and logs
to a Slim 4 application. No Docker required.

## 1. Install PHP extensions

```bash
pecl install opentelemetry-1.2.1 mongodb-2.2.1
```

Enable them in your `php.ini`:

```ini
extension=opentelemetry
extension=mongodb
```

## 2. Install composer dependencies

```bash
composer require \
  slim/slim:^4.15 \
  slim/psr7:^1.8 \
  php-di/php-di:^7.1 \
  open-telemetry/sdk:^1.13 \
  open-telemetry/exporter-otlp:^1.4 \
  open-telemetry/opentelemetry-auto-slim:^1.3 \
  open-telemetry/opentelemetry-auto-mongodb:^0.2 \
  open-telemetry/opentelemetry-logger-monolog:^1.1 \
  php-http/guzzle7-adapter:^1.1 \
  guzzlehttp/psr7:^2.8
```

The `opentelemetry-auto-slim` package automatically instruments
Slim 4 HTTP requests, creating root SERVER spans with route
pattern names. No manual `TelemetryMiddleware` required.

The `opentelemetry-auto-mongodb` package automatically creates
spans for all MongoDB driver operations. Do not duplicate these
attributes manually in your application code.

## 3. Set environment variables

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

## 4. Bootstrap Slim 4 with PHP-DI

Slim 4 requires a PSR-11 container (we use PHP-DI) and explicit
PSR-7 implementation (`slim/psr7`):

```php
<?php

use DI\ContainerBuilder;
use OpenTelemetry\API\Trace\Span;
use OpenTelemetry\API\Trace\StatusCode;
use Psr\Http\Message\ServerRequestInterface;
use Psr\Log\LoggerInterface;
use Slim\Factory\AppFactory;

require __DIR__ . '/../vendor/autoload.php';

Dotenv\Dotenv::createImmutable(__DIR__ . '/..')->safeLoad();

require __DIR__ . '/../src/telemetry.php';

$builder = new ContainerBuilder();
$builder->addDefinitions(__DIR__ . '/../src/dependencies.php');
$container = $builder->build();

AppFactory::setContainer($container);
$app = AppFactory::create();

$app->addBodyParsingMiddleware();
$app->addRoutingMiddleware();

// Your custom middleware
$app->add(new \App\Middleware\SecurityHeadersMiddleware());

// Routes
require __DIR__ . '/../src/routes.php';

// Error handler with span recording
$displayErrors = ($_ENV['APP_DEBUG'] ?? 'false') === 'true';
$errorMiddleware = $app->addErrorMiddleware($displayErrors, true, true);
$errorMiddleware->setDefaultErrorHandler(function (
    ServerRequestInterface $request,
    \Throwable $exception,
    bool $displayErrorDetails,
    bool $logErrors,
    bool $logErrorDetails,
) use ($app) {
    $span = Span::getCurrent();
    $span->recordException($exception);
    $span->setStatus(StatusCode::STATUS_ERROR, $exception->getMessage());

    $logger = $app->getContainer()->get(LoggerInterface::class);
    $logger->error('Unhandled exception', [
        'exception' => $exception,
        'uri' => (string) $request->getUri(),
        'method' => $request->getMethod(),
    ]);

    $statusCode = 500;
    if ($exception instanceof \Slim\Exception\HttpException) {
        $statusCode = $exception->getCode();
    }

    $response = $app->getResponseFactory()->createResponse($statusCode);
    $response->getBody()->write(json_encode([
        'error' => $displayErrorDetails
            ? $exception->getMessage()
            : 'Internal server error',
    ]));

    return $response->withHeader('Content-Type', 'application/json');
});

$app->run();
```

Key differences from Slim 3:

- `AppFactory::create()` instead of `new \Slim\App()`
- `addBodyParsingMiddleware()` for JSON request body parsing
- `addRoutingMiddleware()` for route resolution
- `addErrorMiddleware()` for error handling
- No `determineRouteBeforeAppMiddleware` setting needed
- Custom error handler records exceptions on the active span

## 5. Register shutdown handlers

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

## 6. HTTP spans are automatic

With `opentelemetry-auto-slim` installed and
`OTEL_PHP_AUTOLOAD_ENABLED=true`, every Slim 4 request
automatically gets a root SERVER span with:

- Span name: `{METHOD} {route_pattern}` (e.g. `GET /api/articles/{id}`)
- Semantic convention attributes (`http.request.method`, `http.route`, `http.response.status_code`)
- HTTP server metrics (request duration, count)

No manual `TelemetryMiddleware` is needed (unlike Slim 3).
Do not create duplicate HTTP metrics or span attributes in your
application code; the auto-instrumentation handles these.

## 7. Write PSR-15 middleware

Slim 4 uses PSR-15 `MiddlewareInterface` instead of Slim 3's
callable middleware:

```php
<?php

namespace App\Middleware;

use Psr\Http\Message\ResponseInterface;
use Psr\Http\Message\ServerRequestInterface;
use Psr\Http\Server\MiddlewareInterface;
use Psr\Http\Server\RequestHandlerInterface;

class SecurityHeadersMiddleware implements MiddlewareInterface
{
    public function process(
        ServerRequestInterface $request,
        RequestHandlerInterface $handler
    ): ResponseInterface {
        $response = $handler->handle($request);

        return $response
            ->withHeader('X-Content-Type-Options', 'nosniff')
            ->withHeader('X-Frame-Options', 'DENY');
    }
}
```

Key differences from Slim 3:

- Implements `MiddlewareInterface` with `process()` method
- Uses `$handler->handle($request)` instead of `$next($request, $response)`
- No `$response` parameter; create `new \Slim\Psr7\Response()` when
  needed (e.g. for 401 errors in JWT middleware)

## 8. Add business logic spans with scope activation

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

Use it in your controllers with constructor-injected logger:

```php
use App\Repositories\ArticleRepository;
use App\Telemetry\Metrics;
use App\Telemetry\TracesOperations;
use Psr\Log\LoggerInterface;

class ArticleController
{
    use TracesOperations;

    private ArticleRepository $articleRepository;
    private LoggerInterface $logger;

    public function __construct(
        ArticleRepository $articleRepository,
        LoggerInterface $logger
    ) {
        $this->articleRepository = $articleRepository;
        $this->logger = $logger;
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
                    return $this->json($response,
                        ['error' => 'Title and body are required'], 422);
                }

                $article = $this->articleRepository->create($data);

                $span->setAttribute('enduser.id', $user['sub']);
                $span->setAttribute('app.article.id', $article['id']);

                Metrics::articleCreated();
                $this->logger->info('Article created',
                    ['article.id' => $article['id'],
                     'user.id' => $user['sub']]);

                $response->getBody()->write(json_encode([
                    'article' => $article,
                ]));
                return $response
                    ->withHeader('Content-Type', 'application/json')
                    ->withStatus(201);
            }
        );
    }
}
```

Note: Slim 4 does not have `$response->withJson()`. Write JSON
to the response body manually and set the Content-Type header.

## 9. Map log severity to OTel conventions

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

## 10. Wire up the logger

Register both handlers in your DI container:

```php
use App\Telemetry\OtelLevelFormatter;
use App\Telemetry\OtelLogHandler;
use Monolog\Handler\StreamHandler;
use Monolog\Logger;
use OpenTelemetry\API\Globals;
use Psr\Log\LoggerInterface;

return [
    LoggerInterface::class => function () {
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
    },
];
```

With span scope activation (step 8), the OTel Monolog handler
automatically attaches `traceId` and `spanId` to every log record.
No manual trace context injection needed.

## 11. Define application metrics

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

## 12. Verify

With auto-slim + auto-mongodb + TracesOperations, a typical
request produces this span hierarchy:

```text
POST /api/articles        (SERVER  - auto-slim)
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

The `opentelemetry-auto-slim` package automatically creates root
SERVER spans for every Slim 4 request with route pattern names
(low cardinality, e.g. `/api/articles/{id}` not `/api/articles/abc123`)
and HTTP server metrics.

The `opentelemetry-auto-mongodb` package automatically creates
spans for all MongoDB driver operations with semantic convention
attributes. Do not duplicate these in your application code.
