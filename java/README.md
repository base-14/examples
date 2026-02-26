# Java Examples

OpenTelemetry instrumentation examples for Java applications.

## Projects

| Project | Description |
| ------- | ----------- |
| [quarkus-postgres](./quarkus-postgres) | Quarkus 3.30 + Java 21 + PostgreSQL 18 with built-in OpenTelemetry, native compilation support, and JWT authentication |
| [spring-boot-java17-mysql](./spring-boot-java17-mysql) | Spring Boot 3.5 + Java 17 + MySQL with auto-instrumentation for traces, metrics, and logs |
| [spring-boot-java25-postgresql](./spring-boot-java25-postgresql) | Spring Boot 3.5 + Java 25 + PostgreSQL with SDK Integration approach for OpenTelemetry instrumentation |
| [spring-boot-java25-mongodb-java-agent](./spring-boot-java25-mongodb-java-agent) | Spring Boot 3.5 + Java 25 + MongoDB 7 with Java Agent approach for OpenTelemetry instrumentation |
| [ai-customer-support](./ai-customer-support) | Spring Boot 4.0 + Spring AI 2.0 + Java 25 + pgvector — conversational AI support agent with RAG, tool calling, SSE streaming, and three-layer OTel instrumentation |

## Contributing

When adding new examples:

- Include a complete README with setup and usage instructions
- Provide docker-compose setup for easy local testing
- Include OpenTelemetry configuration (collector config recommended)
- Document all environment variables and endpoints
- Add troubleshooting section for common issues
- Keep examples focused and production-ready

Follow the structure of existing projects for consistency.
