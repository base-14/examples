.PHONY: build test clean run docker-build docker-up docker-down docker-logs test-api verify-scout lint format check

build:
	cargo build --release --bin server

test:
	cargo test --all

clean:
	cargo clean
	rm -f target/release/server

run: build
	./target/release/server

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
	cargo clippy --all-targets -- -D warnings

format:
	cargo fmt

check:
	cargo check --all-targets
	cargo clippy --all-targets -- -D warnings
	cargo test

.DEFAULT_GOAL := build
