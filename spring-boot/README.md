# Spring Boot with OpenTelemetry

A production-ready Spring Boot application with comprehensive OpenTelemetry instrumentation for distributed tracing, metrics, and logs.

> 📚 **[Official Documentation](https://docs.base14.io/instrument/apps/auto-instrumentation/spring-boot)** - Complete guide for Spring Boot auto-instrumentation with Base14

## Overview

This application demonstrates enterprise-grade observability patterns using:

- **OpenTelemetry SDK 1.50.0** - Full auto-instrumentation
- **Spring Boot 3.5.7** - Modern Java framework
- **Micrometer** - Metrics bridge to OpenTelemetry
- **MySQL 9.5** - Database with connection pool monitoring
- **Docker Compose** - Containerized deployment

### Instrumented Components

- ✅ HTTP requests and responses
- ✅ Database queries (JDBC/JPA)
- ✅ JVM metrics (memory, threads, GC)
- ✅ Custom business metrics
- ✅ Distributed trace propagation (W3C)

## Prerequisites

- **Docker Desktop** (recommended) or Docker Engine with Compose plugin
- **Java 17+** (for local development)
- **Gradle 8.4+** (wrapper included)
- **OpenTelemetry Collector** (see configuration options below)

## Quick Start

### 1. Clone and Navigate

```bash
git clone https://github.com/base-14/examples.git
cd examples/spring-boot
```

### 2. Start the Application

```bash
docker-compose up --build -d
```

This starts:
- **MySQL** on port `3306`
- **Spring Boot app** on port `8080`

### 3. Verify Application

```bash
# Check health
curl http://localhost:8080/actuator/health

# Test API
curl http://localhost:8080/users/testMessage
```

## OpenTelemetry Collector Configuration

### Current Configuration: External Collector (Recommended for Production)

The application is configured to send telemetry to an **external** OpenTelemetry Collector running outside the compose stack.

**Configuration** (`compose.yaml`):
```yaml
environment:
  OTEL_EXPORTER_OTLP_PROTOCOL: http/protobuf
  OTEL_EXPORTER_OTLP_TRACES_ENDPOINT: http://host.docker.internal:4318/v1/traces
  OTEL_EXPORTER_OTLP_METRICS_ENDPOINT: http://host.docker.internal:4318/v1/metrics
  OTEL_EXPORTER_OTLP_LOGS_ENDPOINT: http://host.docker.internal:4318/v1/logs
```

**When to use this:**
- ✅ Production/staging environments
- ✅ Multiple applications sending to a centralized collector
- ✅ Collector managed by platform/SRE team
- ✅ Collector configuration changes independently of app deployment
- ✅ Better resource isolation and scaling

**Prerequisites:**
- OpenTelemetry Collector must be running on the host machine
- Collector must listen on ports `4317` (gRPC) and `4318` (HTTP)

**Start your collector:**
```bash
# Example: Using Docker
docker run -d \
  --name otel-collector \
  -p 4317:4317 \
  -p 4318:4318 \
  -v $(pwd)/config/otel-config.yml:/etc/otelcol-contrib/config.yaml \
  otel/opentelemetry-collector-contrib:0.128.0
```

### Alternative Configuration: Embedded Collector (Development/Testing)

For self-contained local development, you can include the collector in `compose.yaml`.

**Add to `compose.yaml`:**
```yaml
services:
  otel-collector:
    image: otel/opentelemetry-collector-contrib:0.128.0
    container_name: otel-collector
    ports:
      - '4317:4317'
      - '4318:4318'
    volumes:
      - ./config/otel-config.yml:/etc/otelcol-contrib/config.yaml

  spring-service:
    depends_on:
      - db
      - otel-collector
    environment:
      # Update endpoints to use collector service name
      OTEL_EXPORTER_OTLP_TRACES_ENDPOINT: http://otel-collector:4318/v1/traces
      OTEL_EXPORTER_OTLP_METRICS_ENDPOINT: http://otel-collector:4318/v1/metrics
      OTEL_EXPORTER_OTLP_LOGS_ENDPOINT: http://otel-collector:4318/v1/logs
```

**When to use this:**
- ✅ Local development on a new machine
- ✅ Demo/testing environments
- ✅ CI/CD integration tests
- ✅ Completely self-contained setup
- ✅ No external dependencies

**Trade-offs:**
- ⚠️ Tighter coupling between app and collector lifecycle
- ⚠️ More resources consumed on developer machine
- ⚠️ Collector restarts when compose stack restarts

## Configuration Reference

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SPRING_APPLICATION_NAME` | Service name in traces | `java-spring-boot-otel` |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | Protocol for OTLP export | `http/protobuf` |
| `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | Traces endpoint URL | `http://host.docker.internal:4318/v1/traces` |
| `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` | Metrics endpoint URL | `http://host.docker.internal:4318/v1/metrics` |
| `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` | Logs endpoint URL | `http://host.docker.internal:4318/v1/logs` |
| `OTEL_RESOURCE_ATTRIBUTES` | Resource attributes | `service.name=...,service.namespace=base14,...` |

### Resource Attributes

The application automatically includes:

```properties
service.name=java-spring-boot-otel
service.namespace=base14
service.version=0.0.1-SNAPSHOT
deployment.environment=dev
deployment.environment.name=dev  # Current OTel standard
```

## API Endpoints

### User Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/users/` | Get all users |
| `POST` | `/users/saveUser` | Create a new user |
| `PUT` | `/users/{id}` | Update user by ID |
| `DELETE` | `/users/{id}` | Delete user by ID |
| `GET` | `/users/testMessage` | Health check endpoint |

### Example Requests

```bash
# Create user
curl -X POST http://localhost:8080/users/saveUser \
  -H "Content-Type: application/json" \
  -d '{"name":"John Doe","address":"123 Main St"}'

# Get all users
curl http://localhost:8080/users/

# Update user
curl -X PUT http://localhost:8080/users/1 \
  -H "Content-Type: application/json" \
  -d '{"id":1,"name":"Jane Doe","address":"456 Elm St"}'
```

### Actuator Endpoints

| Endpoint | Description |
|----------|-------------|
| `/actuator/health` | Application health status |
| `/actuator/metrics` | Available metrics list |
| `/actuator/metrics/{metric}` | Specific metric details |
| `/actuator/prometheus` | Prometheus format metrics |

## Development Workflow

### Local Development (without Docker)

**Prerequisites:**
- MySQL running on `localhost:3306`
- Database `company` created
- OpenTelemetry Collector running on `localhost:4318`

```bash
# Update application.properties for local MySQL
# spring.datasource.url=jdbc:mysql://localhost:3306/company...

# Build and run
./gradlew bootRun

# Run tests
./gradlew test

# Build JAR
./gradlew build
```

### Docker Development

```bash
# Build and start
docker-compose up --build

# View logs
docker logs spring-app -f

# Restart after code changes
docker-compose restart spring-service

# Clean rebuild
docker-compose down
docker-compose up --build

# Stop all services
docker-compose down -v  # -v removes volumes
```

### Hot Reload (Development)

For faster iteration without Docker rebuilds:

1. Run MySQL in Docker: `docker-compose up db -d`
2. Update `application.properties` to use `localhost:3306`
3. Run locally: `./gradlew bootRun`

## Monitoring and Observability

### Traces

Distributed traces include:
- HTTP request spans with status codes, methods, URLs
- Database query spans with SQL statements
- Exception stack traces
- Custom business logic spans

### Metrics

Auto-collected metrics:
- **HTTP**: Request count, duration, error rate (RED metrics)
- **JVM**: Heap/non-heap memory, GC pause time, thread count
- **Database**: Connection pool size, active connections, query duration
- **Process**: CPU usage, file descriptors

### Logs

Structured logging with trace correlation:
- All logs include `trace_id` and `span_id`
- Log levels: `INFO` (default), `DEBUG` (OpenTelemetry internals)

## Troubleshooting

### Common Issues

**1. Cannot connect to OpenTelemetry Collector**

Error: `Failed to connect to localhost/127.0.0.1:4317`

**Solution:**
- Verify collector is running: `docker ps | grep otel-collector`
- Check collector logs: `docker logs otel-collector`
- Ensure using `host.docker.internal` not `localhost` in Docker

**2. No traces/metrics appearing**

**Solution:**
- Check application logs: `docker logs spring-app | grep -i otel`
- Verify collector configuration exports to correct backend
- Check resource attributes are set correctly
- Ensure `OTEL_SDK_DISABLED=false`

**3. Database connection errors**

Error: `Communications link failure`

**Solution:**
- Wait for MySQL healthcheck: `docker-compose ps`
- Check MySQL logs: `docker logs mysql-db`
- Verify network connectivity: `docker network ls`

**4. Build fails with Java version error**

**Solution:**
- Docker uses Java 17 (specified in Dockerfile)
- Local builds require Java 17+
- Check: `java -version`

### Debug Mode

Enable detailed OpenTelemetry logs:

```yaml
# compose.yaml
environment:
  OTEL_LOG_LEVEL: DEBUG
```

Or in `application.properties`:
```properties
logging.level.io.opentelemetry=DEBUG
logging.level.io.opentelemetry.exporter=TRACE
```

## Project Structure

```
.
├── src/
│   ├── main/
│   │   ├── java/com/base14/demo/
│   │   │   ├── controller/      # REST controllers
│   │   │   ├── model/           # JPA entities
│   │   │   ├── repository/      # Data access layer
│   │   │   ├── service/         # Business logic
│   │   │   └── DemoApplication.java
│   │   └── resources/
│   │       └── application.properties
│   └── test/
├── config/
│   └── otel-config.yml          # OpenTelemetry Collector config
├── build.gradle                 # Dependencies and build config
├── Dockerfile                   # Multi-stage build
├── compose.yaml                 # Docker Compose services
└── README.md
```

## Technology Stack

| Component           | Version | Purpose          |
|---------------------|---------|------------------|
| Spring Boot         | 3.5.7   | Web framework    |
| OpenTelemetry Java  | 2.16.0  | Instrumentation  |
| OpenTelemetry SDK   | 1.50.0  | Core SDK         |
| Micrometer          | -       | Metrics bridge   |
| MySQL               | 9.5     | Database         |
| Gradle              | 8.4.0   | Build tool       |
| Java                | 17      | Runtime          |

## Contributing

### Code Style

- Use 4 spaces for indentation
- Follow standard Java conventions
- Keep methods focused and concise
- Add comments for complex logic only

### Testing

```bash
# Run all tests
./gradlew test

# Run specific test
./gradlew test --tests UserControllerTest

# Generate coverage report
./gradlew jacocoTestReport
```

## Resources

### Base14 Documentation
- **[Spring Boot Auto-Instrumentation Guide](https://docs.base14.io/instrument/apps/auto-instrumentation/spring-boot)** - Official Base14 documentation
- [Base14 Platform](https://base14.io) - Observability platform

### OpenTelemetry & Spring Boot
- [OpenTelemetry Java Docs](https://opentelemetry.io/docs/languages/java/)
- [Spring Boot Actuator](https://docs.spring.io/spring-boot/docs/current/reference/html/actuator.html)
- [OpenTelemetry Collector](https://opentelemetry.io/docs/collector/)
- [W3C Trace Context](https://www.w3.org/TR/trace-context/)

## License

This project is part of the Base14 examples repository.
