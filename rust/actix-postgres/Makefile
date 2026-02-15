.PHONY: build build-api build-worker test clean run run-api run-worker docker-up docker-down docker-logs docker-build test-api verify-scout lint format build-lint check

build: build-api build-worker

build-api:
	cargo build --release --bin api

build-worker:
	cargo build --release --bin worker

test:
	cargo test --all

clean:
	cargo clean
	rm -f target/release/api target/release/worker

run: run-api

run-api: build-api
	./target/release/api

run-worker: build-worker
	./target/release/worker

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

lint:
	cargo clippy --all-targets

format:
	cargo fmt

check:
	cargo check --all-targets

build-lint: build
	@echo "Running build and lint..."
	cargo clippy --all-targets
	cargo fmt --check
	cargo test --all

.DEFAULT_GOAL := build
