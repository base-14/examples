<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Article;
use App\Models\Comment;
use App\Models\User;
use Illuminate\Http\Response;
use Illuminate\Support\Facades\DB;

class MetricsController extends Controller
{
    public function __invoke(): Response
    {
        $metrics = $this->collectMetrics();
        $output = $this->formatPrometheus($metrics);

        return response($output, 200)
            ->header('Content-Type', 'text/plain; version=0.0.4; charset=utf-8');
    }

    private function collectMetrics(): array
    {
        return [
            [
                'name' => 'app_users_total',
                'help' => 'Total number of registered users',
                'type' => 'gauge',
                'value' => User::count(),
            ],
            [
                'name' => 'app_articles_total',
                'help' => 'Total number of articles',
                'type' => 'gauge',
                'value' => Article::count(),
            ],
            [
                'name' => 'app_comments_total',
                'help' => 'Total number of comments',
                'type' => 'gauge',
                'value' => Comment::count(),
            ],
            [
                'name' => 'app_database_up',
                'help' => 'Database connection status (1 = up, 0 = down)',
                'type' => 'gauge',
                'value' => $this->isDatabaseUp() ? 1 : 0,
            ],
            [
                'name' => 'app_info',
                'help' => 'Application information',
                'type' => 'gauge',
                'value' => 1,
                'labels' => [
                    'version' => config('app.version', '1.0.0'),
                    'php_version' => PHP_VERSION,
                    'laravel_version' => app()->version(),
                ],
            ],
        ];
    }

    private function formatPrometheus(array $metrics): string
    {
        $lines = [];

        foreach ($metrics as $metric) {
            $lines[] = "# HELP {$metric['name']} {$metric['help']}";
            $lines[] = "# TYPE {$metric['name']} {$metric['type']}";

            $labels = '';
            if (isset($metric['labels']) && !empty($metric['labels'])) {
                $labelParts = [];
                foreach ($metric['labels'] as $key => $value) {
                    $labelParts[] = "{$key}=\"{$value}\"";
                }
                $labels = '{' . implode(',', $labelParts) . '}';
            }

            $lines[] = "{$metric['name']}{$labels} {$metric['value']}";
            $lines[] = '';
        }

        return implode("\n", $lines);
    }

    private function isDatabaseUp(): bool
    {
        try {
            DB::connection()->getPdo();
            return true;
        } catch (\Exception $e) {
            return false;
        }
    }
}
