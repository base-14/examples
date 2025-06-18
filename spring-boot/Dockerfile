<<<<<<< HEAD
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
COPY --from=builder /app/build/libs/java-spring-boot-otlel-0.0.1-SNAPSHOT.jar /app/app.jar

# Expose port if needed
EXPOSE 8080

# Run the app
ENTRYPOINT ["java", "-Dotel.java.global-autoconfigure.enabled=true","-jar", "/app/app.jar"]
=======
# Runtime stage
FROM openjdk:17.0.1-jdk-slim

# Copy the built JAR from build stage
COPY build/libs/java-spring-boot-otlel-0.0.1-SNAPSHOT.jar app.jar

# Expose ports
EXPOSE 8080 8001

# Set the entry point
ENTRYPOINT ["java", "-Dotel.java.global-autoconfigure.enabled=true","-jar", "app.jar"]


>>>>>>> 5895e5f (Add all files to spring boot folder)
