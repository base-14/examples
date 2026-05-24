FROM eclipse-temurin:24-jdk AS builder
WORKDIR /app
COPY gradle/ gradle/
COPY gradlew settings.gradle.kts build.gradle.kts ./
RUN chmod +x gradlew && ./gradlew dependencies --no-daemon
COPY src/ src/
RUN ./gradlew shadowJar --no-daemon

FROM eclipse-temurin:24-jre
WORKDIR /app
RUN apt-get update -qq && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
ARG OTEL_AGENT_VERSION=2.28.1
ADD https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/download/v${OTEL_AGENT_VERSION}/opentelemetry-javaagent.jar /app/opentelemetry-javaagent.jar
RUN addgroup --gid 1001 appgroup && \
    adduser --uid 1001 --gid 1001 --disabled-password --gecos "" appuser && \
    chown appuser:appgroup /app/opentelemetry-javaagent.jar
COPY --from=builder --chown=appuser:appgroup /app/build/libs/notify.jar /app/notify.jar
USER appuser
EXPOSE 8081
ENV JAVA_TOOL_OPTIONS="-javaagent:/app/opentelemetry-javaagent.jar"
ENTRYPOINT ["java", "-jar", "/app/notify.jar"]
