# -------- Stage 1: Build the application --------
FROM gradle:8.4.0-jdk17 AS builder

COPY --chown=gradle:gradle . /app
WORKDIR /app

# Build the application (fat JAR)
RUN gradle build --no-daemon

# -------- Stage 2: Create a minimal runtime image --------
FROM eclipse-temurin
WORKDIR /app

# Copy the fat jar from the build stage
COPY --from=builder /app/build/libs/java-spring-boot-otel-0.0.1-SNAPSHOT.jar /app/app.jar

# Expose port if needed
EXPOSE 8080

# Run the app
ENTRYPOINT ["java", "-Dotel.java.global-autoconfigure.enabled=true", "-jar", "/app/app.jar"]
