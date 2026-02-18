<?php

namespace App\Middleware;

use App\Telemetry\Metrics;
use Psr\Http\Message\ResponseInterface;
use Psr\Http\Message\ServerRequestInterface;

class ApiMetricsMiddleware
{
    public function __invoke(ServerRequestInterface $request, ResponseInterface $response, callable $next): ResponseInterface
    {
        $start = hrtime(true);

        $response = $next($request, $response);

        $durationMs = (hrtime(true) - $start) / 1e6;
        $method = $request->getMethod();
        $path = $request->getUri()->getPath();
        $statusCode = $response->getStatusCode();

        Metrics::apiRequest($method, $path, $statusCode);
        Metrics::apiResponseTime($durationMs, $method, $path);

        return $response;
    }
}
