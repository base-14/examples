<?php

use App\Controllers\HealthController;
use App\Controllers\MetricsController;
use App\Controllers\AuthController;
use App\Controllers\ArticleController;

// System endpoints
$app->get('/api/health', HealthController::class . ':health');
$app->get('/api/metrics', MetricsController::class . ':metrics');

// Public auth
$app->post('/api/register', AuthController::class . ':register');
$app->post('/api/login', AuthController::class . ':login');

// Public articles
$app->get('/api/articles', ArticleController::class . ':index');
$app->get('/api/articles/{id}', ArticleController::class . ':show');

// Authenticated routes
$app->group('', function () use ($app) {
    $app->get('/api/user', AuthController::class . ':me');
    $app->post('/api/logout', AuthController::class . ':logout');

    $app->post('/api/articles', ArticleController::class . ':create');
    $app->put('/api/articles/{id}', ArticleController::class . ':update');
    $app->delete('/api/articles/{id}', ArticleController::class . ':delete');
    $app->post('/api/articles/{id}/favorite', ArticleController::class . ':favorite');
    $app->delete('/api/articles/{id}/favorite', ArticleController::class . ':unfavorite');
})->add($app->getContainer()['jwtMiddleware']);
