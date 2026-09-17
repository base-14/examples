.PHONY: install dev build start check lint format typecheck test test-api verify measure index docker-build docker-up docker-down clean

install:
	npm install

dev:
	npm run dev

build:
	npm run build

start:
	npm run start

check: typecheck build lint test

lint:
	npm run lint

format:
	npm run format

typecheck:
	npm run typecheck

test:
	npm run test

test-api:
	npm run test:api

# Drives one planned run and one declined run, then checks the spans, the attributes
# and the six instruments against the collector's debug output. Needs the collector
# up; does not need Scout credentials.
verify:
	bash scripts/verify-scout.sh

# Runs the same request under TOOL_CATALOGUE=deferred and TOOL_CATALOGUE=full and
# prints the difference. Restarts the app twice and puts it back.
measure:
	bash scripts/measure-catalogue.sh

index:
	npm run index

# --build-context shared is the same named context compose.yaml declares. _shared/ sits at
# the repo root, outside this build context, and the image needs the price table in it.
docker-build:
	docker build --build-context shared=../../_shared -t ai-learning-path-planner .

docker-up:
	docker compose up -d

docker-down:
	docker compose down -v

clean:
	rm -rf dist node_modules coverage
