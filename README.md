# OpenTelemetry Integration Examples

Production-ready examples for integrating OpenTelemetry with
[Base14 Scout][scout] observability platform.

## Available Examples

### Node.js

| Framework | Stack | Example | Features |
| --------- | ----- | ------- | -------- |
| **Express 5** | Express 5 + TypeScript + PostgreSQL 18 | [express5-postgres](./nodejs/express5-postgres) | BullMQ jobs, WebSockets, auto-instrumentation |
| **NestJS** | NestJS 11 + TypeScript + PostgreSQL 18 | [nestjs-postgres](./nodejs/nestjs-postgres) | Enterprise architecture, BullMQ, WebSockets |
| **Express (Legacy)** | Express + TypeScript + MongoDB | [express-typescript-mongodb](./nodejs/express-typescript-mongodb) | MongoDB integration, Redis |

### Python

| Framework | Stack | Example | Features |
| --------- | ----- | ------- | -------- |
| **Django** | Django 5.2 LTS + PostgreSQL 18 | [django-postgres](./python/django-postgres) | Celery jobs, PII masking, auto-instrumentation |
| **Flask** | Flask 3.1 + PostgreSQL 18 | [flask-postgres](./python/flask-postgres) | Celery jobs, SQLAlchemy, auto-instrumentation |
| **FastAPI** | FastAPI 0.123 + PostgreSQL | [fastapi-postgres](./python/fastapi-postgres) | JWT auth, auto-instrumentation |
| **FastAPI + Celery** | FastAPI + Celery + PostgreSQL | [fastapi-celery-postgres](./python/fastapi-celery-postgres) | Distributed tracing across async tasks |

### Go

| Framework | Stack | Example | Features |
| --------- | ----- | ------- | -------- |
| **Echo** | Echo 4.13 + GORM + PostgreSQL 18 | [echo-postgres](./go/echo-postgres) | Asynq jobs, GORM service pattern |
| **Fiber** | Fiber 2.52 + sqlx + PostgreSQL 18 | [fiber-postgres](./go/fiber-postgres) | River jobs (PostgreSQL-native), repository pattern |
| **Echo + Temporal** | Echo 4.15 + Temporal + PostgreSQL 18 | [go-temporal-postgres](./go/go-temporal-postgres) | Workflow orchestration, microservice workers, simulation framework |
| **Chi** | Chi + In-memory storage | [chi-inmemory](./go/chi-inmemory) | Custom instrumentation |
| **Gin (Legacy)** | Gin 1.9.1 + PostgreSQL 14 | [go119-gin191-postgres](./go/go119-gin191-postgres) | Legacy Go 1.19 support |

### Java

| Framework | Stack | Example | Features |
| --------- | ----- | ------- | -------- |
| **Quarkus** | Quarkus 3.17 + Java 21 + PostgreSQL 18 | [quarkus-postgres](./java/quarkus-postgres) | Built-in OTEL, native compilation, JWT auth |
| **Spring Boot** | Spring Boot 3.5.7 + Java 17 + MySQL | [spring-boot-java17-mysql](./java/spring-boot-java17-mysql) | Auto-instrumentation |
| **Spring Boot** | Spring Boot 3.5.8 + Java 25 + PostgreSQL | [spring-boot-java25-postgresql](./java/spring-boot-java25-postgresql) | SDK Integration |
| **Spring Boot** | Spring Boot 3.5.8 + Java 25 + MongoDB | [spring-boot-java25-mongodb-java-agent](./java/spring-boot-java25-mongodb-java-agent) | Java Agent |

### Ruby

| Framework | Stack | Example | Features |
| --------- | ----- | ------- | -------- |
| **Rails** | Rails | [ruby](./ruby) | [Guide][doc-rails] |

### PHP

