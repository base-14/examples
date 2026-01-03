<?php

namespace App\Logging;

use Monolog\Logger;
use OpenTelemetry\API\Globals;
use OpenTelemetry\Contrib\Logs\Monolog\Handler as OtelHandler;
use Psr\Log\LogLevel;

class OtlpLogger
{
    public function __invoke(array $config): Logger
    {
        $loggerProvider = Globals::loggerProvider();
        $level = $config['level'] ?? LogLevel::WARNING;

        $handler = new OtelHandler($loggerProvider, $level);

        return new Logger('otlp', [$handler]);
    }
}
