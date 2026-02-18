<?php

use App\Middleware\SecurityHeadersMiddleware;
use App\Middleware\TelemetryMiddleware;

// Slim 3 middleware is LIFO: last added = first executed
$app->add(new SecurityHeadersMiddleware());
$app->add(new TelemetryMiddleware());
