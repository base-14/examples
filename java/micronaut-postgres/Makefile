.PHONY: build test check clean docker-up docker-down docker-logs docker-build test-api verify-scout

MODULES := app notify

build:
	for m in $(MODULES); do (cd $$m && ./gradlew build -x test) || exit 1; done

test:
	for m in $(MODULES); do (cd $$m && ./gradlew test) || exit 1; done

check:
	for m in $(MODULES); do (cd $$m && ./gradlew check -x test) || exit 1; done

clean:
	for m in $(MODULES); do (cd $$m && ./gradlew clean) || exit 1; done

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
