<?php

use App\Middleware\JwtMiddleware;
use App\Telemetry\OtelLevelFormatter;
use App\Telemetry\OtelLogHandler;
use Monolog\Handler\StreamHandler;
use Monolog\Logger;
use OpenTelemetry\API\Globals;

$container = $app->getContainer();

$container['logger'] = function () {
    $logger = new Logger('slim-app');
    $stderrHandler = new StreamHandler('php://stderr', Logger::DEBUG);
    $stderrHandler->setFormatter(new OtelLevelFormatter());
    $logger->pushHandler($stderrHandler);

    try {
        $loggerProvider = Globals::loggerProvider();
        $logger->pushHandler(new OtelLogHandler($loggerProvider, Logger::DEBUG));
    } catch (\Throwable $e) {
        // OTel logger not available, continue with stderr only
    }

    return $logger;
};

$container['mongo'] = function () {
    $uri = $_ENV['MONGO_URI'] ?? 'mongodb://mongo:27017';
    return new MongoDB\Client($uri);
};

$container['db'] = function ($c) {
    $database = $_ENV['MONGO_DATABASE'] ?? 'slim_app';
    return $c['mongo']->selectDatabase($database);
};

$container['userRepository'] = function ($c) {
    return new App\Repositories\UserRepository($c['db']);
};

$container['articleRepository'] = function ($c) {
    return new App\Repositories\ArticleRepository($c['db']);
};

$container['jwt_secret'] = function () {
    $secret = $_ENV['JWT_SECRET'] ?? null;
    if ($secret === null || $secret === '') {
        throw new \RuntimeException('JWT_SECRET environment variable is required');
    }
    return $secret;
};

$container['jwtMiddleware'] = function ($c) {
    return new JwtMiddleware($c['logger'], $c['jwt_secret']);
};
