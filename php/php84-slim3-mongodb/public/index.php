<?php

require __DIR__ . '/../vendor/autoload.php';

$dotenv = Dotenv\Dotenv::createImmutable(__DIR__ . '/..');
$dotenv->safeLoad();

require __DIR__ . '/../src/telemetry.php';

$app = new \Slim\App([
    'settings' => [
        'displayErrorDetails' => true,
        'addContentLengthHeader' => false,
        'determineRouteBeforeAppMiddleware' => true,
    ],
]);

require __DIR__ . '/../src/dependencies.php';
require __DIR__ . '/../src/middleware.php';
require __DIR__ . '/../src/routes.php';

$app->run();
