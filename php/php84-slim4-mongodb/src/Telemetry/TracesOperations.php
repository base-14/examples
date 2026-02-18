<?php

namespace App\Telemetry;

use OpenTelemetry\API\Globals;
use OpenTelemetry\API\Trace\SpanKind;
use OpenTelemetry\API\Trace\StatusCode;
use OpenTelemetry\API\Trace\TracerInterface;
use OpenTelemetry\Context\ScopeInterface;

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
        $scope = $span->activate();

        foreach ($attributes as $key => $value) {
            $span->setAttribute($key, $value);
        }

        try {
            return $callback($span);
        } catch (\Exception $e) {
            $span->recordException($e);
            $span->setStatus(StatusCode::STATUS_ERROR, $e->getMessage());
            throw $e;
        } finally {
            $scope->detach();
            $span->end();
        }
    }
}
