.PHONY: test clean dev docker-up docker-down docker-logs docker-build test-api verify-scout lint format build-lint

test:
	python manage.py test

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov __pycache__
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

dev:
	python manage.py runserver

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
	ruff check apps tests
	ruff format --check apps tests

format:
	ruff check --fix apps tests
	ruff format apps tests

build-lint: lint
	@echo "Lint passed"
	python manage.py test

.DEFAULT_GOAL := test
