#!/usr/bin/env bash
# Refreshes the fixture cache from the SEC: the ticker list and the company facts of the
# companies in fixtures/companies.txt. Needs SEC_USER_AGENT, a name and contact email, from
# the environment or .env. Refreshed figures can differ from the verified docs page.
#
# Usage: scripts/fetch-fixtures.sh
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -z "${SEC_USER_AGENT:-}" && -f .env ]]; then
  SEC_USER_AGENT="$(grep -E '^SEC_USER_AGENT=' .env | tail -1 | cut -d= -f2-)"
  export SEC_USER_AGENT
fi

# The SEC client needs OpenTelemetry, which each framework extra installs; Strands is enough.
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-.venv-strands}"
uv run --extra strands python -m scripts.fetch_fixtures
uv run --extra strands python -m filing_analyst.fixtures check
