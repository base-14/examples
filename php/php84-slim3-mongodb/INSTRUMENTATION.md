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
  open-telemetry/sdk:1.13.0 \
  open-telemetry/exporter-otlp:1.4.0 \
  open-telemetry/opentelemetry-auto-mongodb:0.2.0 \
  open-telemetry/opentelemetry-logger-monolog:1.1.0 \
  php-http/guzzle7-adapter:1.1.0 \
  guzzlehttp/psr7:2.8.0
```

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
```

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

Call it early in your bootstrap, before `$app->run()`:

```php
require __DIR__ . '/../vendor/autoload.php';

\App\Telemetry\Shutdown::register();

$app = new \Slim\App([
    'settings' => [
        'determineRouteBeforeAppMiddleware' => true,
    ],
]);
```

The `determineRouteBeforeAppMiddleware` setting is required so
the middleware can read the matched route pattern for span names.

## 6. Add HTTP tracing middleware

Create `src/Middleware/TelemetryMiddleware.php`. This creates a
root span for every request with low-cardinality route names:

```php
<?php

namespace App\Middleware;

use OpenTelemetry\API\Globals;
use OpenTelemetry\API\Trace\SpanKind;
use OpenTelemetry\API\Trace\StatusCode;
use Psr\Http\Message\ResponseInterface;
use Psr\Http\Message\ServerRequestInterface;

class TelemetryMiddleware
{
    public function __invoke(
        ServerRequestInterface $request,
        ResponseInterface $response,
        callable $next
    ): ResponseInterface {
        $tracer = Globals::tracerProvider()->getTracer('slim-app');
        $method = $request->getMethod();
        $path = $request->getUri()->getPath();

        $span = $tracer->spanBuilder("$method $path")
            ->setSpanKind(SpanKind::KIND_SERVER)
            ->startSpan();
        $scope = $span->activate();

        $span->setAttribute('http.method', $method);
        $span->setAttribute('http.target', $path);

        try {
            $response = $next($request, $response);

            // Update span name to route pattern (requires
            // determineRouteBeforeAppMiddleware = true)
            $route = $request->getAttribute('route');
            if ($route instanceof \Slim\Route) {
                $pattern = $route->getPattern();
                $span->updateName("$method $pattern");
                $span->setAttribute('http.route', $pattern);
            }

            $span->setAttribute(
                'http.status_code',
                $response->getStatusCode()
            );
            $span->setStatus(StatusCode::STATUS_OK);

            return $response;
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

Register it as application middleware:

```php
$app->add(new \App\Middleware\TelemetryMiddleware());
```

## 7. Add business logic spans

Create a `TracesOperations` trait to wrap any operation in a
child span:

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
        array $attributes = []
    ): mixed {
        $span = Globals::tracerProvider()
            ->getTracer('slim-app')
            ->spanBuilder($name)
            ->setSpanKind(SpanKind::KIND_INTERNAL)
            ->startSpan();

        foreach ($attributes as $k => $v) {
            $span->setAttribute($k, $v);
        }

        try {
            $result = $callback($span);
            $span->setStatus(StatusCode::STATUS_OK);
            return $result;
        } catch (\Exception $e) {
            $span->recordException($e);
            $span->setStatus(
                StatusCode::STATUS_ERROR,
                $e->getMessage()
            );
            throw $e;
        } finally {
            $span->end();
        }
    }
}
```

Use it in your controllers:

```php
use App\Telemetry\TracesOperations;

class ArticleController
{
    use TracesOperations;

    public function create($request, $response)
    {
        return $this->withSpan(
            'article.create',
            function ($span) use ($request, $response) {
                $data = $request->getParsedBody();
                // ... your logic ...
                $span->setAttribute('article.id', $id);
                return $response->withJson(['article' => $article], 201);
            },
            ['db.operation' => 'insertOne']
        );
    }
}
```

## 8. Verify

MongoDB operations are auto-instrumented by
`opentelemetry-auto-mongodb`. Combined with steps 6 and 7,
a typical request produces this span hierarchy:

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

Check the collector output for spans with your service name.

## What you get for free

With `OTEL_PHP_AUTOLOAD_ENABLED=true`, the OTel SDK
auto-configures TracerProvider, MeterProvider, and LoggerProvider
from environment variables. No PHP SDK setup code needed.

The `opentelemetry-auto-mongodb` package automatically creates
spans for all MongoDB driver operations with `db.system`,
`db.name`, `db.mongodb.collection`, and `db.operation` attributes.
