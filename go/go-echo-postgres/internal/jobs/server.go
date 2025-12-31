package jobs

import (
	"context"

	"go-echo-postgres/internal/jobs/tasks"
	"go-echo-postgres/internal/logging"

	"github.com/hibiken/asynq"
)

type Server struct {
	server *asynq.Server
	mux    *asynq.ServeMux
}

func NewServer(redisAddr string, concurrency int) *Server {
	server := asynq.NewServer(
		asynq.RedisClientOpt{Addr: redisAddr},
		asynq.Config{
			Concurrency: concurrency,
			Queues: map[string]int{
				DefaultQueue: 10,
			},
			ErrorHandler: asynq.ErrorHandlerFunc(func(ctx context.Context, task *asynq.Task, err error) {
				logging.Error(ctx).
					Err(err).
					Str("task_type", task.Type()).
					Msg("task failed")
			}),
		},
	)

	mux := asynq.NewServeMux()
	mux.HandleFunc(TypeNotification, tasks.HandleNotification)

	return &Server{
		server: server,
		mux:    mux,
	}
}

func (s *Server) Start() error {
	logging.Logger().Info().Msg("starting asynq worker")
	return s.server.Start(s.mux)
}

func (s *Server) Shutdown() {
	logging.Logger().Info().Msg("shutting down asynq worker")
	s.server.Shutdown()
}
