.PHONY: install dev build check check-all lint format typecheck test test-integration clean run docker-build docker-up docker-down fetch-fixtures check-fixtures outdated

# Each framework is its own uv extra with its own OpenTelemetry pins, so each gets its own
# virtual environment: make check FRAMEWORK=adk uses .venv-adk.
FRAMEWORK ?= strands
FRAMEWORKS := strands adk maf openai-agents
ADAPTERS := strands adk maf openai_agents
ADAPTER := $(subst -,_,$(FRAMEWORK))
empty :=
space := $(empty) $(empty)
OTHER_ADAPTERS := $(subst $(space),|,$(filter-out $(ADAPTER),$(ADAPTERS)))
UV_ENV := UV_PROJECT_ENVIRONMENT=.venv-$(FRAMEWORK)
UV_RUN := $(UV_ENV) uv run --extra $(FRAMEWORK) --extra dev

install:
	$(UV_ENV) uv sync --extra $(FRAMEWORK) --extra dev

build: install

dev: install

check: lint typecheck test

check-all:
	@for framework in $(FRAMEWORKS); do \
		$(MAKE) --no-print-directory check FRAMEWORK=$$framework || exit 1; \
	done

lint:
	$(UV_RUN) ruff check src tests scripts
	$(UV_RUN) ruff format --check src tests scripts

format:
	$(UV_RUN) ruff check --fix src tests scripts
	$(UV_RUN) ruff format src tests scripts

typecheck:
	$(UV_RUN) mypy src scripts --exclude 'frameworks/($(OTHER_ADAPTERS))(_faults)?\.py$$'

test:
	$(UV_RUN) pytest -m "not integration"

test-integration:
	$(UV_RUN) pytest -m integration

fetch-fixtures:
	./scripts/fetch-fixtures.sh

check-fixtures:
	$(UV_RUN) python -m filing_analyst.fixtures check

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov __pycache__
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

run:
	FILING_FRAMEWORK=$(FRAMEWORK) $(UV_RUN) uvicorn filing_analyst.main:app --reload --host 0.0.0.0 --port 8000

docker-build:
	docker build --build-arg FILING_FRAMEWORK=$(FRAMEWORK) -t ai-filing-analyst:$(FRAMEWORK) .

# Without FRAMEWORK on the command line, Compose takes FILING_FRAMEWORK from the shell or .env.
docker-up:
	$(if $(filter command line,$(origin FRAMEWORK)),FILING_FRAMEWORK=$(FRAMEWORK) )docker compose up -d --build

docker-down:
	docker compose down -v

outdated:
	$(UV_ENV) uv pip list --outdated
