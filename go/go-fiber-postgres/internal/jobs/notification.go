package jobs

import (
	"context"
	"time"

	"github.com/riverqueue/river"
	"go-fiber-postgres/internal/logging"
	"go-fiber-postgres/internal/telemetry"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/propagation"
)

type NotificationArgs struct {
	ArticleID    int               `json:"article_id"`
	ArticleTitle string            `json:"article_title"`
	TraceContext map[string]string `json:"trace_context"`
}

func (NotificationArgs) Kind() string { return "notification" }

type NotificationWorker struct {
	river.WorkerDefaults[NotificationArgs]
}

func (w *NotificationWorker) Work(ctx context.Context, job *river.Job[NotificationArgs]) error {
	parentCtx := otel.GetTextMapPropagator().Extract(
		context.Background(),
		propagation.MapCarrier(job.Args.TraceContext),
	)

	ctx, span := telemetry.Tracer().Start(parentCtx, "job.notification")
	defer span.End()

	logging.Info(ctx, "processing notification job",
		"articleId", job.Args.ArticleID,
		"articleTitle", job.Args.ArticleTitle,
	)

	time.Sleep(100 * time.Millisecond)

	logging.Info(ctx, "notification sent",
		"articleId", job.Args.ArticleID,
	)

	telemetry.JobsCompleted.Add(ctx, 1)

	return nil
}
