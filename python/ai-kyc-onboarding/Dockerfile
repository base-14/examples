FROM python:3.14-slim AS builder

WORKDIR /app

RUN pip install --no-cache-dir uv==0.12.18

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --no-dev --frozen --no-install-project

FROM python:3.14-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/* && \
    useradd --create-home --uid 10001 app

WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app src/ src/
COPY --chown=app:app prompts/ prompts/

ENV PATH=/app/.venv/bin:$PATH \
    PYTHONPATH=/app/src

USER app
EXPOSE 8000

CMD ["uvicorn", "kyc_onboarding.main:app", "--host", "0.0.0.0", "--port", "8000"]
