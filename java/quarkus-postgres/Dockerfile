# Stage 1: Build
FROM maven:3.9-eclipse-temurin-21 AS builder
WORKDIR /app
COPY pom.xml .
RUN mvn dependency:go-offline -B
COPY src ./src
RUN mvn package -DskipTests -B

# Stage 2: Runtime
FROM eclipse-temurin:21-jre-alpine
WORKDIR /app

RUN addgroup -S appgroup && adduser -S appuser -G appgroup
USER appuser

COPY --from=builder /app/target/quarkus-app/lib/ /app/lib/
COPY --from=builder /app/target/quarkus-app/*.jar /app/
COPY --from=builder /app/target/quarkus-app/app/ /app/app/
COPY --from=builder /app/target/quarkus-app/quarkus/ /app/quarkus/

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/quarkus-run.jar"]
