<?php

namespace App\Jobs;

use App\Concerns\TracesOperations;
use App\Models\Article;
use App\Telemetry\Metrics;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Bus\Dispatchable;
use Illuminate\Queue\InteractsWithQueue;
use Illuminate\Queue\SerializesModels;
use Illuminate\Support\Facades\Log;
use OpenTelemetry\API\Trace\Span;
use OpenTelemetry\API\Trace\SpanKind;

class ProcessArticleJob implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable, SerializesModels, TracesOperations;

    public int $tries = 3;
    public int $backoff = 5;

    private ?string $traceId = null;
    private ?string $spanId = null;
    private int $traceFlags = 0;

    public function __construct(
        public Article $article,
        ?string $traceId = null,
        ?string $spanId = null,
        int $traceFlags = 0
    ) {
        $this->traceId = $traceId;
        $this->spanId = $spanId;
        $this->traceFlags = $traceFlags;
    }

    public static function dispatchWithContext(Article $article): void
    {
        $traceId = null;
        $spanId = null;
        $traceFlags = 0;

        $currentSpan = Span::getCurrent();
        $spanContext = $currentSpan->getContext();

        if ($spanContext->isValid()) {
            $traceId = $spanContext->getTraceId();
            $spanId = $spanContext->getSpanId();
            $traceFlags = $spanContext->getTraceFlags();
        }

        self::dispatch($article, $traceId, $spanId, $traceFlags);
        Metrics::jobEnqueued(self::class);
    }

    public function handle(): void
    {
        $startTime = microtime(true);
        $queue = $this->queue ?? 'default';

        $this->withLinkedSpan(
            'job.process_article',
            function ($span) {
                $span->setAttribute('job.name', self::class);
                $span->setAttribute('job.queue', $this->queue ?? 'default');
                $span->setAttribute('job.attempt', $this->attempts());
                $span->setAttribute('article.id', $this->article->id);
                $span->setAttribute('article.slug', $this->article->slug);
                $span->setAttribute('article.author_id', $this->article->author_id);

                if ($this->traceId) {
                    $span->setAttribute('job.parent_trace_id', $this->traceId);
                    $span->setAttribute('job.parent_span_id', $this->spanId);
                }

                $span->addEvent('job.started', [
                    'article.title' => $this->article->title,
                ]);

                $this->processArticle();

                $span->addEvent('job.completed');

                Log::info('Article processed successfully', [
                    'article_id' => $this->article->id,
                    'trace_id' => $span->getContext()->getTraceId(),
                    'span_id' => $span->getContext()->getSpanId(),
                    'parent_trace_id' => $this->traceId,
                ]);
            },
            $this->traceId,
            $this->spanId,
            $this->traceFlags
        );

        $durationMs = (microtime(true) - $startTime) * 1000;
        Metrics::jobCompleted(self::class, $queue);
        Metrics::jobDuration($durationMs, self::class, $queue);
    }

    private function processArticle(): void
    {
        usleep(100000);
        $this->article->touch();
    }

    public function failed(\Throwable $exception): void
    {
        Metrics::jobFailed(self::class, $this->queue ?? 'default');

        $this->withSpan(
            'job.failed',
            function ($span) use ($exception) {
                $span->setAttribute('job.name', self::class);
                $span->setAttribute('article.id', $this->article->id);
                $span->setAttribute('error.type', 'job_failed');
                $span->recordException($exception);

                Log::error('ProcessArticleJob failed permanently', [
                    'article_id' => $this->article->id,
                    'error' => $exception->getMessage(),
                    'trace_id' => $span->getContext()->getTraceId(),
                ]);

                throw $exception;
            },
            [],
            SpanKind::KIND_INTERNAL,
            'laravel-app'
        );
    }
}
