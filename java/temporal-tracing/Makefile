.PHONY: build check clean docker-build docker-up docker-down docker-logs test-workflow verify-scout

build:
	mvn package -DskipTests -B

check:
	mvn verify -DskipTests -B

clean:
	mvn clean

docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

test-workflow:
	./scripts/test-workflow.sh

verify-scout:
	./scripts/verify-scout.sh

.DEFAULT_GOAL := build
