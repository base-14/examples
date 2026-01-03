package jobs

import (
	"context"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/riverqueue/river"
	"github.com/riverqueue/river/riverdriver/riverpgxv5"
	"go-fiber-postgres/internal/logging"
)

type Worker struct {
	client *river.Client[pgx.Tx]
}

func NewWorker(ctx context.Context, pool *pgxpool.Pool) (*Worker, error) {
	workers := river.NewWorkers()
	river.AddWorker(workers, &NotificationWorker{})

	client, err := river.NewClient(riverpgxv5.New(pool), &river.Config{
		Queues: map[string]river.QueueConfig{
			river.QueueDefault: {MaxWorkers: 10},
		},
		Workers: workers,
	})
	if err != nil {
		return nil, err
	}

	return &Worker{client: client}, nil
}

func (w *Worker) Start(ctx context.Context) error {
	logging.Info(ctx, "starting river worker")
	return w.client.Start(ctx)
}

func (w *Worker) Stop(ctx context.Context) error {
	logging.Info(ctx, "stopping river worker")
	return w.client.Stop(ctx)
}
