# OpenTelemetry Integration Examples

Production-ready examples for integrating OpenTelemetry with
[Base14 Scout][scout] observability platform.

## Available Examples

### Backend Frameworks

| Framework | Language | Example | Documentation |
| --------- | -------- | ------- | ------------- |
| **Spring Boot** | Java 17 | [java17-mysql](./spring-boot/java17-mysql) | [Guide][doc-spring-boot] |
| **FastAPI** | Python | [python-fast-api](./python-fast-api) | [Guide][doc-fastapi] |
| **Rails** | Ruby | [rails](./rails) | [Guide][doc-rails] |
| **Phoenix** | Elixir | [elixir-phoenix-otel](./elixir-phoenix-otel) | [Guide][doc-phoenix] |
| **Laravel** | PHP | [laravel](./laravel) | [Guide][doc-laravel] |
| **Go** | Go | [go](./go) | [Guide][doc-go] |

### Infrastructure & Integrations

| Component | Purpose | Example | Documentation |
| --------- | ------- | ------- | ------------- |
| **Scout Collector** | OpenTelemetry Collector | [scout-collector](./scout-collector) | [Guide][doc-collector] |
| **AWS CloudWatch** | CloudWatch log streaming | [aws-cloudwatch-stream](./aws-cloudwatch-stream) | - |

### Mobile Applications

| Platform | Example |
| -------- | ------- |
| **Mobile Demo** | [astronomy_shop_mobile](./astronomy_shop_mobile) |

## Quick Start

### 1. Choose Your Framework

Navigate to the framework directory that matches your stack:

```bash
cd spring-boot/java17-mysql    # For Spring Boot (Java)
cd python-fast-api              # For FastAPI (Python)
cd rails                        # For Rails (Ruby)
```

### 2. Follow Framework-Specific README

Each example includes:

- Prerequisites and setup instructions
- OpenTelemetry configuration
- Docker Compose setup for local development
- API endpoints and usage examples
- Troubleshooting guides

### 3. Configure Scout Connection

All examples require an OpenTelemetry Collector endpoint. See the
[Collector Setup Guide][doc-collector] for configuration options.

## What's Instrumented?

All examples demonstrate:

- ✅ **Distributed Tracing** - Request flows across services
- ✅ **Metrics Collection** - Application and infrastructure metrics
- ✅ **Structured Logging** - Correlated logs with trace context
- ✅ **Resource Attributes** - Service identification and metadata

## Framework Highlights

### Spring Boot

Most comprehensive example with auto-instrumentation, MySQL connection pool
monitoring, and Actuator endpoints.
[View README →](./spring-boot/java17-mysql/README.md)

### Go

Demonstrates custom instrumentation with detailed span events and performance
monitoring histograms. [View README →](./go/README.md)

## Adding New Examples

Each framework example should follow this structure:

```plain
framework-name/
├── README.md              # Setup instructions, prerequisites, troubleshooting
├── compose.yaml           # Docker Compose for local development
├── Dockerfile             # Container configuration
├── config/
│   └── otel-config.yml   # OpenTelemetry Collector config (if needed)
└── src/                  # Application source code
```

Include in your README:

- Quick start guide with Docker commands
- Environment variables and configuration
- API endpoints or usage examples
- Link to Base14 [App Instrumentation][doc-apps] docs

## Resources

### Base14 Documentation

- [Scout Platform][scout] - Observability platform overview
- [App Instrumentation][doc-apps] - Framework-specific guides
- [Collector Setup][doc-collector] - OpenTelemetry Collector configuration

### OpenTelemetry

- [OpenTelemetry Docs](https://opentelemetry.io/docs/) - Official documentation
- [Language SDKs](https://opentelemetry.io/docs/languages/) - Language-specific guides

## License

See [LICENSE](./LICENSE) for details.

[scout]: https://base14.io/scout
[doc-spring-boot]: https://docs.base14.io/instrument/apps/auto-instrumentation/spring-boot
[doc-fastapi]: https://docs.base14.io/instrument/apps/auto-instrumentation/fast-api
[doc-rails]: https://docs.base14.io/instrument/apps/auto-instrumentation/rails
[doc-phoenix]: https://docs.base14.io/instrument/apps/auto-instrumentation/elixir-phoenix
[doc-laravel]: https://docs.base14.io/instrument/apps/auto-instrumentation/laravel
[doc-go]: https://docs.base14.io/instrument/apps/custom-instrumentation/go
[doc-collector]: https://docs.base14.io/category/opentelemetry-collector-setup
[doc-apps]: https://docs.base14.io/category/app-instrumentation
