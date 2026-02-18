# Instrumenting PHP 8.4 + Slim 4 with OpenTelemetry

Step-by-step guide to add distributed tracing, metrics, and logs
to a Slim 4 application. No Docker required.

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
to hook into PHP's internals. Without it, the SDK packages have
nothing to work with.

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

What each package does:

- **sdk** — Core OTel PHP SDK (creates spans, manages context)
- **exporter-otlp** — Sends telemetry over OTLP protocol
- **opentelemetry-auto-slim** — Auto-instruments every Slim route
  (creates spans for each HTTP request with zero application code)
- **opentelemetry-auto-mongodb** — Auto-creates spans for all
  MongoDB driver operations
- **opentelemetry-logger-monolog** — Bridges Monolog to OTel logs,
  automatically attaches `traceId` and `spanId` for correlation
- **guzzle7-adapter + psr7** — HTTP transport for the OTLP exporter

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

`OTEL_PHP_AUTOLOAD_ENABLED=true` is the key switch. It tells the
SDK to automatically discover and activate the auto-instrumentation
packages. Without it, the packages sit idle.

Use `deployment.environment.name` (not the deprecated `deployment.environment`).

## 4. Bootstrap Slim 4 with exception recording

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

$app->add(new \App\Middleware\SecurityHeadersMiddleware());

require __DIR__ . '/../src/routes.php';

$displayErrors = ($_ENV['APP_DEBUG'] ?? 'false') === 'true';
$errorMiddleware = $app->addErrorMiddleware($displayErrors, true, true);
$errorMiddleware->setDefaultErrorHandler(function (
    ServerRequestInterface $request,
    \Throwable $exception,
    bool $displayErrorDetails,
    bool $logErrors,
    bool $logErrorDetails,
) use ($app) {
    // Record exception on the auto-instrumented span
    $span = Span::getCurrent();
    $span->recordException($exception);
    $span->setStatus(StatusCode::STATUS_ERROR, $exception->getMessage());

    // Log with trace correlation (traceId/spanId attached automatically)
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

The three lines that record exceptions on spans are the only OTel
API calls in the entire entry point. `Span::getCurrent()` retrieves
the auto-instrumented span — no manual span creation needed.

## 5. Register shutdown handlers

Create `src/Telemetry/Shutdown.php` to flush telemetry on
process exit. This is important for php-fpm workers that can
exit before the SDK flushes its buffer:

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

Bootstrap it from `src/telemetry.php`:

```php
<?php
use App\Telemetry\Shutdown;
Shutdown::register();
```

## 6. Wire up the logger with OTel correlation

Register Monolog with both a stderr handler and the stock OTel
log handler. The OTel handler automatically attaches `traceId` and
`spanId` to every log record — no manual trace context injection:

```php
use Monolog\Handler\StreamHandler;
use Monolog\Logger;
use OpenTelemetry\API\Globals;
use OpenTelemetry\Contrib\Logs\Monolog\Handler as OtelLogHandler;
use Psr\Log\LoggerInterface;

return [
    LoggerInterface::class => function () {
        $logger = new Logger('slim-app');
        $logger->pushHandler(new StreamHandler('php://stderr', Logger::DEBUG));

        try {
            $loggerProvider = Globals::loggerProvider();
            $logger->pushHandler(new OtelLogHandler($loggerProvider, Logger::DEBUG));
        } catch (\Throwable $e) {
            // OTel logger not available, continue with stderr only
        }

        return $logger;
    },
];
```

## 7. Add business metrics

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

Call these from your controllers as simple one-liners:

```php
Metrics::authLoginSuccess();
Metrics::articleCreated();
```

No span wrapping, no trace context management. The counters flow
through the `OTEL_METRICS_EXPORTER=otlp` pipeline independently.

## 8. HTTP spans are automatic

With `opentelemetry-auto-slim` installed and
`OTEL_PHP_AUTOLOAD_ENABLED=true`, every Slim 4 request
automatically gets:

- Root SERVER span named `{METHOD} {route_pattern}` (e.g. `GET /api/articles/{id}`)
- Controller-level INTERNAL span (e.g. `ArticleController::create`)
- Semantic convention attributes (`http.request.method`, `http.route`, `http.response.status_code`)
- HTTP server metrics (request duration, count)

No manual `TelemetryMiddleware` is needed (unlike Slim 3).
Do not create duplicate HTTP metrics or span attributes in your
application code.

## 9. MongoDB spans are automatic

With `opentelemetry-auto-mongodb`, every MongoDB driver operation
gets a CLIENT span with:

- Span name: `MongoDB {collection}.{operation}` (e.g. `MongoDB articles.insert`)
- Semantic convention attributes (`db.system.name`, `db.namespace`, `db.operation.name`, `db.query.text`)

These nest as children of the auto-instrumented controller span.
Do not duplicate these attributes in your application code.

## 10. Write clean controllers

With auto-instrumentation handling traces, your controllers stay
focused on business logic. The only OTel touchpoint is the
`Metrics::*` one-liner calls:

```php
use App\Repositories\ArticleRepository;
use App\Telemetry\Metrics;
use Psr\Log\LoggerInterface;

class ArticleController
{
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
        $data = $request->getParsedBody();
        $user = $request->getAttribute('user');

        if (empty($data['title']) || empty($data['body'])) {
            $this->logger->warning('Article validation failed',
                ['reason' => 'missing fields']);
            return $this->json($response,
                ['error' => 'Title and body are required'], 422);
        }

        $data['author_id'] = $user['sub'];
        $article = $this->articleRepository->create($data);
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
}
```

The logger calls produce OTel log records with trace correlation.
The `Metrics::articleCreated()` call increments a counter. Neither
requires any span or context management.

## 11. Verify

A typical request produces this span hierarchy, all from
auto-instrumentation:

```text
POST /api/articles              (SERVER   - auto-slim)
  +-- ArticleController::create (INTERNAL - auto-slim)
       +-- MongoDB articles.insert (CLIENT - auto-mongodb)
```

Start an OTel Collector locally and point
`OTEL_EXPORTER_OTLP_ENDPOINT` at it, then hit an endpoint:

```bash
curl -X POST http://localhost:8080/api/articles \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"Hello","body":"World"}'
```

Check the collector output for:

- Spans with your service name and proper parent-child nesting
- Logs with `traceId`/`spanId` correlation
- Metrics with `app.` prefix (e.g. `app.user.logins`, `app.article.creates`)

## What you get for free

With `OTEL_PHP_AUTOLOAD_ENABLED=true`, the OTel SDK
auto-configures TracerProvider, MeterProvider, and LoggerProvider
from environment variables. No PHP SDK setup code needed.

The only manual code in this example:

1. **3 lines** in the error handler to record exceptions on spans
2. **Stock OTel Monolog handler** for log-trace correlation
3. **Metrics class** with static counter methods for business metrics
4. **Shutdown handler** to flush telemetry in php-fpm

Everything else — HTTP spans, controller spans, MongoDB spans,
semantic convention attributes — is fully automatic.
