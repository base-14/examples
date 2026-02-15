.PHONY: test clean dev docker-up docker-down docker-logs docker-build test-api verify-scout build-lint

test:
	pytest

clean:
	rm -rf .pytest_cache .coverage htmlcov __pycache__
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

dev:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

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

build-lint:
	@echo "Running tests..."
	pytest

.DEFAULT_GOAL := test
