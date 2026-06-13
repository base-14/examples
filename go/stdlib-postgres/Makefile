.PHONY: check build lint vet fmt tidy test docker-build docker-up docker-down docker-logs test-api verify-scout

check: vet build test
	@echo "All checks passed."

build:
	@cd app && go build ./...
	@cd notify && go build ./...

test:
	@cd app && go test ./...
	@cd notify && go test ./...

vet:
	@cd app && go vet ./...
	@cd notify && go vet ./...

lint: vet
	@cd app && OUT="$$(gofmt -l .)"; test -z "$$OUT" || { echo "gofmt issues:"; echo "$$OUT"; exit 1; }
	@cd notify && OUT="$$(gofmt -l .)"; test -z "$$OUT" || { echo "gofmt issues:"; echo "$$OUT"; exit 1; }

fmt:
	@cd app && gofmt -w .
	@cd notify && gofmt -w .

tidy:
	@cd app && go mod tidy
	@cd notify && go mod tidy

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

.DEFAULT_GOAL := check
