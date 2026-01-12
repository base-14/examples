.PHONY: all build test lint run clean docker-build docker-up docker-down help

# Go parameters
GOCMD=go
GOBUILD=$(GOCMD) build
GOTEST=$(GOCMD) test
GOVET=$(GOCMD) vet
GOMOD=$(GOCMD) mod
BINARY_API=bin/api
BINARY_WORKER=bin/worker

# Build flags
LDFLAGS=-ldflags "-s -w"
BUILD_FLAGS=-race

all: lint test build

## build: Build API and Worker binaries
build:
	@echo "Building API..."
	CGO_ENABLED=1 $(GOBUILD) $(BUILD_FLAGS) $(LDFLAGS) -o $(BINARY_API) ./cmd/api
	@echo "Building Worker..."
	CGO_ENABLED=1 $(GOBUILD) $(BUILD_FLAGS) $(LDFLAGS) -o $(BINARY_WORKER) ./cmd/worker

## build-prod: Build for production (no race detector)
build-prod:
	@echo "Building API (production)..."
	CGO_ENABLED=0 GOOS=linux $(GOBUILD) $(LDFLAGS) -o $(BINARY_API) ./cmd/api
	@echo "Building Worker (production)..."
	CGO_ENABLED=0 GOOS=linux $(GOBUILD) $(LDFLAGS) -o $(BINARY_WORKER) ./cmd/worker

## test: Run all tests
test:
	$(GOTEST) -v -race -cover ./...

## test-unit: Run unit tests only
test-unit:
	$(GOTEST) -v -race -short ./...

## test-integration: Run integration tests
test-integration:
	$(GOTEST) -v -race -run Integration ./...

## test-workflow: Run workflow-specific tests
test-workflow:
	$(GOTEST) -v -race ./tests/...

## lint: Run linter (must pass with zero warnings)
lint:
	@echo "Running golangci-lint..."
	golangci-lint run --timeout 5m
	@echo "Running go vet..."
	$(GOVET) ./...
	@echo "Checking for deprecated usage..."
	@! grep -rn "middleware.Timeout\|middleware.Logger()" internal/ cmd/ 2>/dev/null || (echo "ERROR: Deprecated middleware usage found!" && exit 1)
	@echo "Lint passed with zero warnings"

## fmt: Format code
fmt:
	$(GOCMD) fmt ./...
	@which goimports > /dev/null && goimports -w . || echo "goimports not installed, skipping"

## tidy: Tidy dependencies
tidy:
	$(GOMOD) tidy
	$(GOMOD) verify

## run-api: Run API server locally
run-api:
	$(GOCMD) run ./cmd/api

## run-worker: Run Temporal worker locally
run-worker:
	$(GOCMD) run ./cmd/worker

## docker-build: Build Docker images
docker-build:
	docker build -t go-temporal-api:latest -f Dockerfile .
	docker build -t go-temporal-worker:latest -f Dockerfile.worker .

## docker-up: Start all services with Docker Compose
docker-up:
	docker compose up -d

## docker-down: Stop all services
docker-down:
	docker compose down

## docker-logs: View logs
docker-logs:
	docker compose logs -f

## docker-clean: Remove containers and volumes
docker-clean:
	docker compose down -v --remove-orphans

## verify-scout: Verify Scout integration
verify-scout:
	./scripts/verify-scout.sh

## test-api: Run API integration tests
test-api:
	./scripts/test-api.sh

## test-workflows-e2e: Run workflow E2E tests
test-workflows-e2e:
	./scripts/test-workflows.sh

## clean: Clean build artifacts
clean:
	rm -rf bin/
	$(GOCMD) clean -cache

## deps: Download dependencies
deps:
	$(GOMOD) download

## update-deps: Update all dependencies to latest
update-deps:
	$(GOCMD) get -u ./...
	$(GOMOD) tidy

## generate: Run go generate
generate:
	$(GOCMD) generate ./...

## coverage: Generate test coverage report
coverage:
	$(GOTEST) -coverprofile=coverage.out ./...
	$(GOCMD) tool cover -html=coverage.out -o coverage.html
	@echo "Coverage report: coverage.html"

## help: Show this help
help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@sed -n 's/^##//p' $(MAKEFILE_LIST) | column -t -s ':' | sed -e 's/^/ /'

# Default target
.DEFAULT_GOAL := help
