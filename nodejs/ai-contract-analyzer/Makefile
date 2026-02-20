.PHONY: install dev check lint format typecheck test test-api seed docker-build docker-up docker-down clean

install:
	bun install

dev:
	bun run --watch src/index.ts

check: lint typecheck test

lint:
	bunx biome check src tests

format:
	bunx biome format --write src tests

typecheck:
	tsc --noEmit

test:
	vitest run

test-watch:
	vitest

test-coverage:
	vitest run --coverage

test-api:
	./scripts/test-api.sh

seed:
	bun run scripts/seed-data.ts

db-migrate:
	bun run scripts/db-migrate.ts

docker-build:
	docker build -t ai-contract-analyzer .

docker-up:
	docker compose up -d

docker-down:
	docker compose down -v

clean:
	rm -rf dist node_modules .cache