| Framework | Stack | Example | Features |
| --------- | ----- | ------- | -------- |
| **Laravel 8** | Laravel 8.65 + PHP 8 + SQLite | [php8-laravel8-sqlite](./php/php8-laravel8-sqlite) | JWT auth, auto-instrumentation |
| **Laravel 12** | Laravel 12.39 + PHP 8.5 + PostgreSQL 18 | [php85-laravel12-postgres](./php/php85-laravel12-postgres) | JWT auth, auto-instrumentation |

### Elixir

| Framework | Stack | Example | Features |
| --------- | ----- | ------- | -------- |
| **Phoenix** | Phoenix 1.8 + Ecto 3 + PostgreSQL 14+ | [phoenix18-ecto3-postgres](./elixir/phoenix18-ecto3-postgres) | LiveView, real-time chat, auto-instrumentation |

### Infrastructure & Integrations

| Component | Purpose | Example | Documentation |
| --------- | ------- | ------- | ------------- |
| **Scout Collector** | OpenTelemetry Collector | [scout-collector](./scout-collector) | [Guide][doc-collector] |
| **AWS CloudWatch** | CloudWatch log streaming | [aws-cloudwatch-stream](./aws-cloudwatch-stream) | - |
| **Load Generator** | Load testing with OTEL | [loadgen](./loadgen) | [README](./loadgen/README.md) |

### Mobile Applications

| Platform | Example |
| -------- | ------- |
| **Mobile Demo** | [astronomy_shop_mobile](./astronomy_shop_mobile) |

## Quick Start

### 1. Choose Your Framework

Navigate to the framework directory that matches your stack:

```bash
# Node.js
cd nodejs/express5-postgres              # Express 5 + PostgreSQL + BullMQ
cd nodejs/nestjs-postgres                # NestJS + PostgreSQL + BullMQ

# Python
cd python/django-postgres                # Django + PostgreSQL + Celery
cd python/flask-postgres                 # Flask + PostgreSQL + Celery

# Go
cd go/echo-postgres                      # Echo + GORM + Asynq
cd go/fiber-postgres                     # Fiber + sqlx + River

# Java
cd java/quarkus-postgres                 # Quarkus + PostgreSQL
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

### Express 5

Modern Express REST API with TypeScript, WebSocket support, and background job processing with BullMQ.
Demonstrates comprehensive auto-instrumentation and trace propagation across HTTP → Queue → Worker flows.

[View README →](./nodejs/express5-postgres/README.md)

### NestJS

Enterprise-grade architecture with dependency injection, background jobs, and WebSocket gateway.
Full OpenTelemetry integration including queue depth metrics and distributed tracing.

[View README →](./nodejs/nestjs-postgres/README.md)

### Django

Django LTS framework with Celery background tasks and PII masking at collector level.
Comprehensive auto-instrumentation showing distributed tracing across app and worker processes.

[View README →](./python/django-postgres/README.md)

### Go Echo (GORM Pattern)

Demonstrates GORM ORM with service layer pattern, Asynq job queue, and type-safe database operations with auto-migrations.
[View README →](./go/echo-postgres/README.md)

### Go Fiber (Repository Pattern)

Shows repository pattern with raw SQL via sqlx, River PostgreSQL-native job queue (no Redis), and fine-grained SQL control for performance optimization.
[View README →](./go/fiber-postgres/README.md)

### Go Temporal (Workflow Orchestration)

Demonstrates Temporal workflow orchestration with microservice workers for order fulfillment. Features fraud detection, inventory management, payment processing, and configurable failure simulation for testing.
[View README →](./go/go-temporal-postgres/README.md)

### Quarkus

Supersonic startup times with native compilation support, built-in OpenTelemetry extension, and production-ready synchronous REST API pattern.
[View README →](./java/quarkus-postgres/README.md)

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
[doc-rails]: https://docs.base14.io/instrument/apps/auto-instrumentation/rails
[doc-collector]: https://docs.base14.io/category/opentelemetry-collector-setup
[doc-apps]: https://docs.base14.io/category/app-instrumentation
