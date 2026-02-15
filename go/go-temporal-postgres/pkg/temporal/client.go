package temporal

import (
	"go.temporal.io/sdk/client"
)

type ClientConfig struct {
	HostPort  string
	Namespace string
}

func NewClient(cfg ClientConfig) (client.Client, error) {
	opts := client.Options{
		HostPort:  cfg.HostPort,
		Namespace: cfg.Namespace,
	}

	if opts.Namespace == "" {
		opts.Namespace = "default"
	}

	return client.Dial(opts)
}
