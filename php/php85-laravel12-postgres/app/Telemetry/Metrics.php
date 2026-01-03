<?php

namespace App\Telemetry;

use OpenTelemetry\API\Globals;
use OpenTelemetry\API\Metrics\CounterInterface;
use OpenTelemetry\API\Metrics\HistogramInterface;
use OpenTelemetry\API\Metrics\MeterInterface;

class Metrics
{
    private static ?MeterInterface $meter = null;
    private static array $counters = [];
    private static array $histograms = [];

    private static function getMeter(): MeterInterface
    {
        if (self::$meter === null) {
            self::$meter = Globals::meterProvider()->getMeter('laravel-app');
        }
        return self::$meter;
    }

    private static function getCounter(string $name, string $description = '', string $unit = ''): CounterInterface
    {
        if (!isset(self::$counters[$name])) {
            self::$counters[$name] = self::getMeter()->createCounter($name, $unit, $description);
        }
        return self::$counters[$name];
    }

    private static function getHistogram(string $name, string $description = '', string $unit = ''): HistogramInterface
    {
        if (!isset(self::$histograms[$name])) {
            self::$histograms[$name] = self::getMeter()->createHistogram($name, $unit, $description);
        }
        return self::$histograms[$name];
    }

    public static function jobEnqueued(string $jobName, string $queue = 'default'): void
    {
        self::getCounter('jobs.enqueued.total', 'Total jobs enqueued')
            ->add(1, ['job.name' => $jobName, 'job.queue' => $queue]);
    }

    public static function jobCompleted(string $jobName, string $queue = 'default'): void
    {
        self::getCounter('jobs.completed.total', 'Total jobs completed successfully')
            ->add(1, ['job.name' => $jobName, 'job.queue' => $queue]);
    }

    public static function jobFailed(string $jobName, string $queue = 'default'): void
    {
        self::getCounter('jobs.failed.total', 'Total jobs failed')
            ->add(1, ['job.name' => $jobName, 'job.queue' => $queue]);
    }

    public static function jobDuration(float $durationMs, string $jobName, string $queue = 'default'): void
    {
        self::getHistogram('jobs.processing.duration', 'Job processing duration in milliseconds', 'ms')
            ->record($durationMs, ['job.name' => $jobName, 'job.queue' => $queue]);
    }

    public static function authRegistration(): void
    {
        self::getCounter('users.registered.total', 'Total user registrations')->add(1);
    }

    public static function authLoginSuccess(): void
    {
        self::getCounter('users.login.success.total', 'Total successful logins')->add(1);
    }

    public static function authLoginFailed(): void
    {
        self::getCounter('users.login.failed.total', 'Total failed login attempts')->add(1);
    }

    public static function authLogout(): void
    {
        self::getCounter('users.logout.total', 'Total logouts')->add(1);
    }

    public static function apiRequest(string $method, string $endpoint, int $statusCode): void
    {
        self::getCounter('api.requests.total', 'Total API requests')
            ->add(1, ['http.method' => $method, 'http.route' => $endpoint, 'http.status_code' => $statusCode]);
    }

    public static function apiResponseTime(float $durationMs, string $method, string $endpoint): void
    {
        self::getHistogram('api.response.time', 'API response time in milliseconds', 'ms')
            ->record($durationMs, ['http.method' => $method, 'http.route' => $endpoint]);
    }

    public static function articleCreated(): void
    {
        self::getCounter('articles.created.total', 'Total articles created')->add(1);
    }

    public static function articleDeleted(): void
    {
        self::getCounter('articles.deleted.total', 'Total articles deleted')->add(1);
    }

    public static function articleFavorited(): void
    {
        self::getCounter('articles.favorited.total', 'Total article favorites')->add(1);
    }

    public static function articleUnfavorited(): void
    {
        self::getCounter('articles.unfavorited.total', 'Total article unfavorites')->add(1);
    }
}
