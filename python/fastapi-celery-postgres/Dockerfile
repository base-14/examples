FROM python:3.13-slim

# Create non-root user early
RUN groupadd -r celeryuser && useradd -r -g celeryuser -m celeryuser

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Switch to non-root user for Poetry installation
USER celeryuser

# Install Poetry as non-root user
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="/home/celeryuser/.local/bin:$PATH"

# Copy poetry files
COPY --chown=celeryuser:celeryuser pyproject.toml poetry.lock* ./

# Install dependencies
RUN poetry install --no-root

# Copy application code
COPY --chown=celeryuser:celeryuser . .