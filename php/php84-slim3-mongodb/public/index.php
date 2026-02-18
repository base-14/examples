<?php

use OpenTelemetry\API\Trace\Span;
use OpenTelemetry\API\Trace\StatusCode;

require __DIR__ . '/../vendor/autoload.php';

$dotenv = Dotenv\Dotenv::createImmutable(__DIR__ . '/..');
$dotenv->safeLoad();

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
        $statusCode = method_exists($exception, 'getCode') && $exception->getCode() >= 400 && $exception->getCode() < 600
            ? $exception->getCode()
            : 500;

        return $response
            ->withJson([
                'error' => $displayErrors ? $exception->getMessage() : 'Internal server error',
            ], $statusCode);
    };
};

$app->run();
