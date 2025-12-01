.PHONY: build test clean run run-server run-cli run-both docker-up docker-down docker-build docker-logs test-api lint format build-lint

BINARY_NAME=parking-lot
MAIN_PACKAGE=./cmd/parking-lot

build:
	go build -o $(BINARY_NAME) $(MAIN_PACKAGE)

test:
	go test ./...

clean:
	go clean
	rm -f $(BINARY_NAME)

run: run-cli

run-cli: build
	./$(BINARY_NAME) --mode=cli

run-server: build
	./$(BINARY_NAME) --mode=server --port=8080

run-both: build
	./$(BINARY_NAME) --mode=both --port=8080

docker-build:
	docker-compose build

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f

test-api:
	./scripts/test-api.sh

lint:
	go vet ./...
	go fmt ./...

format:
	go fmt ./...

build-lint: build
	@echo "Running build and lint..."
	go vet ./...
	go fmt ./...
	go test ./...

.DEFAULT_GOAL := build