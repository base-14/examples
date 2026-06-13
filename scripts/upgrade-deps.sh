#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Legacy projects to skip
SKIP_PROJECTS="go119-gin191-postgres|ruby27-rails52-mysql8|php8-laravel8-sqlite"

LANGUAGE="all"
SKIP_MAJOR=false
DRY_RUN=false
SCOPE="all"

# A scope restricts the sweep to one dependency family. Add a preset by giving it
# a node package filter (ncu globs), the go module path patterns to `go get -u`,
# and a grep that decides whether a project owns any of those deps (so untouched
# projects are skipped silently). "all" = unfiltered, every dependency.
NODE_FILTER=""      # passed verbatim to npm-check-updates as package filters
GO_PATTERNS=""      # passed verbatim to `go get -u`
SCOPE_GREP=""       # manifest grep guard; empty = no guard

usage() {
  echo "Usage: $0 [--language nodejs|python|go|rust|java|all] [--scope all|otel] [--skip-major] [--dry-run]"
  echo ""
  echo "Upgrade dependencies across all example projects."
  echo ""
  echo "Options:"
  echo "  --language     Filter by language (default: all)"
  echo "  --scope        Restrict to a dependency family (default: all). 'otel' bumps"
  echo "                 only @opentelemetry/* + @fastify/otel (node) and"
  echo "                 go.opentelemetry.io/* + opentelemetry-operations-go (go),"
  echo "                 minor/patch only, node+go projects only."
  echo "  --skip-major   Only apply minor/patch updates"
  echo "  --dry-run      Show what would change without modifying files"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --language) LANGUAGE="$2"; shift 2 ;;
    --scope) SCOPE="$2"; shift 2 ;;
    --skip-major) SKIP_MAJOR=true; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    --help|-h) usage ;;
    *) echo "Unknown option: $1"; usage ;;
  esac
done

case "$SCOPE" in
  all) ;;
  otel)
    NODE_FILTER='@opentelemetry/* @fastify/otel'
    GO_PATTERNS='go.opentelemetry.io/otel/... go.opentelemetry.io/contrib/... github.com/GoogleCloudPlatform/opentelemetry-operations-go/...'
    SCOPE_GREP='@opentelemetry/|@fastify/otel|go.opentelemetry.io'
    SKIP_MAJOR=true   # OTel sweep is minor/patch by definition
    ;;
  *) echo "Unknown scope: $SCOPE"; usage ;;
esac

passed=0
failed=0
skipped=0
declare -a results=()

is_skipped() {
  local dir="$1"
  echo "$dir" | grep -qE "$SKIP_PROJECTS"
}

