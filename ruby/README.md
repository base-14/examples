# Ruby Examples

OpenTelemetry instrumentation examples for Ruby applications.

## Projects

| Project | Description |
| ------- | ----------- |
| [rails8-sqlite](./rails8-sqlite) | Rails 8.1.1 with auto-instrumentation, SQLite, and OIDC authentication |
| [ruby27-rails52-mysql8](./ruby27-rails52-mysql8) | Rails 5.2.8 with Ruby 2.7.7, MySQL 8, and Scout APM integration |
| [puma-metrics](./puma-metrics) | Puma runtime metrics via yabeda-prometheus, scraped by the OTel Collector and shipped to Scout |

## Contributing

When adding new examples:

- Include a complete README with setup and usage instructions
- Provide docker-compose setup for easy local testing
- Include OpenTelemetry configuration (collector config recommended)
- Document all environment variables and endpoints
- Add troubleshooting section for common issues
- Keep examples focused and production-ready

Follow the structure of existing projects for consistency.
