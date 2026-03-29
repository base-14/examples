<?php

require_once __DIR__ . '/../vendor/autoload.php';

use OpenTelemetry\API\Globals;
use OpenTelemetry\API\Trace\SpanKind;
use OpenTelemetry\API\Trace\StatusCode;

$method = $_SERVER['REQUEST_METHOD'];
$path = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);

header('Content-Type: application/json');

if ($method === 'POST' && $path === '/notify') {
    $propagator = Globals::propagator();
    $tracer = Globals::tracerProvider()->getTracer('symfony-notify');

    $headers = [];
    foreach ($_SERVER as $key => $value) {
        if (str_starts_with($key, 'HTTP_')) {
            $headerName = strtolower(str_replace('_', '-', substr($key, 5)));
            $headers[$headerName] = $value;
        }
    }

    $parentContext = $propagator->extract($headers);

    $span = $tracer->spanBuilder('POST /notify')
        ->setParent($parentContext)
        ->setSpanKind(SpanKind::KIND_SERVER)
        ->startSpan();

    $scope = $span->activate();

    $body = file_get_contents('php://input');
    $payload = json_decode($body, true);

    $traceId = $span->getContext()->getTraceId();
    $spanId = $span->getContext()->getSpanId();

    $log = json_encode([
        'level' => 'INFO',
        'message' => 'Notification received',
        'trace_id' => $traceId,
        'span_id' => $spanId,
        'article_id' => $payload['id'] ?? null,
        'article_title' => $payload['title'] ?? null,
        'service.name' => 'symfony-notify',
    ]);
    file_put_contents('php://stderr', $log . "\n");

    $span->setAttribute('article.id', $payload['id'] ?? 0);
    $span->setStatus(StatusCode::STATUS_OK);

    echo json_encode([
        'data' => ['status' => 'notified'],
        'meta' => ['trace_id' => $traceId],
    ]);

    $scope->detach();
    $span->end();
} elseif ($method === 'GET' && ($path === '/notify' || $path === '/health' || $path === '/')) {
    echo json_encode(['data' => ['status' => 'ok']]);
} else {
    http_response_code(404);
    echo json_encode(['error' => ['code' => 'NOT_FOUND', 'message' => 'Not found']]);
}
