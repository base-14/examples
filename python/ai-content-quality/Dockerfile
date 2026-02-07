FROM python:3.14-slim

WORKDIR /app

# Install uv and curl (for healthcheck)
RUN pip install --no-cache-dir uv && \
    apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Copy dependency files and README (required by hatchling)
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --no-dev

# Copy source code and prompts
COPY src/ src/
COPY prompts/ prompts/

ENV PYTHONPATH=/app/src
EXPOSE 8000

CMD ["uv", "run", "uvicorn", "content_quality.main:app", "--host", "0.0.0.0", "--port", "8000"]
