FROM gradle:9.2.1-jdk25 AS builder

ARG OTEL_AGENT_VERSION=2.31.1

WORKDIR /app

# Fetched here rather than with ADD so the layer caches and the download retries.
RUN curl -fsSL --retry 5 --retry-all-errors --retry-delay 5 \
    -o /app/opentelemetry-javaagent.jar \
    "https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/download/v${OTEL_AGENT_VERSION}/opentelemetry-javaagent.jar"

COPY build.gradle settings.gradle ./
COPY config/checkstyle ./config/checkstyle
COPY --from=shared pricing.json /app/_shared/pricing.json
COPY --from=shared test-vectors /app/_shared/test-vectors
COPY src ./src

RUN gradle bootJar --no-daemon

FROM eclipse-temurin:25-jre

# curl is here only so the container healthcheck has something to call.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --create-home app

WORKDIR /app

COPY --from=builder --chown=app:app /app/opentelemetry-javaagent.jar /app/opentelemetry-javaagent.jar

COPY --from=builder --chown=app:app /app/build/libs/ai-customer-support-0.0.1-SNAPSHOT.jar /app/app.jar

USER app
EXPOSE 8080

ENTRYPOINT ["java", \
  "-javaagent:/app/opentelemetry-javaagent.jar", \
  "-jar", "/app/app.jar"]
