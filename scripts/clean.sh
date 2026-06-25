#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Legacy projects to skip (parity with upgrade-deps.sh)
SKIP_PROJECTS="go119-gin191-postgres|ruby27-rails52-mysql8|php8-laravel8-sqlite"

# Top-level dirs whose immediate children are projects.
CONTAINER_DIRS="nodejs python go rust java csharp ruby php kotlin bun elixir flutter components iot"
# Dirs that are themselves a single project.
STANDALONE_DIRS="astronomy_shop_mobile aws-cloudwatch-stream loadgen scout-collector"

# Sourced before each reset so compose files that require Scout env vars
# (e.g. ${SCOUT_OTLP_ENDPOINT:?...}) can be interpolated for `docker compose down`.
SCOUT_ENV="${SCOUT_OTLP_CONFIG:-$HOME/.config/base14/scout-otel-config.env}"

LANGUAGE="all"
DRY_RUN=false
CLEAN_ONLY=false
RESET_ONLY=false
PRUNE_IMAGES=false

usage() {
  echo "Usage: $0 [--language <dir>|all] [--clean-only|--reset-only] [--prune-images] [--dry-run]"
  echo ""
  echo "Clean build artifacts and tear down docker state across example projects."
  echo "Run by hand as part of maintenance. This is DESTRUCTIVE: 'clean' removes"
  echo "vendored deps (node_modules, build output) and 'reset' removes containers"
  echo "and named volumes. Preview with --dry-run first, then scope with --language."
  echo ""
  echo "Two verbs (both run by default):"
  echo "  clean   per-project build artifacts/caches via 'make clean' or 'npm run clean'"
  echo "  reset   'docker compose down -v --remove-orphans' for any project with a compose file"
  echo ""
  echo "Options:"
  echo "  --language <dir>  Restrict to one top-level dir (nodejs, go, components, ...). Default: all"
  echo "  --clean-only      Only run the clean step (skip docker teardown)"
  echo "  --reset-only      Only run the reset step (skip artifact cleanup)"
  echo "  --prune-images    Add '--rmi local' to reset (drop images the compose project built)"
  echo "  --dry-run         Show what would run; change nothing"
  echo "  --help            This help"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --language) LANGUAGE="$2"; shift 2 ;;
    --clean-only) CLEAN_ONLY=true; shift ;;
    --reset-only) RESET_ONLY=true; shift ;;
    --prune-images) PRUNE_IMAGES=true; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    --help|-h) usage ;;
    *) echo "Unknown option: $1"; usage ;;
  esac
done

if [[ "$CLEAN_ONLY" == true && "$RESET_ONLY" == true ]]; then
  echo "Error: --clean-only and --reset-only are mutually exclusive."
  exit 1
fi

passed=0
failed=0
skipped=0
declare -a results=()

is_skipped() {
  echo "$1" | grep -qE "$SKIP_PROJECTS"
}

