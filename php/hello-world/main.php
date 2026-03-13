<?php
// PHP Hello World — OpenTelemetry

require __DIR__ . '/vendor/autoload.php';

use OpenTelemetry\API\Logs\Severity;
use OpenTelemetry\API\Trace\StatusCode;
use OpenTelemetry\API\Trace\TracerInterface;
use OpenTelemetry\Contrib\Otlp\LogsExporter;
use OpenTelemetry\Contrib\Otlp\MetricExporter;
use OpenTelemetry\Contrib\Otlp\SpanExporter;
use OpenTelemetry\SDK\Common\Attribute\Attributes as SdkAttributes;
use OpenTelemetry\SDK\Common\Time\ClockFactory;
use OpenTelemetry\SDK\Logs\LoggerProvider;
use OpenTelemetry\SDK\Logs\Processor\BatchLogRecordProcessor;
use OpenTelemetry\SDK\Metrics\MeterProvider;
use OpenTelemetry\SDK\Metrics\MetricReader\ExportingReader;
use OpenTelemetry\SDK\Resource\ResourceInfo;
use OpenTelemetry\SDK\Resource\ResourceInfoFactory;
use OpenTelemetry\SDK\Trace\SpanProcessor\BatchSpanProcessor;
use OpenTelemetry\SDK\Trace\TracerProvider;
use OpenTelemetry\SemConv\ResourceAttributes;

// -- Configuration ----------------------------------------------------------
// The collector endpoint. Set this to where your OTel collector accepts
// OTLP/HTTP traffic (default port 4318).
$endpoint = getenv('OTEL_EXPORTER_OTLP_ENDPOINT');
if (!$endpoint) {
    fwrite(STDERR, "Set OTEL_EXPORTER_OTLP_ENDPOINT (e.g. http://localhost:4318)\n");
    exit(1);
}

// A Resource identifies your application in the telemetry backend.
// Every span, log, and metric carries this identity.
$resource = ResourceInfoFactory::defaultResource()->merge(
    ResourceInfo::create(SdkAttributes::create([
        ResourceAttributes::SERVICE_NAME => 'hello-world-php',
        'process.runtime.name' => 'php',
        'process.runtime.version' => PHP_VERSION,
        'process.pid' => getmypid(),
        'os.type' => PHP_OS_FAMILY,
        'os.version' => php_uname('r'),
        'host.arch' => php_uname('m'),
    ]))
);

// -- Traces -----------------------------------------------------------------
// A TracerProvider manages the lifecycle of traces. It batches spans and
// sends them to the collector via the OTLP/HTTP exporter.
$transportFactory = \OpenTelemetry\SDK\Common\Export\Http\PsrTransportFactory::discover();
$spanExporter = new SpanExporter($transportFactory->create($endpoint . '/v1/traces', 'application/json'));
$tracerProvider = TracerProvider::builder()
    ->setResource($resource)
    ->addSpanProcessor(new BatchSpanProcessor($spanExporter, ClockFactory::getDefault()))
    ->build();
$tracer = $tracerProvider->getTracer('hello-world-php');

// -- Logs -------------------------------------------------------------------
// A LoggerProvider sends structured logs to the collector. Logs emitted
// inside a span automatically carry the span's trace ID and span ID —
// this is called log-trace correlation.
$logExporter = new LogsExporter($transportFactory->create($endpoint . '/v1/logs', 'application/json'));
$loggerProvider = LoggerProvider::builder()
    ->setResource($resource)
    ->addLogRecordProcessor(new BatchLogRecordProcessor($logExporter, ClockFactory::getDefault()))
    ->build();
$logger = $loggerProvider->getLogger('hello-world-php');

// -- Metrics ----------------------------------------------------------------
// A MeterProvider manages metrics. The ExportingReader collects and exports
// metric data.
$metricExporter = new MetricExporter($transportFactory->create($endpoint . '/v1/metrics', 'application/json'));
$metricReader = new ExportingReader($metricExporter);
$meterProvider = MeterProvider::builder()
    ->setResource($resource)
    ->addReader($metricReader)
    ->build();
$meter = $meterProvider->getMeter('hello-world-php');

// A counter tracks how many times something happens.
$helloCounter = $meter->createCounter('hello.count', description: 'Number of times the hello-world app has run');

// -- Application Logic ------------------------------------------------------

// A normal operation — creates a span with an info log.
function sayHello(TracerInterface $tracer, $logger, $counter): void {
    // A span represents a unit of work.
    $span = $tracer->spanBuilder('say-hello')->startSpan();
    $scope = $span->activate();
    try {
        // This log is emitted inside the span, so it carries the span's trace ID.
        // In Scout, you can jump to the trace from a log detail.
        $logger->emit(
            (new \OpenTelemetry\API\Logs\LogRecord())
                ->setSeverityNumber(Severity::INFO)
                ->setSeverityText('INFO')
                ->setBody('Hello, World!')
        );
        $counter->add(1);
        $span->setAttribute('greeting', 'Hello, World!');
    } finally {
        $scope->detach();
        $span->end();
    }
}

// A degraded operation — creates a span with a warning log.
function checkDiskSpace(TracerInterface $tracer, $logger): void {
    $span = $tracer->spanBuilder('check-disk-space')->startSpan();
    $scope = $span->activate();
    try {
        // Warnings show up in Scout with a distinct severity level, making
        // them easy to filter and spot before they become errors.
        $logger->emit(
            (new \OpenTelemetry\API\Logs\LogRecord())
                ->setSeverityNumber(Severity::WARN)
                ->setSeverityText('WARN')
                ->setBody('Disk usage above 90%')
        );
        $span->setAttribute('disk.usage_percent', 92);
    } finally {
        $scope->detach();
        $span->end();
    }
}

// A failed operation — creates a span with an error and exception.
function parseConfig(TracerInterface $tracer, $logger): void {
    $span = $tracer->spanBuilder('parse-config')->startSpan();
    $scope = $span->activate();
    try {
        $error = new \RuntimeException("invalid config: missing 'database_url'");
        // recordException attaches the stack trace to the span.
        // setStatus marks the span as errored so it stands out in TraceX.
        $span->recordException($error);
        $span->setStatus(StatusCode::STATUS_ERROR, $error->getMessage());
        $logger->emit(
            (new \OpenTelemetry\API\Logs\LogRecord())
                ->setSeverityNumber(Severity::ERROR)
                ->setSeverityText('ERROR')
                ->setBody('Failed to parse configuration: ' . $error->getMessage())
        );
    } finally {
        $scope->detach();
        $span->end();
    }
}

// -- Run --------------------------------------------------------------------

sayHello($tracer, $logger, $helloCounter);
checkDiskSpace($tracer, $logger);
parseConfig($tracer, $logger);

// -- Shutdown ---------------------------------------------------------------
// Flush all buffered telemetry to the collector before exiting.
// Without this, the last batch of spans/logs/metrics may be lost.
$tracerProvider->shutdown();
$loggerProvider->shutdown();
$meterProvider->shutdown();

echo "Done. Check Scout for your trace, log, and metric.\n";
