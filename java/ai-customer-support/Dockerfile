FROM gradle:9.2.1-jdk25 AS builder

WORKDIR /app
COPY build.gradle settings.gradle ./
COPY gradle ./gradle
COPY src ./src

RUN gradle build -x test --no-daemon

FROM eclipse-temurin:25-jre

WORKDIR /app

ADD https://github.com/open-telemetry/opentelemetry-java-instrumentation/releases/download/v2.25.0/opentelemetry-javaagent.jar /app/opentelemetry-javaagent.jar

COPY --from=shared pricing.json /app/pricing.json

COPY --from=builder /app/build/libs/ai-customer-support-0.0.1-SNAPSHOT.jar /app/app.jar

EXPOSE 8080

ENTRYPOINT ["java", \
  "-javaagent:/app/opentelemetry-javaagent.jar", \
  "-jar", "/app/app.jar"]
