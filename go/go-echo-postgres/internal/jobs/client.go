package jobs

import (
	"context"
	"encoding/json"

	"go-echo-postgres/internal/logging"

	"github.com/hibiken/asynq"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"
	"go.opentelemetry.io/otel/propagation"
)

const (
	TypeNotification = "notification:article"
	DefaultQueue     = "default"
)

var (
	tracer           = otel.Tracer("go-echo-postgres")
	meter            = otel.Meter("go-echo-postgres")
	jobsEnqueued     metric.Int64Counter
)

type NotificationPayload struct {
	ArticleID    uint              `json:"article_id"`
	ArticleTitle string            `json:"article_title"`
	TraceContext map[string]string `json:"trace_context"`
}

type Client struct {
	client *asynq.Client
}

func NewClient(redisAddr string) (*Client, error) {
	client := asynq.NewClient(asynq.RedisClientOpt{Addr: redisAddr})

	var err error
	jobsEnqueued, err = meter.Int64Counter(
		"jobs.enqueued",
		metric.WithDescription("Total number of jobs enqueued"),
	)
	if err != nil {
		logging.Logger().Error().Err(err).Msg("failed to create jobs enqueued counter")
	}

	return &Client{client: client}, nil
}

func (c *Client) Close() error {
	return c.client.Close()
}

func (c *Client) EnqueueNotification(ctx context.Context, articleID uint, articleTitle string) error {
	ctx, span := tracer.Start(ctx, "job.enqueue.notification")
	defer span.End()

	span.SetAttributes(
		attribute.Int64("article.id", int64(articleID)),
		attribute.String("article.title", articleTitle),
		attribute.String("job.type", TypeNotification),
	)

	carrier := propagation.MapCarrier{}
	otel.GetTextMapPropagator().Inject(ctx, carrier)

	payload := NotificationPayload{
		ArticleID:    articleID,
		ArticleTitle: articleTitle,
		TraceContext: carrier,
	}

	payloadBytes, err := json.Marshal(payload)
	if err != nil {
		return err
	}

	task := asynq.NewTask(TypeNotification, payloadBytes)
	info, err := c.client.EnqueueContext(ctx, task)
	if err != nil {
		span.RecordError(err)
		return err
	}

	if jobsEnqueued != nil {
		jobsEnqueued.Add(ctx, 1, metric.WithAttributes(
			attribute.String("job.type", TypeNotification),
		))
	}

	span.SetAttributes(
		attribute.String("job.id", info.ID),
		attribute.String("job.queue", info.Queue),
	)

	logging.Info(ctx).
		Str("job_id", info.ID).
		Str("job_type", TypeNotification).
		Uint("article_id", articleID).
		Msg("job enqueued")

	return nil
}
