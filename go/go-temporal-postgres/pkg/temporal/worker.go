package temporal

import (
	"go.opentelemetry.io/otel"
	"go.temporal.io/sdk/client"
	"go.temporal.io/sdk/contrib/opentelemetry"
	"go.temporal.io/sdk/interceptor"
	"go.temporal.io/sdk/worker"
)

type WorkerConfig struct {
	TaskQueue string
}

func NewWorker(c client.Client, cfg WorkerConfig) (worker.Worker, error) {
	tracingInterceptor, err := opentelemetry.NewTracingInterceptor(opentelemetry.TracerOptions{
		Tracer: otel.Tracer("temporal-worker"),
	})
	if err != nil {
		return nil, err
	}

	opts := worker.Options{
		Interceptors: []interceptor.WorkerInterceptor{
			tracingInterceptor,
		},
	}

	return worker.New(c, cfg.TaskQueue, opts), nil
}
