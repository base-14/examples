.PHONY: build build-api build-worker test clean run docker-up docker-down docker-logs docker-build test-api build-lint check restore

build: build-api build-worker

build-api:
	dotnet build src/Api/Api.csproj -c Release

build-worker:
	dotnet build src/Worker/Worker.csproj -c Release

restore:
	dotnet restore

test:
	dotnet test

clean:
	dotnet clean
	rm -rf src/Api/bin src/Api/obj
	rm -rf src/Worker/bin src/Worker/obj

run: build-api
	dotnet run --project src/Api/Api.csproj

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

build-lint: build
	@echo "Running build and format check..."
	dotnet format --verify-no-changes
	dotnet test

check:
	dotnet build --no-restore

format:
	dotnet format

.DEFAULT_GOAL := build
