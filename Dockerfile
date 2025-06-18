# Runtime stage
FROM openjdk:17.0.1-jdk-slim

# Copy the built JAR from build stage
COPY build/libs/java-spring-boot-otlel-0.0.1-SNAPSHOT.jar app.jar

# Expose ports
EXPOSE 8080 8001

# Set the entry point
ENTRYPOINT ["java", "-Dotel.java.global-autoconfigure.enabled=true","-jar", "app.jar"]


