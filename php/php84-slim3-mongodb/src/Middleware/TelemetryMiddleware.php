<?php

namespace App\Middleware;

use OpenTelemetry\API\Globals;
use OpenTelemetry\API\Trace\SpanKind;
use OpenTelemetry\API\Trace\StatusCode;
use Psr\Http\Message\ResponseInterface;
use Psr\Http\Message\ServerRequestInterface;

class TelemetryMiddleware
{
    public function __invoke(ServerRequestInterface $request, ResponseInterface $response, callable $next): ResponseInterface
    {
        $tracer = Globals::tracerProvider()->getTracer('slim-app');
        $method = $request->getMethod();
        $path = (string) $request->getUri()->getPath();

        $span = $tracer->spanBuilder("$method $path")
            ->setSpanKind(SpanKind::KIND_SERVER)
            ->startSpan();

        $scope = $span->activate();

        $span->setAttribute('http.method', $method);
        $span->setAttribute('http.url', (string) $request->getUri());
        $span->setAttribute('http.target', $path);
        $span->setAttribute('http.scheme', $request->getUri()->getScheme() ?: 'http');

        try {
            $response = $next($request, $response);

            $route = $request->getAttribute('route');
            if ($route instanceof \Slim\Route) {
                $pattern = $route->getPattern();
                $span->updateName("$method $pattern");
                $span->setAttribute('http.route', $pattern);
            }

            $statusCode = $response->getStatusCode();
            $span->setAttribute('http.status_code', $statusCode);

            if ($statusCode >= 400) {
                $span->setStatus(StatusCode::STATUS_ERROR, "HTTP $statusCode");
            } else {
                $span->setStatus(StatusCode::STATUS_OK);
            }

            return $response;
        } catch (\Exception $e) {
            $span->recordException($e);
            $span->setAttribute('error.type', get_class($e));
            $span->setStatus(StatusCode::STATUS_ERROR, $e->getMessage());
            throw $e;
        } finally {
            $scope->detach();
            $span->end();
        }
    }
}
