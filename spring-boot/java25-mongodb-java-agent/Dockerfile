# -------- Stage 1: Build the application --------
FROM gradle:9.2.1-jdk25 AS builder

COPY --chown=gradle:gradle . /app
WORKDIR /app

# Build the application (fat JAR)
RUN gradle build -x test --no-daemon

# -------- Stage 2: Create a minimal runtime image --------
FROM eclipse-temurin:25-jre
WORKDIR /app

# Download OpenTelemetry Java Agent
RUN apt-get update && apt-get install -y wget && \
  wget https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/download/v2.22.0/opentelemetry-javaagent.jar \
  -O /app/opentelemetry-javaagent.jar && \
  apt-get remove -y wget && \
  apt-get autoremove -y && \
  rm -rf /var/lib/apt/lists/*

# Copy the fat jar from the build stage
COPY --from=builder /app/build/libs/demo-0.0.1-SNAPSHOT.jar /app/app.jar

# Expose port if needed
EXPOSE 8080

# Run the app with Java Agent
ENTRYPOINT ["java", "-javaagent:/app/opentelemetry-javaagent.jar", "-jar", "/app/app.jar"]
