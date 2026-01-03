<?php

namespace App\Concerns;

use OpenTelemetry\API\Globals;
use OpenTelemetry\API\Trace\Span;
use OpenTelemetry\API\Trace\SpanContext;
use OpenTelemetry\API\Trace\SpanInterface;
use OpenTelemetry\API\Trace\SpanKind;
use OpenTelemetry\API\Trace\StatusCode;
use OpenTelemetry\API\Trace\TracerInterface;
use OpenTelemetry\Context\Context;

trait TracesOperations
{
    protected function getTracer(string $name = 'laravel-app'): TracerInterface
    {
        return Globals::tracerProvider()->getTracer($name);
    }

    protected function withLinkedSpan(
        string $name,
        callable $callback,
        ?string $parentTraceId = null,
        ?string $parentSpanId = null,
        int $traceFlags = 0,
        array $attributes = [],
        int $spanKind = SpanKind::KIND_CONSUMER,
        string $tracerName = 'laravel-worker'
    ): mixed {
        $tracer = $this->getTracer($tracerName);
        $spanBuilder = $tracer->spanBuilder($name)->setSpanKind($spanKind);

        if ($parentTraceId && $parentSpanId) {
            $parentContext = SpanContext::createFromRemoteParent(
                $parentTraceId,
                $parentSpanId,
                $traceFlags
            );

            if ($parentContext->isValid()) {
                $spanBuilder->addLink($parentContext, [
                    'link.type' => 'parent_job',
                ]);

                $spanBuilder->setParent(
                    Context::getCurrent()->withContextValue(
                        Span::wrap($parentContext)
                    )
                );
            }
        }

        $span = $spanBuilder->startSpan();
        $scope = $span->activate();

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
            $scope->detach();
            $span->end();
        }
    }

    protected function withSpan(
        string $name,
        callable $callback,
        array $attributes = [],
        int $spanKind = SpanKind::KIND_INTERNAL,
        string $tracerName = 'laravel-app'
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
