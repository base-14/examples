#!/bin/bash

# Verify OTel Collector across all example projects
#
# Runs test-api.sh and verify-scout.sh for each project, then prints a report.
# Use after bumping the collector version, upgrading dependencies, or adding
# new examples.
#
# Usage:
#   ./scripts/verify-collector-bump.sh                              # 1 per language (~20 min)
#   ./scripts/verify-collector-bump.sh --all                        # all projects (~90 min)
#   ./scripts/verify-collector-bump.sh python/fastapi-postgres ...  # specific projects
#
# Flow per project:
#   docker compose up -d --build → wait for collector health →
#   test-api.sh → verify-scout.sh → docker compose down -v
#
# Skips:
#   - Legacy projects (pinned old runtimes, not worth re-verifying)
#   - AI examples requiring LLM API keys (unless keys are set in env)

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
REPORT_FILE="$ROOT_DIR/scripts/.verify-report-$(date +%Y%m%d-%H%M%S).txt"
STARTUP_TIMEOUT=120

# Legacy projects — always skip
LEGACY_PROJECTS="go/go119-gin191-postgres ruby/ruby27-rails52-mysql8 php/php8-laravel8-sqlite"

# AI projects — skip unless LLM API keys are set
AI_PROJECTS="python/ai-sales-intelligence python/ai-content-quality nodejs/ai-contract-analyzer go/ai-data-analyst rust/ai-report-generator java/ai-customer-support"

# Representative projects (1 per language, for fast verification)
REPRESENTATIVE=(
  "python/fastapi-postgres"
  "nodejs/express5-postgres"
  "go/echo-postgres"
  "java/spring-boot-java25-postgresql"
  "kotlin/ktor-postgres"
  "rust/axum-postgres"
  "ruby/rails8-sqlite"
  "php/php85-laravel13-postgres"
  "csharp/dotnet-sqlserver"
  "elixir/phoenix18-ecto3-postgres"
)

# All non-legacy, non-AI projects
ALL_PROJECTS=(
  "python/fastapi-postgres"
  "python/fastapi-celery-postgres"
  "python/django-postgres"
  "python/flask-postgres"
  "nodejs/express-typescript-mongodb"
  "nodejs/express5-postgres"
  "nodejs/fastify-postgres"
  "nodejs/nestjs-postgres"
  "nodejs/nextjs-api-mongodb"
  "go/echo-postgres"
  "go/fiber-postgres"
  "go/go-temporal-postgres"
  "java/spring-boot-java25-postgresql"
  "java/spring-boot-java25-mongodb-java-agent"
  "java/spring-boot-java17-mysql"
  "java/quarkus-postgres"
  "java/micronaut-postgres"
  "kotlin/ktor-postgres"
  "rust/axum-postgres"
  "ruby/rails8-sqlite"
  "ruby/ruby30-rails61-mysql"
  "php/php85-laravel13-postgres"
  "php/php84-slim4-mongodb"
  "php/php84-slim3-mongodb"
  "php/symfony-mysql"
  "csharp/dotnet-sqlserver"
  "elixir/phoenix18-ecto3-postgres"
)

# ──────────────────────────────────────────────────────────
# Parse arguments
# ──────────────────────────────────────────────────────────
MODE="representative"
CUSTOM_PROJECTS=()

for arg in "$@"; do
  case "$arg" in
    --all)
      MODE="all"
      ;;
    --help|-h)
      echo "Usage: $0 [--all] [project/path ...]"
      echo ""
      echo "Modes:"
      echo "  (no args)          Run 1 representative project per language (~20 min)"
      echo "  --all              Run all non-legacy, non-AI projects (~90 min)"
      echo "  project/path ...   Run only the specified projects"
      echo ""
      echo "Examples:"
      echo "  $0                                          # fast, 1 per language"
      echo "  $0 --all                                    # full suite"
      echo "  $0 python/fastapi-postgres go/echo-postgres # just these two"
      exit 0
      ;;
    *)
      MODE="custom"
      CUSTOM_PROJECTS+=("$arg")
      ;;
  esac
done

case "$MODE" in
  all)    PROJECTS=("${ALL_PROJECTS[@]}") ;;
  custom) PROJECTS=("${CUSTOM_PROJECTS[@]}") ;;
  *)      PROJECTS=("${REPRESENTATIVE[@]}") ;;
esac

# ──────────────────────────────────────────────────────────
# Results tracking
# ──────────────────────────────────────────────────────────
declare -a RESULTS_PROJECT
declare -a RESULTS_API
declare -a RESULTS_SCOUT
declare -a RESULTS_NOTES
TOTAL=0
API_PASS=0
API_FAIL=0
API_SKIP=0
SCOUT_PASS=0
SCOUT_FAIL=0
SCOUT_SKIP=0

