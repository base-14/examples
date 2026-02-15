.PHONY: build test clean dev docker-up docker-down docker-logs docker-build test-api verify-scout lint build-lint

build:
	bundle install

test:
	rails test

clean:
	rm -rf tmp/cache log/*.log

dev:
	rails server

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
	bundle exec rubocop

build-lint: build
	@echo "Running lint..."
	bundle exec rubocop
	rails test

.DEFAULT_GOAL := build