print_header() {
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  $1"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# Echo the basename of the project's primary compose file, or nothing.
find_compose() {
  local dir="$1" f
  for f in compose.yaml compose.yml docker-compose.yaml docker-compose.yml; do
    if [[ -f "$dir/$f" ]]; then echo "$f"; return 0; fi
  done
  return 0
}

# Echo the project's clean command (make/npm/bun), or nothing.
detect_clean_cmd() {
  local dir="$1"
  if [[ -f "$dir/Makefile" ]] && grep -q '^clean:' "$dir/Makefile" 2>/dev/null; then
    echo "make clean"; return 0
  fi
  if [[ -f "$dir/package.json" ]] && grep -q '"clean"[[:space:]]*:' "$dir/package.json" 2>/dev/null; then
    if [[ -f "$dir/bun.lock" ]] || grep -q '"bun-types"' "$dir/package.json" 2>/dev/null; then
      echo "bun run clean"
    else
      echo "npm run clean"
    fi
    return 0
  fi
  return 0
}

# True if the dir looks like a real project (so a "nothing to do" gets reported,
# not silently swallowed).
has_marker() {
  local dir="$1" m
  for m in package.json go.mod Cargo.toml pom.xml build.gradle build.gradle.kts \
           Gemfile pubspec.yaml requirements.txt pyproject.toml mix.exs; do
    [[ -f "$dir/$m" ]] && return 0
  done
  return 1
}

# $1=dir $2=command $3=kind(clean|reset). Prints status, returns command rc.
run_action() {
  local dir="$1" cmd="$2" kind="$3"
  echo "  $kind: ($cmd)"
  if [[ "$DRY_RUN" == true ]]; then
    echo "    [dry-run] not executed"
    return 0
  fi
  local rc=0
  if [[ "$kind" == "reset" && -f "$SCOUT_ENV" ]]; then
    # Scout env exports let compose files with required (no-default) vars interpolate.
    # shellcheck source=/dev/null
    ( cd "$dir" && set -a && . "$SCOUT_ENV" && set +a && eval "$cmd" ) >/tmp/clean-action.log 2>&1 || rc=$?
  else
    ( cd "$dir" && eval "$cmd" ) >/tmp/clean-action.log 2>&1 || rc=$?
  fi
  if [[ $rc -eq 0 ]]; then
    echo "    done"
  else
    echo "    FAILED (rc=$rc):"
    tail -6 /tmp/clean-action.log | sed 's/^/      /'
  fi
  return $rc
}

process_project() {
  local dir="$1" label="$2"
  local name; name="$(basename "$dir")"
  [[ -d "$dir" ]] || return 0
  [[ "$name" == "_shared" ]] && return 0

  if is_skipped "$name"; then
    results+=("$label: SKIP (legacy)"); skipped=$((skipped + 1)); return 0
  fi

  local compose clean_cmd
  compose="$(find_compose "$dir")"
  clean_cmd="$(detect_clean_cmd "$dir")"

  if [[ -z "$compose" && -z "$clean_cmd" ]]; then
    if has_marker "$dir"; then
      results+=("$label: SKIP (no clean target, no compose)"); skipped=$((skipped + 1))
    fi
    return 0
  fi

  print_header "$label"
  local ok=true detail=""

  if [[ "$RESET_ONLY" == false ]]; then
    if [[ -n "$clean_cmd" ]]; then
      if run_action "$dir" "$clean_cmd" "clean"; then detail="${detail}clean "; else detail="${detail}clean=FAIL "; ok=false; fi
    else
      echo "  clean: (no clean target — skipped)"
    fi
  fi

  if [[ "$CLEAN_ONLY" == false ]]; then
    if [[ -n "$compose" ]]; then
      local rmi=""
      [[ "$PRUNE_IMAGES" == true ]] && rmi=" --rmi local"
      if run_action "$dir" "docker compose -f $compose down -v --remove-orphans$rmi" "reset"; then detail="${detail}reset "; else detail="${detail}reset=FAIL "; ok=false; fi
    else
      echo "  reset: (no compose — skipped)"
    fi
  fi

  if [[ "$ok" == true ]]; then
    results+=("$label: OK [${detail% }]"); passed=$((passed + 1))
  else
    results+=("$label: FAIL [${detail% }]"); failed=$((failed + 1))
  fi
  return 0
}

echo "Cleaning examples..."
echo "Language: $LANGUAGE | clean-only: $CLEAN_ONLY | reset-only: $RESET_ONLY | prune-images: $PRUNE_IMAGES | dry-run: $DRY_RUN"

for c in $CONTAINER_DIRS; do
  [[ "$LANGUAGE" == "all" || "$LANGUAGE" == "$c" ]] || continue
  [[ -d "$REPO_ROOT/$c" ]] || continue
  for dir in "$REPO_ROOT/$c"/*/; do
    [[ -d "$dir" ]] || continue
    process_project "${dir%/}" "$c/$(basename "$dir")"
  done
done

for s in $STANDALONE_DIRS; do
  [[ "$LANGUAGE" == "all" || "$LANGUAGE" == "$s" ]] || continue
  [[ -d "$REPO_ROOT/$s" ]] || continue
  process_project "$REPO_ROOT/$s" "$s"
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Results"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
for r in "${results[@]}"; do
  echo "  $r"
done
echo ""
echo "  OK: $passed | Failed: $failed | Skipped: $skipped"

if [[ $failed -gt 0 ]]; then
  exit 1
fi
