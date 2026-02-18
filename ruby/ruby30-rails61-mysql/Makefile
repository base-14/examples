.PHONY: build clean docker-build docker-up docker-down docker-logs test-api verify-scout

build:
	bundle install

clean:
	rm -rf tmp/cache log/*.log

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

.DEFAULT_GOAL := build
