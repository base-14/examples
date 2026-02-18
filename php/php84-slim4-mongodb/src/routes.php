<?php

use App\Controllers\ArticleController;
use App\Controllers\AuthController;
use App\Controllers\HealthController;
use App\Controllers\MetricsController;
use App\Middleware\JwtMiddleware;
use Slim\Routing\RouteCollectorProxy;

$app->get('/api/health', [HealthController::class, 'health']);
$app->get('/api/metrics', [MetricsController::class, 'metrics']);

$app->post('/api/register', [AuthController::class, 'register']);
$app->post('/api/login', [AuthController::class, 'login']);

$app->get('/api/articles', [ArticleController::class, 'index']);
$app->get('/api/articles/{id}', [ArticleController::class, 'show']);

$app->group('', function (RouteCollectorProxy $group) {
    $group->get('/api/user', [AuthController::class, 'me']);
    $group->post('/api/logout', [AuthController::class, 'logout']);

    $group->post('/api/articles', [ArticleController::class, 'create']);
    $group->put('/api/articles/{id}', [ArticleController::class, 'update']);
    $group->delete('/api/articles/{id}', [ArticleController::class, 'delete']);
    $group->post('/api/articles/{id}/favorite', [ArticleController::class, 'favorite']);
    $group->delete('/api/articles/{id}/favorite', [ArticleController::class, 'unfavorite']);
})->add($app->getContainer()->get(JwtMiddleware::class));