cleanup() {
  local project_dir="$1"
  cd "$project_dir"
  if [ -f "docker-compose.yml" ]; then
    docker compose -f docker-compose.yml down -v --remove-orphans >/dev/null 2>&1 || true
  else
    docker compose down -v --remove-orphans >/dev/null 2>&1 || true
  fi
  cd "$ROOT_DIR"
}

wait_for_healthy() {
  local elapsed=0
  local health_url="http://localhost:13133/"
  while [ $elapsed -lt $STARTUP_TIMEOUT ]; do
    if curl -sf "$health_url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 3
    elapsed=$((elapsed + 3))
  done
  return 1
}

run_project() {
  local project="$1"
  local project_dir="$ROOT_DIR/$project"
  local api_result="SKIP"
  local scout_result="SKIP"
  local notes=""

  TOTAL=$((TOTAL + 1))

  echo ""
  echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
  echo -e "${BOLD}[$TOTAL/${#PROJECTS[@]}] $project${NC}"
  echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

  if [ ! -d "$project_dir" ]; then
    notes="directory not found"
    echo -e "${RED}  SKIP: $notes${NC}"
    RESULTS_PROJECT+=("$project")
    RESULTS_API+=("SKIP")
    RESULTS_SCOUT+=("SKIP")
    RESULTS_NOTES+=("$notes")
    API_SKIP=$((API_SKIP + 1))
    SCOUT_SKIP=$((SCOUT_SKIP + 1))
    return
  fi

  cd "$project_dir"

  local compose_cmd="docker compose"
  if [ -f "docker-compose.yml" ] && [ ! -f "compose.yml" ]; then
    compose_cmd="docker compose -f docker-compose.yml"
  fi

  echo -e "  ${YELLOW}Starting services...${NC}"
  if ! $compose_cmd up -d --build 2>&1 | tail -5; then
    notes="docker compose up failed"
    echo -e "  ${RED}FAIL: $notes${NC}"
    cleanup "$project_dir"
    RESULTS_PROJECT+=("$project")
    RESULTS_API+=("FAIL")
    RESULTS_SCOUT+=("SKIP")
    RESULTS_NOTES+=("$notes")
    API_FAIL=$((API_FAIL + 1))
    SCOUT_SKIP=$((SCOUT_SKIP + 1))
    return
  fi

  echo -e "  ${YELLOW}Waiting for collector...${NC}"
  if ! wait_for_healthy; then
    notes="collector health timeout (${STARTUP_TIMEOUT}s)"
    echo -e "  ${RED}FAIL: $notes${NC}"
    cleanup "$project_dir"
    RESULTS_PROJECT+=("$project")
    RESULTS_API+=("FAIL")
    RESULTS_SCOUT+=("SKIP")
    RESULTS_NOTES+=("$notes")
    API_FAIL=$((API_FAIL + 1))
    SCOUT_SKIP=$((SCOUT_SKIP + 1))
    return
  fi

  sleep 5

  # Run test-api.sh
  if [ -f "scripts/test-api.sh" ]; then
    echo -e "  ${YELLOW}Running test-api.sh...${NC}"
    if bash scripts/test-api.sh > /tmp/verify-api-$$.log 2>&1; then
      api_result="PASS"
      API_PASS=$((API_PASS + 1))
      echo -e "  ${GREEN}✓ test-api.sh passed${NC}"
    else
      api_result="FAIL"
      API_FAIL=$((API_FAIL + 1))
      notes="test-api.sh failed"
      echo -e "  ${RED}✗ test-api.sh failed${NC}"
      tail -5 /tmp/verify-api-$$.log 2>/dev/null | sed 's/^/    /'
    fi
  else
    echo -e "  ${YELLOW}  No test-api.sh found${NC}"
    API_SKIP=$((API_SKIP + 1))
  fi

  sleep 10

  # Run verify-scout.sh
  if [ -f "scripts/verify-scout.sh" ]; then
    echo -e "  ${YELLOW}Running verify-scout.sh...${NC}"
    if bash scripts/verify-scout.sh > /tmp/verify-scout-$$.log 2>&1; then
      scout_result="PASS"
      SCOUT_PASS=$((SCOUT_PASS + 1))
      echo -e "  ${GREEN}✓ verify-scout.sh passed${NC}"
    else
      scout_result="FAIL"
      SCOUT_FAIL=$((SCOUT_FAIL + 1))
      if [ -z "$notes" ]; then
        notes="verify-scout.sh failed"
      else
        notes="$notes; verify-scout.sh failed"
      fi
      echo -e "  ${RED}✗ verify-scout.sh failed${NC}"
      tail -10 /tmp/verify-scout-$$.log 2>/dev/null | sed 's/^/    /'
    fi

    grep -E "(Passed|Failed|✓|✗)" /tmp/verify-scout-$$.log 2>/dev/null | tail -20 >> "$REPORT_FILE.detail" 2>/dev/null || true
    echo "---" >> "$REPORT_FILE.detail" 2>/dev/null || true
  else
    echo -e "  ${YELLOW}  No verify-scout.sh found${NC}"
    SCOUT_SKIP=$((SCOUT_SKIP + 1))
  fi

  echo -e "  ${YELLOW}Stopping services...${NC}"
  cleanup "$project_dir"

  RESULTS_PROJECT+=("$project")
  RESULTS_API+=("$api_result")
  RESULTS_SCOUT+=("$scout_result")
  RESULTS_NOTES+=("${notes:-ok}")
}

