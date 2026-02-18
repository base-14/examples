<?php

namespace App\Telemetry;

use OpenTelemetry\API\Logs as API;
use OpenTelemetry\Contrib\Logs\Monolog\Handler as OTelHandler;

class OtelLogHandler extends OTelHandler
{
    private const LEVEL_MAP = [
        'DEBUG' => 'DEBUG',
        'INFO' => 'INFO',
        'NOTICE' => 'INFO',
        'WARNING' => 'WARN',
        'ERROR' => 'ERROR',
        'CRITICAL' => 'ERROR',
        'ALERT' => 'ERROR',
        'EMERGENCY' => 'FATAL',
    ];

    protected function write($record): void
    {
        $formatted = $record['formatted'];
        $monologLevel = $record['level_name'];
        $otelLevel = self::LEVEL_MAP[$monologLevel] ?? $monologLevel;

        $logRecord = (new API\LogRecord())
            ->setTimestamp((int) $record['datetime']->format('Uu') * 1000)
            ->setSeverityNumber(API\Severity::fromPsr3($monologLevel))
            ->setSeverityText($otelLevel)
            ->setBody($formatted['message']);

        foreach (['context', 'extra'] as $key) {
            if (isset($formatted[$key]) && count($formatted[$key]) > 0) {
                $logRecord->setAttribute($key, $formatted[$key]);
            }
        }

        $this->getLogger($record['channel'])->emit($logRecord);
    }
}
