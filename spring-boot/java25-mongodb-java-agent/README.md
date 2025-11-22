# Spring Boot with OpenTelemetry - Java Agent Approach

Spring Boot 3.5.8 application with OpenTelemetry instrumentation using the
**Java Agent** approach.

> 📚 [Full Documentation](https://docs.base14.io/instrument/apps/auto-instrumentation/spring-boot-alternatives#java-agent-approach)

## Instrumentation Approach

This example uses **OpenTelemetry Java Agent** (zero-code instrumentation):

- Attach: `-javaagent:/path/to/opentelemetry-javaagent.jar`
- No code changes or OTel dependencies required
- Configuration via environment variables only
- Automatic instrumentation of 150+ libraries

### What's Auto-Instrumented

- ✅ HTTP requests and responses (Spring MVC)
- ✅ MongoDB queries and operations
- ✅ JVM metrics (memory, threads, GC)
- ✅ Distributed trace propagation (W3C)
- ✅ Logback logging with trace correlation
- ✅ Custom methods with `@WithSpan` annotations

### Key Differences from SDK Integration

**Advantages:**

- Zero code changes required
- No dependency management needed
- Works with legacy applications
- Comprehensive auto-instrumentation

**Limitations:**

- Configuration via environment variables only (no application.properties support)
- Not compatible with GraalVM native-image
- May conflict with other JVM agents

## Custom Instrumentation

Add custom spans using `@WithSpan` annotations for deeper application visibility.

1. Add dependency to `build.gradle`:

   ```gradle
   implementation 'io.opentelemetry.instrumentation:opentelemetry-instrumentation-annotations:2.10.0'
   ```

1. Enable annotations (already configured in `compose.yaml`):

   ```yaml
   OTEL_INSTRUMENTATION_ANNOTATIONS_ENABLED: true
   ```

1. Annotate methods:

   ```java
   import io.opentelemetry.instrumentation.annotations.WithSpan;

   @WithSpan("UserService.save")
   public User save(User user) {
       return userRepository.save(user);
   }
   ```

## Prerequisites

- Docker Desktop or Docker Engine with Compose
- Base14 Scout credentials ([setup guide](https://docs.base14.io/category/opentelemetry-collector-setup))
- Java 25+ (only for local development without Docker)

## Quick Start

```bash
# Clone and navigate
git clone https://github.com/base-14/examples.git
cd examples/spring-boot/java25-mongodb-java-agent

# Set Base14 Scout credentials as environment variables
export SCOUT_ENDPOINT=https://your-tenant.base14.io/v1/traces
export SCOUT_CLIENT_ID=your_client_id
export SCOUT_CLIENT_SECRET=your_client_secret
export SCOUT_TOKEN_URL=https://your-tenant.base14.io/oauth/token

# Start application (MongoDB + Spring Boot + OTel Collector)
docker-compose up --build -d

# Verify it's running
curl http://localhost:8080/actuator/health
curl http://localhost:8080/users/testMessage
```

The app runs on port `8080`, MongoDB on `27017`, OTel Collector on `4317/4318`.

### Verify Java Agent Loaded

Check the application logs for the agent startup message:

```bash
docker logs spring-app | grep otel.javaagent
```

You should see: `[otel.javaagent] OpenTelemetry Javaagent 2.10.0`

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

Java Agent uses **environment variables only** for configuration:

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `OTEL_SERVICE_NAME` | `java-spring-boot-otel-mongodb` | Service identifier |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | `http/protobuf` | OTLP protocol |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://otel-collector:4318` | Collector URL |
| `OTEL_TRACES_EXPORTER` | `otlp` | Trace exporter |
| `OTEL_METRICS_EXPORTER` | `otlp` | Metrics exporter |
| `OTEL_LOGS_EXPORTER` | `otlp` | Logs exporter |
| `OTEL_INSTRUMENTATION_ANNOTATIONS_ENABLED` | `true` | @WithSpan support |

### Resource Attributes

Automatically included in telemetry:

```properties
service.name=java-spring-boot-otel-mongodb
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

Requires MongoDB and OTel Collector running locally on standard ports.

Download the Java Agent first:

```bash
wget https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/download/v2.22.0/opentelemetry-javaagent.jar
```

Then run with the agent:

```bash
# Set required environment variables
export OTEL_SERVICE_NAME=java-spring-boot-otel-mongodb
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OTEL_TRACES_EXPORTER=otlp
export OTEL_METRICS_EXPORTER=otlp
export OTEL_LOGS_EXPORTER=otlp
export SPRING_DATA_MONGODB_URI=mongodb://localhost:27017/company

# Build and run
./gradlew build
java -javaagent:./opentelemetry-javaagent.jar -jar build/libs/demo-0.0.1-SNAPSHOT.jar
```

Update `application.properties` to use `mongodb://localhost:27017/company`.

### Docker Commands

```bash
docker-compose up --build        # Build and start
docker-compose down              # Stop all
docker-compose down -v           # Stop and remove volumes
docker logs spring-app -f        # View logs
docker-compose restart spring-service  # Restart app only
```

### Faster Development Loop

Run only MongoDB in Docker, app locally for quick iteration:

```bash
docker-compose up mongodb -d    # Start MongoDB only
# Run app locally with Java Agent (see above)
```

## Telemetry Data

### Traces

- HTTP requests (method, URL, status)
- MongoDB queries and operations
- Exceptions and stack traces

### Metrics

- **HTTP**: Request count, duration, errors
- **JVM**: Memory, GC, threads
- **MongoDB**: Connection pool, operation duration
- **Process**: CPU, file descriptors

### Logs

All logs include `trace_id` and `span_id` for correlation.

## Troubleshooting

### Java Agent not loaded

Check startup logs for the agent message:

```bash
docker logs spring-app | grep otel.javaagent
```

Expected: `[otel.javaagent] OpenTelemetry Javaagent 2.22.0`

If missing, verify the agent path in Dockerfile and ENTRYPOINT.

### Collector connection failed

```bash
docker ps | grep otel-collector  # Check collector is running
docker logs otel-collector       # View collector logs
```

Ensure `OTEL_EXPORTER_OTLP_ENDPOINT` points to the correct collector address.

### No telemetry data

```bash
docker logs spring-app | grep -i otel  # Check app logs
```

Verify:

- Java Agent loaded successfully
- Environment variables are set correctly
- Collector is receiving data (check collector debug logs)

### MongoDB connection failed

```bash
docker-compose ps           # Check MongoDB health
docker logs mongodb         # View MongoDB logs
```

Wait for MongoDB healthcheck to complete before starting the app.

### Enable debug logging

Add to `compose.yaml` environment:

```yaml
environment:
  OTEL_LOG_LEVEL: DEBUG
```

## Technology Stack

| Component | Version |
| --------- | ------- |
| Spring Boot | 3.5.8 |
| OpenTelemetry Java Agent | 2.22.0 |
| MongoDB | 7.0 |
| OTel Collector | 0.140.0 |
| Gradle | 9.2.1 |
| Java | 25 |

## Resources

- [Java Agent Approach Guide][java-agent] - Base14 documentation
- [OpenTelemetry Java Agent][otel-agent] - Official Java Agent docs
- [Spring Boot Actuator][actuator] - Actuator reference
- [Base14 Scout][scout] - Observability platform

[java-agent]: https://docs.base14.io/instrument/apps/auto-instrumentation/spring-boot-alternatives#java-agent-approach
[otel-agent]: https://opentelemetry.io/docs/languages/java/automatic/
[actuator]: https://docs.spring.io/spring-boot/docs/current/reference/html/actuator.html
[scout]: https://base14.io/scout