print_header() {
  local project="$1"
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  Upgrading: $project"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

detect_verify_cmd() {
  local dir="$1"
  local pkg_json="$dir/package.json"

  if grep -q '"check"' "$pkg_json" 2>/dev/null; then
    echo "npm run check"
  elif grep -q '"build-lint-test"' "$pkg_json" 2>/dev/null; then
    echo "npm run build-lint-test"
  elif grep -q '"build:lint"' "$pkg_json" 2>/dev/null; then
    echo "npm run build:lint"
  elif grep -q '"build-lint"' "$pkg_json" 2>/dev/null; then
    echo "npm run build-lint"
  else
    echo "npm run build"
  fi
}

# Build a no-test verify command (typecheck + build + lint, whichever exist) for
# scoped sweeps. Tests are excluded because they need live services and would
# false-fail an otherwise-clean dependency bump. $2 is the runner (npm|bun).
scoped_verify_cmd() {
  local pkg="$1/package.json" runner="$2"
  local parts=""
  grep -q '"typecheck"' "$pkg" 2>/dev/null && parts="$runner run typecheck"
  if grep -q '"build"' "$pkg" 2>/dev/null; then
    parts="${parts:+$parts && }$runner run build"
  fi
  grep -q '"lint"' "$pkg" 2>/dev/null && parts="${parts:+$parts && }$runner run lint"
  echo "$parts"   # empty = nothing to verify (runtime-only example, install-only)
}

upgrade_nodejs() {
  local dir="$1"
  local name
  name="$(basename "$dir")"

  if is_skipped "$name"; then return; fi
  if [[ ! -f "$dir/package.json" ]]; then return; fi
  if [[ -n "$SCOPE_GREP" ]] && ! grep -qE "$SCOPE_GREP" "$dir/package.json"; then return; fi

  print_header "nodejs/$name"

  local is_bun=false
  if [[ -f "$dir/bun.lock" ]] || grep -q '"bun-types"' "$dir/package.json" 2>/dev/null; then
    is_bun=true
  fi

  local ncu_flags=""
  if [[ "$SKIP_MAJOR" == true ]]; then
    ncu_flags="--target minor"
  fi

  if [[ "$DRY_RUN" == true ]]; then
    echo "  [dry-run] Would run: npx npm-check-updates $ncu_flags $NODE_FILTER"
    cd "$dir" && npx npm-check-updates $ncu_flags $NODE_FILTER 2>/dev/null || true
    results+=("nodejs/$name: DRY-RUN")
    skipped=$((skipped + 1))
    return
  fi

  echo "  Updating package.json..."
  cd "$dir" && npx npm-check-updates -u $ncu_flags $NODE_FILTER 2>/dev/null || true

  echo "  Installing..."
  if [[ "$is_bun" == true ]]; then
    bun install 2>&1 | tail -3
  else
    npm install 2>&1 | tail -3
  fi

  local verify_cmd runner="npm"
  [[ "$is_bun" == true ]] && runner="bun"
  if [[ "$SCOPE" != "all" ]]; then
    # scoped sweep: no-test gate, avoids false-fails from missing live services
    verify_cmd="$(scoped_verify_cmd "$dir" "$runner")"
  elif [[ "$is_bun" == true ]]; then
    verify_cmd="bun run check"
  else
    verify_cmd=$(detect_verify_cmd "$dir")
    # the bare-build fallback doesn't lint; chain a standalone lint so lint
    # regressions (e.g. an eslint plugin crash) aren't masked by a green build
    if [[ "$verify_cmd" == "npm run build" ]] && grep -q '"lint"' "$dir/package.json" 2>/dev/null; then
      verify_cmd="npm run build && npm run lint"
    fi
  fi

  if [[ -z "$verify_cmd" ]]; then
    echo "  UPGRADED (no build/lint script to verify)"
    results+=("nodejs/$name: UPGRADED (no verify)")
    passed=$((passed + 1))
    return
  fi

  echo "  Verifying: $verify_cmd"
  if eval "$verify_cmd" 2>&1; then
    echo "  PASS"
    results+=("nodejs/$name: PASS")
    passed=$((passed + 1))
  else
    echo "  FAIL"
    results+=("nodejs/$name: FAIL")
    failed=$((failed + 1))
    # scoped sweeps revert failures so the tree only carries green changes
    if [[ "$SCOPE" != "all" ]]; then
      cd "$dir" && git checkout -- package.json package-lock.json 2>/dev/null || true
      if [[ "$is_bun" == true ]]; then bun install >/dev/null 2>&1 || true; else npm install >/dev/null 2>&1 || true; fi
    fi
  fi
}

upgrade_python() {
  local dir="$1"
  local name
  name="$(basename "$dir")"

  if is_skipped "$name"; then return; fi
  if [[ ! -f "$dir/requirements.txt" ]]; then return; fi

  print_header "python/$name"

  if [[ "$DRY_RUN" == true ]]; then
    echo "  [dry-run] Would update requirements.txt versions"
    results+=("python/$name: DRY-RUN")
    skipped=$((skipped + 1))
    return
  fi

  echo "  Updating requirements.txt..."
  if command -v pip-compile &>/dev/null; then
    cd "$dir" && pip-compile --upgrade --strip-extras requirements.in 2>/dev/null || true
  else
    echo "  pip-tools not available, skipping auto-upgrade"
    results+=("python/$name: SKIPPED (no pip-tools)")
    skipped=$((skipped + 1))
    return
  fi

  if [[ -f "$dir/Makefile" ]] && grep -q "check:" "$dir/Makefile"; then
    echo "  Verifying: make check"
    if cd "$dir" && make check 2>&1; then
      results+=("python/$name: PASS")
      passed=$((passed + 1))
    else
      results+=("python/$name: FAIL")
      failed=$((failed + 1))
    fi
  else
    results+=("python/$name: UPGRADED (no verify)")
    passed=$((passed + 1))
  fi
}

upgrade_go() {
  local dir="$1"
  local name
  name="$(basename "$dir")"

  if is_skipped "$name"; then return; fi
  if [[ ! -f "$dir/go.mod" ]]; then return; fi
  if [[ -n "$SCOPE_GREP" ]] && ! grep -qE "$SCOPE_GREP" "$dir/go.mod"; then return; fi

  print_header "go/$name"

  local get_target="${GO_PATTERNS:-./...}"

  if [[ "$DRY_RUN" == true ]]; then
    echo "  [dry-run] Would run: go get -u $get_target && go mod tidy"
    results+=("go/$name: DRY-RUN")
    skipped=$((skipped + 1))
    return
  fi

  echo "  Updating modules..."
  cd "$dir" && go get -u $get_target 2>&1 | tail -5 && go mod tidy 2>&1

  local verify_cmd="go build ./..."
  if [[ -f "$dir/Makefile" ]] && grep -q "check:" "$dir/Makefile"; then
    verify_cmd="make check"
  fi

  echo "  Verifying: $verify_cmd"
  if cd "$dir" && eval "$verify_cmd" 2>&1; then
    results+=("go/$name: PASS")
    passed=$((passed + 1))
  else
    results+=("go/$name: FAIL")
    failed=$((failed + 1))
    if [[ "$SCOPE" != "all" ]]; then
      cd "$dir" && git checkout -- go.mod go.sum 2>/dev/null || true
    fi
  fi
}

upgrade_rust() {
  local dir="$1"
  local name
  name="$(basename "$dir")"

  if is_skipped "$name"; then return; fi
  if [[ ! -f "$dir/Cargo.toml" ]]; then return; fi

  print_header "rust/$name"

  if [[ "$DRY_RUN" == true ]]; then
    echo "  [dry-run] Would run: cargo update"
    results+=("rust/$name: DRY-RUN")
    skipped=$((skipped + 1))
    return
  fi

  echo "  Updating Cargo.lock..."
  cd "$dir" && cargo update 2>&1 | tail -5

  echo "  Verifying: cargo check && cargo clippy && cargo test"
  if cd "$dir" && cargo check 2>&1 && cargo clippy -- -D warnings 2>&1 && cargo test 2>&1; then
    results+=("rust/$name: PASS")
    passed=$((passed + 1))
  else
    results+=("rust/$name: FAIL")
    failed=$((failed + 1))
  fi
}

upgrade_java() {
  local dir="$1"
  local name
  name="$(basename "$dir")"

  if is_skipped "$name"; then return; fi

  print_header "java/$name"

  if [[ "$DRY_RUN" == true ]]; then
    if [[ -f "$dir/gradlew" ]]; then
      echo "  [dry-run] Would run: ./gradlew dependencyUpdates (report only)"
    elif [[ -f "$dir/pom.xml" ]]; then
      echo "  [dry-run] Would run: mvn versions:display-dependency-updates (report only)"
    fi
    results+=("java/$name: DRY-RUN")
    skipped=$((skipped + 1))
    return
  fi

  echo "  Java deps require manual review. Run check-outdated.sh first."
  if [[ -f "$dir/gradlew" ]]; then
    echo "  Verifying current build: ./gradlew build"
    if cd "$dir" && ./gradlew build --no-daemon 2>&1 | tail -5; then
      results+=("java/$name: PASS (no upgrade, build verified)")
      passed=$((passed + 1))
    else
      results+=("java/$name: FAIL")
      failed=$((failed + 1))
    fi
  else
    results+=("java/$name: SKIPPED (manual)")
    skipped=$((skipped + 1))
  fi
}

echo "Upgrading dependencies..."
echo "Language: $LANGUAGE | Scope: $SCOPE | Skip major: $SKIP_MAJOR | Dry run: $DRY_RUN"

# Scoped sweeps only define node+go filters; pip/cargo/gradle family-scoping is a
# separate effort, so skip python/rust/java when a scope is set and say why.
scoped_only_nodego=false
[[ "$SCOPE" != "all" ]] && scoped_only_nodego=true

if [[ "$LANGUAGE" == "all" || "$LANGUAGE" == "nodejs" ]]; then
  # find (not glob) so nested monorepo packages like trpc-postgres/{app,notify}
  # are reached, not just top-level project dirs
  while IFS= read -r pkg; do
    upgrade_nodejs "$(dirname "$pkg")"
  done < <(find "$REPO_ROOT"/nodejs -maxdepth 3 -name package.json -not -path '*/node_modules/*' | sort)
fi

if [[ "$scoped_only_nodego" == false ]] && [[ "$LANGUAGE" == "all" || "$LANGUAGE" == "python" ]]; then
  for dir in "$REPO_ROOT"/python/*/; do
    [[ -d "$dir" ]] || continue
    upgrade_python "$dir"
  done
fi

if [[ "$LANGUAGE" == "all" || "$LANGUAGE" == "go" ]]; then
  for dir in "$REPO_ROOT"/go/*/; do
    [[ -d "$dir" ]] || continue
    upgrade_go "$dir"
  done
fi

if [[ "$scoped_only_nodego" == false ]] && [[ "$LANGUAGE" == "all" || "$LANGUAGE" == "rust" ]]; then
  for dir in "$REPO_ROOT"/rust/*/; do
    [[ -d "$dir" ]] || continue
    upgrade_rust "$dir"
  done
fi

if [[ "$scoped_only_nodego" == false ]] && [[ "$LANGUAGE" == "all" || "$LANGUAGE" == "java" ]]; then
  for dir in "$REPO_ROOT"/java/*/; do
    [[ -d "$dir" ]] || continue
    upgrade_java "$dir"
  done
fi

if [[ "$scoped_only_nodego" == true ]]; then
  echo ""
  echo "  (scope=$SCOPE: python/rust/java skipped — use the manual OTel version check for those)"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Results"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
for r in "${results[@]}"; do
  echo "  $r"
done
echo ""
echo "  Passed: $passed | Failed: $failed | Skipped: $skipped"

if [[ $failed -gt 0 ]]; then
  exit 1
fi
