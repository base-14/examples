# Go Examples

OpenTelemetry instrumentation examples for Go applications.

## Projects

| Project | Description |
| ------- | ----------- |
| [echo-postgres](./echo-postgres) | Go 1.24 + Echo 4.13 + GORM + PostgreSQL 18 + Asynq with service pattern and auto-instrumentation |
| [fiber-postgres](./fiber-postgres) | Go 1.24 + Fiber 2.52 + sqlx + PostgreSQL 18 + River with repository pattern and PostgreSQL-native job queue |
| [go-temporal-postgres](./go-temporal-postgres) | Go 1.25 + Temporal + Echo 4.15 + PostgreSQL 18 with workflow orchestration, microservice workers, and full observability |
| [chi-inmemory](./chi-inmemory) | Go 1.25 with chi router, custom instrumentation, and in-memory storage |
| [go119-gin191-postgres](./go119-gin191-postgres) | Go 1.19 with Gin 1.9.1, PostgreSQL 14, and OpenTelemetry v1.17.0 |

## Contributing

When adding new examples:

- Include a complete README with setup and usage instructions
- Provide docker-compose setup for easy local testing
- Include OpenTelemetry configuration (collector config recommended)
- Document all environment variables and endpoints
- Add troubleshooting section for common issues
- Keep examples focused and production-ready

Follow the structure of existing projects for consistency.
