.PHONY: install dev check lint format test clean run docker-build docker-up docker-down test-api

install:
	uv sync

dev:
	uv sync --all-extras

check: lint typecheck test

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests

format:
	uv run ruff check --fix src tests
	uv run ruff format src tests

typecheck:
	uv run mypy src

test:
	uv run pytest

test-integration:
	uv run pytest -m integration

test-cov:
	uv run pytest --cov --cov-report=term-missing

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov __pycache__
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Runs the app on the host against the Postgres and collector that compose.yaml publishes,
# and Ollama on the host. .env is exported so the GenAI instrumentations read it too.
run:
	DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/sales_intelligence \
	OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 \
	OLLAMA_BASE_URL=http://localhost:11434 \
	uv run uvicorn sales_intelligence.main:app --reload --host 0.0.0.0 --port 8000 \
		$(if $(wildcard .env),--env-file .env)

audit:
	uv run pip-audit

outdated:
	uv pip list --outdated

docker-build:
	docker build -t ai-sales-intelligence .

docker-up:
	docker compose up -d

docker-down:
	docker compose down -v

test-api:
	./scripts/test-api.sh
