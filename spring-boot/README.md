<<<<<<< HEAD
# Spring Boot with OpenTelemetry
## Overview

This is a Spring Boot application instrumented with OpenTelemetry for distributed tracing and metrics collection. The application demonstrates:

- Distributed tracing with OpenTelemetry
- Metrics collection and export via OTLP
- Integration with Spring Boot Actuator
- Automatic instrumentation of web requests, JDBC, and JVM metrics

## Prerequisites

- Java 17 or higher
- Gradle 7.6 or higher
- Docker and Docker Compose (for running OpenTelemetry Collector)
- OpenTelemetry Collector (for receiving telemetry data)

### 1. Clone the repository

```bash
git clone https://github.com/base-14/examples.git .
cd java-spring-boot-otel
```



```bash
docker-compose up -d
```

### 3. Build and Run the Application

```bash
# Build the application
./gradlew clean build

# Run the application
./gradlew bootRun
```

### 4. Test the Application

#### Actuator Endpoints

- **Health**: `GET http://localhost:8080/actuator/health`
- **Metrics**: `GET http://localhost:8080/actuator/metrics`
- **Prometheus**: `GET http://localhost:8080/actuator/prometheus`

#### Unit Tests
```bash
# Run tests
./gradlew test
```
```

## Monitoring and Observability

### Metrics

The application exposes the following metrics:

- JVM metrics (memory, threads, GC, etc.)
- HTTP server metrics
- Database connection pool metrics

=======
# examples
>>>>>>> 5895e5f (Add all files to spring boot folder)
