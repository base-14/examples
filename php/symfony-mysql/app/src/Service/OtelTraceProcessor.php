<?php

namespace App\Service;

use Monolog\LogRecord;
use Monolog\Processor\ProcessorInterface;
use OpenTelemetry\API\Trace\Span;

class OtelTraceProcessor implements ProcessorInterface
{
    public function __invoke(LogRecord $record): LogRecord
    {
        $span = Span::getCurrent();
        $context = $span->getContext();

        return $record->with(extra: array_merge($record->extra, [
            'trace_id' => $context->getTraceId(),
            'span_id' => $context->getSpanId(),
            'service.name' => $_ENV['OTEL_SERVICE_NAME'] ?? 'symfony-articles',
        ]));
    }
}