print_report() {
  echo ""
  echo ""
  echo -e "${BOLD}╔══════════════════════════════════════════════════════════════════════════╗${NC}"
  echo -e "${BOLD}║              OTel Collector Verification Report                         ║${NC}"
  echo -e "${BOLD}║              $(date '+%Y-%m-%d %H:%M:%S')                                        ║${NC}"
  echo -e "${BOLD}╠══════════════════════════════════════════════════════════════════════════╣${NC}"
  echo ""

  printf "  %-40s  %-10s  %-12s  %s\n" "Project" "API Test" "Scout Check" "Notes"
  printf "  %-40s  %-10s  %-12s  %s\n" "────────────────────────────────────────" "──────────" "────────────" "──────────────"

  local i=0
  for project in "${RESULTS_PROJECT[@]}"; do
    local api="${RESULTS_API[$i]}"
    local scout="${RESULTS_SCOUT[$i]}"
    local note="${RESULTS_NOTES[$i]}"

    local api_colored scout_colored
    case "$api" in
      PASS) api_colored="${GREEN}PASS${NC}" ;;
      FAIL) api_colored="${RED}FAIL${NC}" ;;
      SKIP) api_colored="${YELLOW}SKIP${NC}" ;;
    esac
    case "$scout" in
      PASS) scout_colored="${GREEN}PASS${NC}" ;;
      FAIL) scout_colored="${RED}FAIL${NC}" ;;
      SKIP) scout_colored="${YELLOW}SKIP${NC}" ;;
    esac

    printf "  %-40s  " "$project"
    printf "%-10b  " "$api_colored"
    printf "%-12b  " "$scout_colored"
    echo "$note"

    i=$((i + 1))
  done

  echo ""
  echo -e "${BOLD}  Summary${NC}"
  echo "  ─────────────────────────────────────"
  echo -e "  API Tests:    ${GREEN}$API_PASS passed${NC}  ${RED}$API_FAIL failed${NC}  ${YELLOW}$API_SKIP skipped${NC}"
  echo -e "  Scout Checks: ${GREEN}$SCOUT_PASS passed${NC}  ${RED}$SCOUT_FAIL failed${NC}  ${YELLOW}$SCOUT_SKIP skipped${NC}"
  echo ""

  if [ $API_FAIL -eq 0 ] && [ $SCOUT_FAIL -eq 0 ]; then
    echo -e "  ${GREEN}${BOLD}ALL CHECKS PASSED${NC}"
  else
    echo -e "  ${RED}${BOLD}SOME CHECKS FAILED — review output above${NC}"
  fi

  echo ""
  echo -e "${BOLD}╚══════════════════════════════════════════════════════════════════════════╝${NC}"

  {
    echo "OTel Collector Verification Report"
    echo "Date: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "Mode: $MODE (${#PROJECTS[@]} projects)"
    echo ""
    printf "%-40s  %-10s  %-12s  %s\n" "Project" "API Test" "Scout Check" "Notes"
    printf "%-40s  %-10s  %-12s  %s\n" "────────────────────────────────────────" "──────────" "────────────" "──────────────"
    local j=0
    for project in "${RESULTS_PROJECT[@]}"; do
      printf "%-40s  %-10s  %-12s  %s\n" "$project" "${RESULTS_API[$j]}" "${RESULTS_SCOUT[$j]}" "${RESULTS_NOTES[$j]}"
      j=$((j + 1))
    done
    echo ""
    echo "API Tests:    $API_PASS passed  $API_FAIL failed  $API_SKIP skipped"
    echo "Scout Checks: $SCOUT_PASS passed  $SCOUT_FAIL failed  $SCOUT_SKIP skipped"
  } > "$REPORT_FILE"

  echo ""
  echo "  Report saved to: $REPORT_FILE"
}

# ──────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────
echo -e "${BOLD}OTel Collector Verification${NC}"
echo -e "Mode: ${CYAN}$MODE${NC} (${#PROJECTS[@]} projects)"
echo ""

touch "$REPORT_FILE.detail" 2>/dev/null || true

for project in "${PROJECTS[@]}"; do
  run_project "$project"
done

print_report
