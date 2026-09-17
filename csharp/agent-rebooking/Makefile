.PHONY: build restore test clean format build-lint check up down reset logs test-api verify-scout ci

build:
	dotnet build AgentRebooking.sln -c Release

restore:
	dotnet restore AgentRebooking.sln

test:
	dotnet test AgentRebooking.sln

clean:
	dotnet clean AgentRebooking.sln
	rm -rf */bin */obj

format:
	dotnet format AgentRebooking.sln

build-lint: build
	@echo "Running format check..."
	dotnet format AgentRebooking.sln --verify-no-changes

check:
	dotnet build AgentRebooking.sln --no-restore

up:
	docker compose up -d --build

# Leaves the Postgres volume in place; use `make reset` to drop it as well.
down:
	docker compose down

# Removes the Postgres volume as well. The seed only inserts rows that are not already
# there, so an edit to Seed.sql has no effect until the volume is gone.
reset:
	docker compose down -v

logs:
	docker compose logs -f

# Both scripts run standalone from scripts/ as well. These targets exist so the whole
# example is driveable from the Makefile; they add nothing but the invocation.
test-api:
	./scripts/test-api.sh

verify-scout:
	./scripts/verify-scout.sh

# Unchanged: ci is the three offline targets. test-api and verify-scout need a running
# stack and a local Ollama, so they stay out of it.
ci: check build-lint test

.DEFAULT_GOAL := build
