.PHONY: install dev check lint format typecheck test test-integration test-cov \
        clean run audit outdated up down logs verify test-api

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
	uv run pytest -m "not integration"

test-integration:
	uv run pytest -m integration

test-cov:
	uv run pytest --cov --cov-report=term-missing

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov __pycache__
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

run:
	uv run uvicorn runbook_assistant.main:app --reload --host 0.0.0.0 --port 8000

audit:
	uv run pip-audit

outdated:
	uv pip list --outdated

up:
	docker compose up -d --build

down:
	docker compose down -v

logs:
	docker compose logs -f

verify:
	./scripts/verify-scout.sh

test-api:
	./scripts/test-api.sh
