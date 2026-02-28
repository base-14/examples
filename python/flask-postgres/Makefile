.PHONY: test clean dev docker-up docker-down docker-logs docker-build test-api verify-scout lint format typecheck check

test:
	pytest

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov __pycache__
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

dev:
	flask run --reload

docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

test-api:
	./scripts/test-api.sh

verify-scout:
	./scripts/verify-scout.sh

lint:
	ruff check app tests
	ruff format --check app tests

format:
	ruff check --fix app tests
	ruff format app tests

typecheck:
	mypy app

check: lint typecheck test

.DEFAULT_GOAL := test
