.PHONY: build test check clean dev docker-up docker-down docker-logs docker-build test-api verify-scout build-lint

build:
	./mvnw package -DskipTests

test:
	./mvnw test

check:
	./mvnw verify -DskipTests -B

clean:
	./mvnw clean

dev:
	./mvnw quarkus:dev

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
	./mvnw verify -DskipTests

.DEFAULT_GOAL := build
