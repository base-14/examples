<?php

namespace App\Telemetry;

use Monolog\Formatter\LineFormatter;
use Monolog\LogRecord;

class OtelLevelFormatter extends LineFormatter
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

    public function format(LogRecord $record): string
    {
        $output = parent::format($record);
        $monologLevel = $record->level->getName();
        $otelLevel = self::LEVEL_MAP[$monologLevel] ?? $monologLevel;

        if ($monologLevel !== $otelLevel) {
            $output = str_replace($monologLevel, $otelLevel, $output);
        }

        return $output;
    }
}
