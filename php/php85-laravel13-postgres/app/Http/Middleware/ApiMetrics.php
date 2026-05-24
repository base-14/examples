<?php

namespace App\Http\Middleware;

use App\Telemetry\Metrics;
use Closure;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

class ApiMetrics
{
    public function handle(Request $request, Closure $next): Response
    {
        $startTime = microtime(true);

        $response = $next($request);

        $durationMs = (microtime(true) - $startTime) * 1000;
        $method = $request->method();
        $route = $request->route()?->uri() ?? $request->path();
        $statusCode = $response->getStatusCode();

        Metrics::apiRequest($method, $route, $statusCode);
        Metrics::apiResponseTime($durationMs, $method, $route);

        return $response;
    }
}
