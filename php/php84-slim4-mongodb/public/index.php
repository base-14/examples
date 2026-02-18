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

require __DIR__ . '/../src/middleware.php';
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
        'error' => $displayErrorDetails ? $exception->getMessage() : 'Internal server error',
    ]));

    return $response->withHeader('Content-Type', 'application/json');
});

$app->run();
