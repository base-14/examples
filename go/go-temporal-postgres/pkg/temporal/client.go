package temporal

import (
	"go.opentelemetry.io/otel"
	"go.temporal.io/sdk/client"
	"go.temporal.io/sdk/contrib/opentelemetry"
	"go.temporal.io/sdk/interceptor"
)

type ClientConfig struct {
	HostPort  string
	Namespace string
}

func NewClient(cfg ClientConfig) (client.Client, error) {
	tracingInterceptor, err := opentelemetry.NewTracingInterceptor(opentelemetry.TracerOptions{
		Tracer: otel.Tracer("temporal-client"),
	})
	if err != nil {
		return nil, err
	}

	opts := client.Options{
		HostPort:  cfg.HostPort,
		Namespace: cfg.Namespace,
		Interceptors: []interceptor.ClientInterceptor{
			tracingInterceptor,
		},
	}

	if opts.Namespace == "" {
		opts.Namespace = "default"
	}

	return client.Dial(opts)
}
