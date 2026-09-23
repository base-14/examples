.PHONY: build restore check format build-lint clean docker-build docker-up docker-down docker-logs test-api verify

build:
	dotnet build -c Release

restore:
	dotnet restore

check:
	dotnet build

format:
	dotnet format

build-lint: build
	dotnet format --verify-no-changes

clean:
	dotnet clean
	rm -rf bin obj

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

verify:
	./scripts/verify-otel.sh

.DEFAULT_GOAL := build
