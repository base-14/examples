<?php

use App\Http\Middleware\ApiMetrics;
use App\Http\Middleware\JwtMiddleware;
use App\Http\Middleware\SecurityHeaders;
use Illuminate\Auth\AuthenticationException;
use Illuminate\Database\Eloquent\ModelNotFoundException;
use Illuminate\Foundation\Application;
use Illuminate\Foundation\Configuration\Exceptions;
use Illuminate\Foundation\Configuration\Middleware;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;
use Illuminate\Validation\ValidationException;
use OpenTelemetry\API\Trace\Span;
use OpenTelemetry\API\Trace\StatusCode;
use Symfony\Component\HttpKernel\Exception\HttpException;

return Application::configure(basePath: dirname(__DIR__))
    ->withRouting(
        web: __DIR__.'/../routes/web.php',
        api: __DIR__.'/../routes/api.php',
        commands: __DIR__.'/../routes/console.php',
        health: '/up',
    )
    ->withMiddleware(function (Middleware $middleware): void {
        $middleware->alias([
            'jwt.auth' => JwtMiddleware::class,
        ]);

        $middleware->append(SecurityHeaders::class);

        $middleware->group('api', [
            ApiMetrics::class,
            \Illuminate\Routing\Middleware\SubstituteBindings::class,
        ]);
    })
    ->withExceptions(function (Exceptions $exceptions): void {
        $exceptions->render(function (Throwable $e, Request $request) {
            $span = Span::getCurrent();

            if ($span->getContext()->isValid()) {
                $span->recordException($e);

                $errorType = match (true) {
                    $e instanceof ValidationException => 'validation',
                    $e instanceof AuthenticationException => 'authentication',
                    $e instanceof ModelNotFoundException => 'not_found',
                    $e instanceof HttpException && $e->getStatusCode() === 403 => 'authorization',
                    $e instanceof HttpException && $e->getStatusCode() === 409 => 'conflict',
                    default => 'exception',
                };

                $span->setAttribute('error.type', $errorType);

                $statusCode = match (true) {
                    $e instanceof ValidationException => 400,
                    $e instanceof AuthenticationException => 401,
                    $e instanceof ModelNotFoundException => 404,
                    $e instanceof HttpException => $e->getStatusCode(),
                    default => 500,
                };

                if ($statusCode !== 404) {
                    $span->setStatus(StatusCode::STATUS_ERROR, $e->getMessage());
                }

                $logContext = [
                    'trace_id' => $span->getContext()->getTraceId(),
                    'span_id' => $span->getContext()->getSpanId(),
                    'error_type' => $errorType,
                    'url' => $request->fullUrl(),
                    'method' => $request->method(),
                ];

                if ($statusCode >= 500) {
                    Log::error($e->getMessage(), $logContext);
                } else {
                    Log::warning($e->getMessage(), $logContext);
                }
            }

            if ($request->expectsJson() || $request->is('api/*')) {
                $statusCode = match (true) {
                    $e instanceof ValidationException => 422,
                    $e instanceof AuthenticationException => 401,
                    $e instanceof ModelNotFoundException => 404,
                    $e instanceof HttpException => $e->getStatusCode(),
                    default => 500,
                };

                $response = [
                    'error' => $e instanceof ValidationException
                        ? $e->errors()
                        : ['message' => $e->getMessage()],
                ];

                if (config('app.debug') && $statusCode >= 500) {
                    $response['exception'] = get_class($e);
                    $response['trace'] = $e->getTraceAsString();
                }

                return response()->json($response, $statusCode);
            }

            return null;
        });
    })->create();
