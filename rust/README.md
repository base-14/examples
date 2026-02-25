# Rust Examples

OpenTelemetry instrumentation examples for Rust applications.

## Projects

| Project | Description |
| ------- | ----------- |
| [axum-postgres](./axum-postgres) | Axum + SQLx + PostgreSQL 18 with JWT auth, PostgreSQL-native job queue, custom spans, and full OTel instrumentation |
| [ai-report-generator](./ai-report-generator) | Rust 1.92 + Axum + async-openai + PostgreSQL with economic report pipeline, multi-provider LLM (OpenAI/Google/Anthropic/Ollama), and GenAI observability |

## Contributing

When adding new examples:

- Include a complete README with setup and usage instructions
- Provide docker-compose setup for easy local testing
- Include OpenTelemetry configuration (collector config recommended)
- Document all environment variables and endpoints
- Add troubleshooting section for common issues
- Keep examples focused and production-ready

Follow the structure of existing projects for consistency.
