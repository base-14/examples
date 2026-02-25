.PHONY: build test lint check clean docker-build docker-up docker-down test-api verify-scout

build:
	./gradlew build -x test --no-daemon

test:
	./gradlew test --no-daemon

lint:
	./gradlew checkstyleMain 2>/dev/null || true

check: build test

clean:
	./gradlew clean --no-daemon

docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down -v

test-api:
	./scripts/test-api.sh

verify-scout:
	./scripts/verify-scout.sh
