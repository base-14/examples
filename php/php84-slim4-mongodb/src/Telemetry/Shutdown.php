<?php

namespace App\Telemetry;

use OpenTelemetry\API\Globals;

class Shutdown
{
    public static function register(): void
    {
        register_shutdown_function([self::class, 'flush']);

        if (!extension_loaded('pcntl')) {
            return;
        }

        pcntl_async_signals(true);

        $handler = function (int $signal) {
            self::flush();
            exit(0);
        };

        if (defined('SIGTERM')) {
            pcntl_signal(SIGTERM, $handler);
        }

        if (defined('SIGINT')) {
            pcntl_signal(SIGINT, $handler);
        }

        if (defined('SIGQUIT')) {
            pcntl_signal(SIGQUIT, $handler);
        }
    }

    public static function flush(): void
    {
        try {
            $tracerProvider = Globals::tracerProvider();
            if (method_exists($tracerProvider, 'forceFlush')) {
                $tracerProvider->forceFlush();
            }
            if (method_exists($tracerProvider, 'shutdown')) {
                $tracerProvider->shutdown();
            }

            $meterProvider = Globals::meterProvider();
            if (method_exists($meterProvider, 'forceFlush')) {
                $meterProvider->forceFlush();
            }
            if (method_exists($meterProvider, 'shutdown')) {
                $meterProvider->shutdown();
            }

            $loggerProvider = Globals::loggerProvider();
            if (method_exists($loggerProvider, 'forceFlush')) {
                $loggerProvider->forceFlush();
            }
            if (method_exists($loggerProvider, 'shutdown')) {
                $loggerProvider->shutdown();
            }
        } catch (\Throwable $e) {
            error_log('Failed to flush telemetry on shutdown: ' . $e->getMessage());
        }
    }
}
