FROM python:3.12-slim

WORKDIR /app

# Upgrade pip and install dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Create non-root user
RUN useradd -m -u 1000 loadgen && \
    chown -R loadgen:loadgen /app

# Copy load generator script
COPY loadgen.py .

# Make script executable
RUN chmod +x loadgen.py

# Switch to non-root user
USER loadgen

# Default configuration (can be overridden with environment variables)
ENV TARGET_URL=http://web:3000
ENV OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
ENV OTEL_SERVICE_NAME=hotel-food-loadgen
ENV REQUESTS_PER_SECOND=2
ENV DURATION_SECONDS=300

CMD ["python", "loadgen.py"]