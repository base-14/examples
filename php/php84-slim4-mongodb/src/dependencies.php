<?php

use App\Controllers\AuthController;
use App\Middleware\JwtMiddleware;
use App\Repositories\ArticleRepository;
use App\Repositories\UserRepository;
use App\Telemetry\OtelLevelFormatter;
use Monolog\Handler\StreamHandler;
use Monolog\Logger;
use MongoDB\Client;
use MongoDB\Database;
use OpenTelemetry\API\Globals;
use App\Telemetry\OtelLogHandler;
use Psr\Container\ContainerInterface;
use Psr\Log\LoggerInterface;

return [
    LoggerInterface::class => function () {
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
    },

    Client::class => function () {
        $uri = $_ENV['MONGO_URI'] ?? 'mongodb://mongo:27017';
        return new Client($uri);
    },

    Database::class => function (ContainerInterface $c) {
        $database = $_ENV['MONGO_DATABASE'] ?? 'slim_app';
        return $c->get(Client::class)->selectDatabase($database);
    },

    UserRepository::class => DI\autowire(),

    ArticleRepository::class => DI\autowire(),

    'jwt_secret' => function () {
        $secret = $_ENV['JWT_SECRET'] ?? null;
        if ($secret === null || $secret === '') {
            throw new \RuntimeException('JWT_SECRET environment variable is required');
        }
        return $secret;
    },

    JwtMiddleware::class => DI\autowire()
        ->constructorParameter('jwt_secret', DI\get('jwt_secret')),

    AuthController::class => DI\autowire()
        ->constructorParameter('jwt_secret', DI\get('jwt_secret')),
];
