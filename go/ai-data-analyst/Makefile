.PHONY: build test lint check docker-build docker-up docker-down seed test-api

BINARY_NAME=ai-data-analyst
MAIN_PACKAGE=./cmd/server

build:
	go build -o $(BINARY_NAME) $(MAIN_PACKAGE)

test:
	go test ./...

lint:
	go vet ./...
	@test -z "$$(gofmt -l .)" || (echo "Files need formatting:" && gofmt -l . && exit 1)

check: lint test

docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down -v

seed:
	go run scripts/seed-data.go

test-api:
	./scripts/test-api.sh

.DEFAULT_GOAL := build
