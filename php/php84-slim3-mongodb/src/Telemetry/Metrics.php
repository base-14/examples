<?php

namespace App\Telemetry;

use OpenTelemetry\API\Globals;
use OpenTelemetry\API\Metrics\CounterInterface;
use OpenTelemetry\API\Metrics\MeterInterface;

class Metrics
{
    private static ?MeterInterface $meter = null;
    private static array $counters = [];

    private static function getMeter(): MeterInterface
    {
        if (self::$meter === null) {
            self::$meter = Globals::meterProvider()->getMeter('slim-app');
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

    public static function authRegistration(): void
    {
        self::getCounter('app.user.registrations', 'User registrations')->add(1);
    }

    public static function authLoginSuccess(): void
    {
        self::getCounter('app.user.logins', 'User login attempts')->add(1, ['result' => 'success']);
    }

    public static function authLoginFailed(): void
    {
        self::getCounter('app.user.logins', 'User login attempts')->add(1, ['result' => 'failure']);
    }

    public static function authLogout(): void
    {
        self::getCounter('app.user.logouts', 'User logouts')->add(1);
    }

    public static function articleCreated(): void
    {
        self::getCounter('app.article.creates', 'Articles created')->add(1);
    }

    public static function articleDeleted(): void
    {
        self::getCounter('app.article.deletes', 'Articles deleted')->add(1);
    }

    public static function articleFavorited(): void
    {
        self::getCounter('app.article.favorites', 'Article favorites')->add(1);
    }

    public static function articleUnfavorited(): void
    {
        self::getCounter('app.article.unfavorites', 'Article unfavorites')->add(1);
    }
}
