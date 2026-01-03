package jobs

import (
	"context"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/riverqueue/river"
	"github.com/riverqueue/river/riverdriver/riverpgxv5"
	"go-fiber-postgres/internal/logging"
	"go-fiber-postgres/internal/telemetry"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/propagation"
)

type Client struct {
	riverClient *river.Client[pgx.Tx]
}

func NewClient(ctx context.Context, pool *pgxpool.Pool) (*Client, error) {
	riverClient, err := river.NewClient(riverpgxv5.New(pool), &river.Config{})
	if err != nil {
		return nil, err
	}

	return &Client{riverClient: riverClient}, nil
}

func (c *Client) EnqueueNotification(ctx context.Context, articleID int, title string) error {
	ctx, span := telemetry.Tracer().Start(ctx, "job.enqueue")
	defer span.End()

	carrier := propagation.MapCarrier{}
	otel.GetTextMapPropagator().Inject(ctx, carrier)

	_, err := c.riverClient.Insert(ctx, NotificationArgs{
		ArticleID:    articleID,
		ArticleTitle: title,
		TraceContext: carrier,
	}, nil)

	if err != nil {
		logging.Error(ctx, "failed to enqueue notification", "error", err)
		telemetry.JobsFailed.Add(ctx, 1)
		return err
	}

	telemetry.JobsEnqueued.Add(ctx, 1)
	logging.Info(ctx, "notification job enqueued", "articleId", articleID)

	return nil
}

func (c *Client) Close(ctx context.Context) error {
	return nil
}
