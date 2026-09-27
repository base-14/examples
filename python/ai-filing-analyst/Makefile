.PHONY: install dev build check lint format typecheck test test-integration clean run docker-build docker-up docker-down fetch-fixtures check-fixtures outdated

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

fetch-fixtures:
	./scripts/fetch-fixtures.sh

check-fixtures:
	uv run python -m filing_analyst.fixtures check

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov __pycache__
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

run:
	uv run uvicorn filing_analyst.main:app --reload --host 0.0.0.0 --port 8000

docker-build:
	docker build -t ai-filing-analyst .

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down -v

outdated:
	uv pip list --outdated
