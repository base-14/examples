.PHONY: build test lint check clean docker-build docker-up docker-down test-api verify-scout

# This host runs a JDK that Gradle 9.2 does not support, so every Gradle task
# runs in the gradle:9.2.1-jdk25 image with the repo root mounted at /repo.
REPO_ROOT := $(abspath $(CURDIR)/../..)
GRADLE := docker run --rm \
	-v $(REPO_ROOT):/repo \
	-v ai-customer-support-gradle:/home/gradle/.gradle \
	-w /repo/java/ai-customer-support \
	gradle:9.2.1-jdk25 gradle --no-daemon

build:
	$(GRADLE) bootJar

test:
	$(GRADLE) test

lint:
	$(GRADLE) checkstyleMain checkstyleTest

check: lint build test

clean:
	$(GRADLE) clean

docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

test-api:
	./scripts/test-api.sh

verify-scout:
	./scripts/verify-scout.sh
