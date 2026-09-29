FROM python:3.14-slim AS builder

ARG FILING_FRAMEWORK=strands

WORKDIR /app

RUN pip install --no-cache-dir uv==0.12.19

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --no-dev --frozen --no-install-project --extra "${FILING_FRAMEWORK}"

FROM python:3.14-slim AS runtime

ARG FILING_FRAMEWORK=strands

RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/* && \
    useradd --create-home --uid 10001 app

WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app src/ src/
COPY --chown=app:app prompts/ prompts/
COPY --chown=app:app fixtures/ fixtures/

ENV PATH=/app/.venv/bin:$PATH \
    PYTHONPATH=/app/src \
    FILING_FRAMEWORK=${FILING_FRAMEWORK}

USER app
EXPOSE 8000

CMD ["uvicorn", "filing_analyst.main:app", "--host", "0.0.0.0", "--port", "8000"]
