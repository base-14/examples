# Spring Boot with OpenTelemetry

Spring Boot 3.5.8 application with OpenTelemetry instrumentation using the
**OpenTelemetry SDK Integration** approach.

> 📚 [Full Documentation](https://docs.base14.io/instrument/apps/auto-instrumentation/spring-boot)

## Instrumentation Approach

This example uses **OpenTelemetry SDK Integration** (production-ready):

- Dependency: `opentelemetry-spring-boot-starter`
- Direct OpenTelemetry API access
- Explicit dependency management via BOM
- Compatible with Spring Boot 2.7+ and 3.x

### What's Auto-Instrumented

- ✅ HTTP requests and responses (Spring MVC)
- ✅ Database queries (JDBC/JPA) and connection pools
- ✅ JVM metrics (memory, threads, GC)
- ✅ Distributed trace propagation (W3C)
- ✅ Custom business metrics via Micrometer

### What Requires Manual Instrumentation

For deeper application-level tracing (controller methods, service methods), consider:

- Manual `@WithSpan` annotations, OR
- [OpenTelemetry Java Agent][java-agent] for zero-code instrumentation

[java-agent]: https://docs.base14.io/instrument/apps/auto-instrumentation/spring-boot-alternatives#java-agent-approach

## Prerequisites

- Docker Desktop or Docker Engine with Compose
- Base14 Scout credentials ([setup guide](https://docs.base14.io/category/opentelemetry-collector-setup))
- Java 25+ (only for local development without Docker)

## Quick Start

```bash
# Clone and navigate
git clone https://github.com/base-14/examples.git
cd examples/java/spring-boot-java25-postgresql

# Set Base14 Scout credentials as environment variables
export SCOUT_ENDPOINT=https://your-tenant.base14.io/v1/traces
export SCOUT_CLIENT_ID=your_client_id
export SCOUT_CLIENT_SECRET=your_client_secret
export SCOUT_TOKEN_URL=https://your-tenant.base14.io/oauth/token

# Start application (PostgreSQL + Spring Boot + OTel Collector)
docker-compose up --build -d

# Verify it's running
curl http://localhost:8080/actuator/health
curl http://localhost:8080/users/testMessage
```

The app runs on port `8080`, PostgreSQL on `5432`, OTel Collector on `4317/4318`.

## Configuration

### Required Environment Variables

The OpenTelemetry Collector requires Base14 Scout credentials to export
telemetry data. Set these before running `docker-compose up`:

| Variable | Required | Description |
| -------- | -------- | ----------- |
| `SCOUT_ENDPOINT` | Yes | Base14 Scout OTLP endpoint |
| `SCOUT_CLIENT_ID` | Yes | OAuth2 client ID from Base14 Scout |
| `SCOUT_CLIENT_SECRET` | Yes | OAuth2 client secret from Base14 Scout |
| `SCOUT_TOKEN_URL` | Yes | OAuth2 token endpoint |

**Example:**

```bash
export SCOUT_ENDPOINT=https://your-tenant.base14.io/v1/traces
export SCOUT_CLIENT_ID=your_client_id
export SCOUT_CLIENT_SECRET=your_client_secret
export SCOUT_TOKEN_URL=https://your-tenant.base14.io/oauth/token
```

See the
[Base14 Collector Setup Guide](https://docs.base14.io/category/opentelemetry-collector-setup)
for obtaining credentials.

### Application Environment Variables (compose.yaml)

| Variable | Default |
| -------- | ------- |
| `SPRING_APPLICATION_NAME` | `java-spring-boot-otel` |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `http/protobuf` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://otel-collector:4318` |

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

Requires PostgreSQL and OTel Collector running locally on standard ports.

```bash
./gradlew bootRun      # Run application
./gradlew test         # Run tests
./gradlew build        # Build JAR
```

Update `application.properties` to use `localhost:5432` for PostgreSQL.

### Docker Commands

```bash
docker-compose up --build        # Build and start
docker-compose down              # Stop all
docker-compose down -v           # Stop and remove volumes
docker logs spring-app -f        # View logs
docker-compose restart spring-service  # Restart app only
```

### Faster Development Loop

Run only PostgreSQL in Docker, app locally for quick iteration:

```bash
docker-compose up db -d    # Start PostgreSQL only
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
docker-compose ps           # Check PostgreSQL health
docker logs postgres-db     # View PostgreSQL logs
```

Wait for PostgreSQL healthcheck to complete before starting the app.

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

## Technology Stack

| Component | Version |
| --------- | ------- |
| Spring Boot | 3.5.8 |
| OpenTelemetry Instrumentation | 2.22.0 |
| OpenTelemetry SDK | 1.55.0 |
| PostgreSQL | 17.7 |
| OTel Collector | 0.140.0 |
| Gradle | 9.2.1 |
| Java | 25 |

## Resources

- [Spring Boot Auto-Instrumentation Guide][spring-boot-guide] - Base14 documentation
- [OpenTelemetry Java][otel-java] - OTel Java docs
- [Spring Boot Actuator][actuator] - Actuator reference
- [Base14 Scout][scout] - Observability platform

[spring-boot-guide]: https://docs.base14.io/instrument/apps/auto-instrumentation/spring-boot
[otel-java]: https://opentelemetry.io/docs/languages/java/
[actuator]: https://docs.spring.io/spring-boot/docs/current/reference/html/actuator.html
[scout]: https://base14.io/scout
