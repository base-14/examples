<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use Illuminate\Http\JsonResponse;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Redis;

class HealthController extends Controller
{
    public function __invoke(): JsonResponse
    {
        $dbHealthy = $this->checkDatabase();
        $redisHealthy = $this->checkRedis();
        $allHealthy = $dbHealthy && $redisHealthy;

        $response = [
            'status' => $allHealthy ? 'healthy' : 'unhealthy',
            'components' => [
                'database' => $dbHealthy ? 'healthy' : 'unhealthy',
                'redis' => $redisHealthy ? 'healthy' : 'unhealthy',
            ],
            'service' => [
                'name' => config('app.name'),
                'version' => config('app.version', '1.0.0'),
            ],
            'timestamp' => now()->toIso8601String(),
        ];

        return response()->json($response, $allHealthy ? 200 : 503);
    }

    private function checkDatabase(): bool
    {
        try {
            DB::connection()->getPdo();
            DB::select('SELECT 1');
            return true;
        } catch (\Exception $e) {
            return false;
        }
    }

    private function checkRedis(): bool
    {
        try {
            Redis::ping();
            return true;
        } catch (\Throwable $e) {
            return false;
        }
    }
}
