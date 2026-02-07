.PHONY: install dev build check lint format typecheck test clean run docker-build docker-up docker-down test-api verify-scout audit outdated eval eval-view

install:
	uv sync

build: install

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

run:
	uv run uvicorn content_quality.main:app --reload --host 0.0.0.0 --port 8000

audit:
	uv run pip-audit

outdated:
	uv pip list --outdated

docker-build:
	docker build -t ai-content-quality .

docker-up:
	docker compose up -d

docker-down:
	docker compose down -v

test-api:
	./scripts/test-api.sh

verify-scout:
	./scripts/verify-scout.sh

eval:
	npx promptfoo@latest eval --no-cache

eval-view:
	npx promptfoo@latest view
