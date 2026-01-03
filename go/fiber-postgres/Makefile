.PHONY: build build-api build-worker test clean run run-api run-worker docker-up docker-down docker-logs docker-build test-api lint format build-lint tidy

build: build-api build-worker

build-api:
	go build -o api ./cmd/api

build-worker:
	go build -o worker ./cmd/worker

test:
	go test ./...

clean:
	go clean
	rm -f api worker

run: run-api

run-api: build-api
	./api

run-worker: build-worker
	./worker

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

lint:
	go vet ./...
	gofmt -l .

format:
	gofmt -w .

tidy:
	go mod tidy

build-lint: build
	@echo "Running build and lint..."
	go vet ./...
	gofmt -w .
	go mod tidy
	go test ./...

.DEFAULT_GOAL := build
