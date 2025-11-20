# Spring Boot with OpenTelemetry

Spring Boot 3.5.7 application with OpenTelemetry auto-instrumentation for
traces, metrics, and logs.

> 📚 [Full Documentation](https://docs.base14.io/instrument/apps/auto-instrumentation/spring-boot)

## What's Instrumented

- HTTP requests and responses
- Database queries (JDBC/JPA) and connection pool
- JVM metrics (memory, threads, GC)
- Distributed trace propagation (W3C)
- Custom business metrics via Micrometer

## Prerequisites

- Docker Desktop or Docker Engine with Compose
- OpenTelemetry Collector running (see [Collector Setup](#collector-setup) below)
- Java 17+ (only for local development without Docker)

## Quick Start

```bash
# Clone and navigate
git clone https://github.com/base-14/examples.git
cd examples/spring-boot/java17-mysql

# Start application (MySQL + Spring Boot)
docker-compose up --build -d

# Verify it's running
curl http://localhost:8080/actuator/health
curl http://localhost:8080/users/testMessage
```

The app runs on port `8080`, MySQL on `3306`.

## Collector Setup

The app sends telemetry to an OpenTelemetry Collector on `host.docker.internal:4318`.

### Option 1: External Collector (Recommended)

Run the collector separately on your host machine. Best for production and
multi-app setups.

```bash
docker run -d \
  --name otel-collector \
  -p 4317:4317 \
  -p 4318:4318 \
  -v $(pwd)/config/otel-config.yml:/etc/otelcol-contrib/config.yaml \
  otel/opentelemetry-collector-contrib:0.128.0
```

See [Base14 Collector Setup Guide][collector-guide] for configuration.

[collector-guide]: https://docs.base14.io/category/opentelemetry-collector-setup

### Option 2: Embedded Collector (Local Development)

Add the collector to `compose.yaml` for a self-contained setup:

```yaml
services:
  otel-collector:
    image: otel/opentelemetry-collector-contrib:0.128.0
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
      OTEL_EXPORTER_OTLP_TRACES_ENDPOINT: http://otel-collector:4318/v1/traces
      OTEL_EXPORTER_OTLP_METRICS_ENDPOINT: http://otel-collector:4318/v1/metrics
      OTEL_EXPORTER_OTLP_LOGS_ENDPOINT: http://otel-collector:4318/v1/logs
```

## Configuration

### Environment Variables (compose.yaml)

| Variable | Default |
| -------- | ------- |
| `SPRING_APPLICATION_NAME` | `java-spring-boot-otel` |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `http/protobuf` |
| `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | `http://host.docker.internal:4318/v1/traces` |
| `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` | `http://host.docker.internal:4318/v1/metrics` |
| `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` | `http://host.docker.internal:4318/v1/logs` |

### Resource Attributes

Automatically included in telemetry:

```properties
service.name=java-spring-boot-otel
service.namespace=base14
service.version=0.0.1-SNAPSHOT
deployment.environment=dev
```

## API Endpoints

### Application Endpoints

| Method | Endpoint | Description |
| ------ | -------- | ----------- |
| `GET` | `/users/` | List all users |
| `POST` | `/users/saveUser` | Create user |
| `PUT` | `/users/{id}` | Update user |
| `DELETE` | `/users/{id}` | Delete user |
| `GET` | `/users/testMessage` | Test endpoint |

```bash
# Create user
curl -X POST http://localhost:8080/users/saveUser \
  -H "Content-Type: application/json" \
  -d '{"name":"John Doe","address":"123 Main St"}'

# List users
curl http://localhost:8080/users/
```

### Actuator Endpoints

| Endpoint | Purpose |
| -------- | ------- |
| `/actuator/health` | Health status |
| `/actuator/metrics` | Metrics list |
| `/actuator/prometheus` | Prometheus format |

## Development

### Run Locally (without Docker)

Requires MySQL and OTel Collector running locally on standard ports.

```bash
./gradlew bootRun      # Run application
./gradlew test         # Run tests
./gradlew build        # Build JAR
```

Update `application.properties` to use `localhost:3306` for MySQL.

### Docker Commands

```bash
docker-compose up --build        # Build and start
docker-compose down              # Stop all
docker-compose down -v           # Stop and remove volumes
docker logs spring-app -f        # View logs
docker-compose restart spring-service  # Restart app only
```

### Faster Development Loop

Run only MySQL in Docker, app locally for quick iteration:

```bash
docker-compose up db -d    # Start MySQL only
./gradlew bootRun          # Run app locally
```

## Telemetry Data

### Traces

- HTTP requests (method, URL, status)
- Database queries (SQL statements)
- Exceptions and stack traces

### Metrics

- **HTTP**: Request count, duration, errors
- **JVM**: Memory, GC, threads
- **Database**: Connection pool, query duration
- **Process**: CPU, file descriptors

### Logs

All logs include `trace_id` and `span_id` for correlation.

## Troubleshooting

### Collector connection failed

```bash
docker ps | grep otel-collector  # Check collector is running
docker logs otel-collector       # View collector logs
```

Use `host.docker.internal` not `localhost` when running app in Docker.

### No telemetry data

```bash
docker logs spring-app | grep -i otel  # Check app logs
```

Verify collector config exports to the correct backend.

### Database connection failed

```bash
docker-compose ps           # Check MySQL health
docker logs mysql-db        # View MySQL logs
```

Wait for MySQL healthcheck to complete before starting the app.

### Enable debug logging

In `compose.yaml`:

```yaml
environment:
  OTEL_LOG_LEVEL: DEBUG
```

Or `application.properties`:

```properties
logging.level.io.opentelemetry=DEBUG
```

## Project Structure

```plain
├── src/main/java/com/base14/demo/
│   ├── controller/          # REST controllers
│   ├── model/               # JPA entities
│   ├── repository/          # Data access
│   ├── service/             # Business logic
│   └── DemoApplication.java
├── src/main/resources/
│   └── application.properties
├── config/otel-config.yml   # Collector config
├── build.gradle             # Dependencies
├── Dockerfile
└── compose.yaml
```

## Technology Stack

| Component | Version |
| --------- | ------- |
| Spring Boot | 3.5.7 |
| OpenTelemetry Instrumentation | 2.21.0 |
| OpenTelemetry SDK | 1.55.0 |
| MySQL | 9.1 |
| Gradle | 9.2.1 |
| Java | 17 (target) / 17-25 (supported) |

## Resources

- [Spring Boot Auto-Instrumentation Guide][spring-boot-guide] -
  Base14 documentation
- [OpenTelemetry Java][otel-java] - OTel Java docs
- [Spring Boot Actuator][actuator] - Actuator reference
- [Base14 Scout][scout] - Observability platform

[spring-boot-guide]: https://docs.base14.io/instrument/apps/auto-instrumentation/spring-boot
[otel-java]: https://opentelemetry.io/docs/languages/java/
[actuator]: https://docs.spring.io/spring-boot/docs/current/reference/html/actuator.html
[scout]: https://base14.io/scout
