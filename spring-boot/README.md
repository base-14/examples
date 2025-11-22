# Spring Boot Examples

OpenTelemetry instrumentation examples for Spring Boot applications.

## Projects

| Project | Description |
| ------- | ----------- |
| [java17-mysql](./java17-mysql) | Spring Boot 3.5.7 with auto-instrumentation, MySQL, and JPA |
| [java25-postgresql](./java25-postgresql) | Spring Boot 3.5.8 with SDK Integration, PostgreSQL, and JPA |
| [java25-mongodb-java-agent](./java25-mongodb-java-agent) | Spring Boot 3.5.8 with Java Agent instrumentation, MongoDB 7.x, and Spring Data MongoDB |

## Contributing

When adding new examples:

- Include a complete README with setup and usage instructions
- Provide docker-compose setup for easy local testing
- Include OpenTelemetry configuration (collector config recommended)
- Document all environment variables and endpoints
- Add troubleshooting section for common issues
- Keep examples focused and production-ready

Follow the structure of existing projects for consistency.
