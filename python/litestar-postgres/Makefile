SERVICES := app notify

.PHONY: help sync test lint format audit check \
        docker-build docker-up docker-down docker-logs docker-restart \
        test-api verify-scout clean

help:
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?##"} {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

sync: ## install/refresh deps for both services
	@for svc in $(SERVICES); do echo ">> uv sync $$svc"; (cd $$svc && uv sync); done

test: ## run pytest in both services
	@for svc in $(SERVICES); do echo ">> pytest $$svc"; (cd $$svc && uv run pytest) || exit 1; done

lint: ## ruff check + format check
	uv tool run ruff check $(addsuffix /src,$(SERVICES)) $(addsuffix /tests,$(SERVICES))
	uv tool run ruff format --check $(addsuffix /src,$(SERVICES)) $(addsuffix /tests,$(SERVICES))

format: ## ruff fix + format
	uv tool run ruff check --fix $(addsuffix /src,$(SERVICES)) $(addsuffix /tests,$(SERVICES))
	uv tool run ruff format $(addsuffix /src,$(SERVICES)) $(addsuffix /tests,$(SERVICES))

audit: ## pip-audit each service env for known CVEs
	@for svc in $(SERVICES); do echo ">> pip-audit $$svc"; (cd $$svc && uv run --with pip-audit pip-audit --strict) || exit 1; done

check: lint audit test ## lint + audit + test (run before commits)

docker-build: ## build all images
	docker compose build

docker-up: ## start the full stack detached
	docker compose up -d

docker-down: ## stop and remove containers + network
	docker compose down

docker-logs: ## tail logs from all services
	docker compose logs -f

docker-restart: docker-down docker-up ## quick recycle

test-api: ## hit live endpoints (requires docker-up)
	./scripts/test-api.sh

verify-scout: ## end-to-end Scout verification (requires Scout creds)
	./scripts/verify-scout.sh

clean: ## remove caches and venvs
	@for svc in $(SERVICES); do \
	  rm -rf $$svc/.venv $$svc/.pytest_cache $$svc/.ruff_cache $$svc/.mypy_cache; \
	  find $$svc -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true; \
	done

.DEFAULT_GOAL := help
