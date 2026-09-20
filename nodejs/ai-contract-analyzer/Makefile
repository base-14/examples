.PHONY: install dev build check lint format typecheck test test-watch test-coverage test-api verify seed db-migrate docker-build docker-up docker-down clean

install:
	bun install

dev:
	bun run --watch --preload ./src/telemetry.ts src/index.ts

build:
	bun build src/index.ts --outdir dist --target bun

check: lint typecheck build test

lint:
	bunx biome check src tests

format:
	bunx biome format --write src tests

typecheck:
	bunx tsc --noEmit

test:
	bunx vitest run

test-watch:
	bunx vitest

test-coverage:
	bunx vitest run --coverage

test-api:
	./scripts/test-api.sh

verify:
	./scripts/verify-scout.sh

seed:
	bun run scripts/seed-data.ts

db-migrate:
	bun run scripts/db-migrate.ts

docker-build:
	docker build --build-context shared=../../_shared -t ai-contract-analyzer .

docker-up:
	docker compose up -d

docker-down:
	docker compose down -v

clean:
	rm -rf dist node_modules .cache
