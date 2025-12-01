# Go Examples

OpenTelemetry instrumentation examples for Go applications.

## Projects

| Project | Description |
| ------- | ----------- |
| [go-chi-inmemory](./go-chi-inmemory) | Go 1.25 with chi router, custom instrumentation, and in-memory storage |
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
