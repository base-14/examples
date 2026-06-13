.PHONY: build test clean run lint format check

build:
	cargo build --release

test:
	cargo test --all

clean:
	cargo clean

run: build
	./target/release/hello-world-rust

lint:
	cargo clippy --all-targets -- -D warnings

format:
	cargo fmt

check:
	cargo check --all-targets
	cargo clippy --all-targets -- -D warnings
	cargo test

.DEFAULT_GOAL := build
