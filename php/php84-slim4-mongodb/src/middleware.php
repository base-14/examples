<?php

use App\Middleware\SecurityHeadersMiddleware;

$app->add(new SecurityHeadersMiddleware());
