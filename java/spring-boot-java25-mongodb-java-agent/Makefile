.PHONY: build test clean dev docker-up docker-down docker-logs docker-build test-api verify-scout build-lint

build:
	./gradlew build -x test

test:
	./gradlew test

clean:
	./gradlew clean

dev:
	./gradlew bootRun

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

build-lint: build
	@echo "Build completed successfully"
	./gradlew check -x test

.DEFAULT_GOAL := build
