# PHP Examples

OpenTelemetry instrumentation examples for PHP applications.

## Projects

| Project | Description |
| ------- | ----------- |
| [php8-laravel8-sqlite](./php8-laravel8-sqlite) | Laravel 8.65 with auto-instrumentation, SQLite, and JWT authentication |
| [php85-laravel12-postgres](./php85-laravel12-postgres) | Laravel 12.39 with auto-instrumentation, PostgreSQL 18, and JWT authentication |
| [php84-slim4-mongodb](./php84-slim4-mongodb) | Slim 4.15 with auto-slim HTTP instrumentation, MongoDB 8, and PHP-FPM + Nginx |
| [php84-slim3-mongodb](./php84-slim3-mongodb) | Slim 3.12 (EOL) with manual TelemetryMiddleware, MongoDB 8, and PHP-FPM + Nginx |

## Contributing

When adding new examples:

- Include a complete README with setup and usage instructions
- Provide docker-compose setup for easy local testing
- Include OpenTelemetry configuration (collector config recommended)
- Document all environment variables and endpoints
- Add troubleshooting section for common issues
- Keep examples focused and production-ready

Follow the structure of existing projects for consistency.
