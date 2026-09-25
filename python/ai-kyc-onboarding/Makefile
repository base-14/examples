.PHONY: install dev build check lint format typecheck test test-integration clean run run-worker docker-build docker-up docker-down outdated

install:
	uv sync

build: install

dev:
	uv sync --all-extras

check: lint typecheck test

lint:
	uv run ruff check src tests scripts
	uv run ruff format --check src tests scripts

format:
	uv run ruff check --fix src tests scripts
	uv run ruff format src tests scripts

typecheck:
	uv run mypy src scripts

test:
	uv run pytest -m "not integration"

test-integration:
	uv run pytest -m integration

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov __pycache__
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

run:
	uv run uvicorn kyc_onboarding.main:app --reload --host 0.0.0.0 --port 8000

run-worker:
	uv run python -m kyc_onboarding.worker

docker-build:
	docker build -t ai-kyc-onboarding .

docker-up:
	docker compose up -d

docker-down:
	docker compose down -v

outdated:
	uv pip list --outdated
