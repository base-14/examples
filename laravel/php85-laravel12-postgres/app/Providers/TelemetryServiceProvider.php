<?php

namespace App\Providers;

use Illuminate\Support\Facades\Log;
use Illuminate\Support\ServiceProvider;
use OpenTelemetry\API\Globals;

class TelemetryServiceProvider extends ServiceProvider
{
    public function register(): void
    {
        //
    }

    public function boot(): void
    {
        $this->registerShutdownHandler();
        $this->registerSignalHandlers();
    }

    private function registerShutdownHandler(): void
    {
        register_shutdown_function(function () {
            $this->flushTelemetry();
        });
    }

    private function registerSignalHandlers(): void
    {
        if (! extension_loaded('pcntl')) {
            return;
        }

        $handler = function (int $signal) {
            Log::info('Received shutdown signal', [
                'signal' => $signal,
                'signal_name' => $this->getSignalName($signal),
            ]);

            $this->flushTelemetry();

            exit(0);
        };

        pcntl_async_signals(true);

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

    private function flushTelemetry(): void
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
            Log::warning('Failed to flush telemetry on shutdown', [
                'error' => $e->getMessage(),
            ]);
        }
    }

    private function getSignalName(int $signal): string
    {
        return match ($signal) {
            SIGTERM => 'SIGTERM',
            SIGINT => 'SIGINT',
            SIGQUIT => 'SIGQUIT',
            default => "SIGNAL($signal)",
        };
    }
}
