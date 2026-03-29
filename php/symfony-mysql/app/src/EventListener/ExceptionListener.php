<?php

namespace App\EventListener;

use Psr\Log\LoggerInterface;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpKernel\Event\ExceptionEvent;
use Symfony\Component\HttpKernel\Exception\HttpExceptionInterface;

class ExceptionListener
{
    public function __construct(private readonly LoggerInterface $logger) {}

    public function onKernelException(ExceptionEvent $event): void
    {
        $exception = $event->getThrowable();

        $statusCode = $exception instanceof HttpExceptionInterface
            ? $exception->getStatusCode()
            : 500;

        if ($statusCode >= 500) {
            $this->logger->error('Unhandled exception', [
                'exception' => $exception->getMessage(),
                'code' => $statusCode,
            ]);
        }

        $span = \OpenTelemetry\API\Trace\Span::getCurrent();
        $traceId = $span->getContext()->getTraceId();

        $response = new JsonResponse([
            'error' => [
                'code' => $statusCode >= 500 ? 'INTERNAL_ERROR' : 'ERROR',
                'message' => $statusCode >= 500 ? 'Internal server error' : $exception->getMessage(),
            ],
            'meta' => ['trace_id' => $traceId],
        ], $statusCode);

        $event->setResponse($response);
    }
}
