package tasks

import (
	"context"
	"encoding/json"
	"time"

	"go-echo-postgres/internal/logging"

	"github.com/hibiken/asynq"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/metric"
	"go.opentelemetry.io/otel/propagation"
)

var (
	tracer        = otel.Tracer("go-echo-postgres-worker")
	meter         = otel.Meter("go-echo-postgres-worker")
	jobsCompleted metric.Int64Counter
	jobsFailed    metric.Int64Counter
	jobsDuration  metric.Float64Histogram
)

func init() {
	var err error

	jobsCompleted, err = meter.Int64Counter(
		"jobs.completed",
		metric.WithDescription("Total number of jobs completed successfully"),
	)
	if err != nil {
		logging.Logger().Error().Err(err).Msg("failed to create jobs completed counter")
	}

	jobsFailed, err = meter.Int64Counter(
		"jobs.failed",
		metric.WithDescription("Total number of jobs failed"),
	)
	if err != nil {
		logging.Logger().Error().Err(err).Msg("failed to create jobs failed counter")
	}

	jobsDuration, err = meter.Float64Histogram(
		"jobs.duration_ms",
		metric.WithDescription("Job processing duration in milliseconds"),
		metric.WithUnit("ms"),
	)
	if err != nil {
		logging.Logger().Error().Err(err).Msg("failed to create jobs duration histogram")
	}
}

type NotificationPayload struct {
	ArticleID    uint              `json:"article_id"`
	ArticleTitle string            `json:"article_title"`
	TraceContext map[string]string `json:"trace_context"`
}

func HandleNotification(ctx context.Context, task *asynq.Task) error {
	start := time.Now()

	var payload NotificationPayload
	if err := json.Unmarshal(task.Payload(), &payload); err != nil {
		recordJobMetrics(ctx, "notification:article", false, time.Since(start))
		return err
	}

	parentCtx := otel.GetTextMapPropagator().Extract(
		context.Background(),
		propagation.MapCarrier(payload.TraceContext),
	)

	ctx, span := tracer.Start(parentCtx, "job.notification")
	defer span.End()

	span.SetAttributes(
		attribute.Int64("article.id", int64(payload.ArticleID)),
		attribute.String("article.title", payload.ArticleTitle),
		attribute.String("job.type", "notification:article"),
	)

	logging.Info(ctx).
		Uint("article_id", payload.ArticleID).
		Str("article_title", payload.ArticleTitle).
		Msg("processing article notification")

	time.Sleep(100 * time.Millisecond)

	span.SetStatus(codes.Ok, "notification processed")
	span.SetAttributes(attribute.Bool("job.success", true))

	logging.Info(ctx).
		Uint("article_id", payload.ArticleID).
		Msg("article notification processed successfully")

	recordJobMetrics(ctx, "notification:article", true, time.Since(start))

	return nil
}

func recordJobMetrics(ctx context.Context, jobType string, success bool, duration time.Duration) {
	attrs := []attribute.KeyValue{
		attribute.String("job.type", jobType),
	}

	if success {
		if jobsCompleted != nil {
			jobsCompleted.Add(ctx, 1, metric.WithAttributes(attrs...))
		}
	} else {
		if jobsFailed != nil {
			jobsFailed.Add(ctx, 1, metric.WithAttributes(attrs...))
		}
	}

	if jobsDuration != nil {
		jobsDuration.Record(ctx, float64(duration.Milliseconds()), metric.WithAttributes(attrs...))
	}
}
