.PHONY: build test clean dev docker-up docker-down docker-logs docker-build test-api verify-scout lint format build-lint

build:
	npm run build

test:
	npm test

clean:
	rm -rf dist coverage test-results node_modules

dev:
	npm run dev

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
	npm run lint

format:
	npm run format

build-lint: build
	@echo "Running build and lint..."
	npm run lint
	npm test

.DEFAULT_GOAL := build
