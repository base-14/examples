.PHONY: build restore test clean format build-lint check up compose-up compose-down compose-logs test-api verify-scout

build:
	dotnet build AspirePostgres.sln -c Release

restore:
	dotnet restore AspirePostgres.sln

test:
	dotnet test AspirePostgres.sln

clean:
	dotnet clean AspirePostgres.sln
	rm -rf */bin */obj

format:
	dotnet format AspirePostgres.sln

build-lint: build
	@echo "Running format check..."
	dotnet format AspirePostgres.sln --verify-no-changes

check:
	dotnet build AspirePostgres.sln --no-restore

up:
	dotnet run --project AppHost/AppHost.csproj

compose-up:
	docker compose up -d --build

compose-down:
	docker compose down

compose-logs:
	docker compose logs -f

test-api:
	./scripts/test-api.sh

verify-scout:
	./scripts/verify-scout.sh

.DEFAULT_GOAL := build
