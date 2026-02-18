<?php

namespace App\Telemetry;

use OpenTelemetry\API\Globals;
use OpenTelemetry\API\Trace\SpanKind;
use OpenTelemetry\API\Trace\StatusCode;
use OpenTelemetry\API\Trace\TracerInterface;

trait TracesOperations
{
    protected function getTracer(string $name = 'slim-app'): TracerInterface
    {
        return Globals::tracerProvider()->getTracer($name);
    }

    protected function withSpan(
        string $name,
        callable $callback,
        array $attributes = [],
        int $spanKind = SpanKind::KIND_INTERNAL,
        string $tracerName = 'slim-app'
    ): mixed {
        $tracer = $this->getTracer($tracerName);
        $span = $tracer->spanBuilder($name)
            ->setSpanKind($spanKind)
            ->startSpan();

        foreach ($attributes as $key => $value) {
            $span->setAttribute($key, $value);
        }

        try {
            $result = $callback($span);
            $span->setStatus(StatusCode::STATUS_OK);

            return $result;
        } catch (\Exception $e) {
            $span->recordException($e);
            $span->setStatus(StatusCode::STATUS_ERROR, $e->getMessage());
            throw $e;
        } finally {
            $span->end();
        }
    }
}
