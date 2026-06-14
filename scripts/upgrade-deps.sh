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
PY_FILTER=""        # pip/uv package-name prefix to upgrade
DOTNET_FILTER=""    # NuGet package-name prefix to upgrade

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
    PY_FILTER='opentelemetry'
    DOTNET_FILTER='OpenTelemetry'
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

# revert a node project's manifest to HEAD and restore node_modules. Checks out
# files one at a time so a missing bun.lock/package-lock doesn't abort the whole
# checkout (which would leave the bumped package.json in place).
revert_node_manifest() {
  local dir="$1" is_bun="$2" f
  cd "$dir" || return
  for f in package.json package-lock.json bun.lock; do
    [[ -f "$f" ]] && git checkout -- "$f" 2>/dev/null || true
  done
  if [[ "$is_bun" == true ]]; then bun install >/dev/null 2>&1 || true; else npm install >/dev/null 2>&1 || true; fi
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
  local inst_rc=0
  if [[ "$is_bun" == true ]]; then
    bun install >/tmp/ud-install.log 2>&1 || inst_rc=$?
  else
    npm install >/tmp/ud-install.log 2>&1 || inst_rc=$?
  fi
  tail -3 /tmp/ud-install.log
  # an install failure (e.g. EOVERRIDE) must not abort the whole sweep: revert
  # this project's manifest and move on
  if [[ $inst_rc -ne 0 ]]; then
    echo "  INSTALL FAIL"
    results+=("nodejs/$name: INSTALL_FAIL"); failed=$((failed + 1))
    revert_node_manifest "$dir" "$is_bun"
    return
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
    # revert failures so the tree only carries green changes
    revert_node_manifest "$dir" "$is_bun"
  fi
}

# $1=label, $2..=files to revert on failure under a scoped sweep.
verify_make_check() {
  local label="$1"; shift
  if [[ ! -f Makefile ]] || ! grep -q '^check:' Makefile; then
    echo "  UPGRADED (no make check)"; results+=("$label: UPGRADED (no verify)"); passed=$((passed + 1)); return
  fi
  echo "  Verifying: make check"
  if make check >/dev/null 2>&1; then
    echo "  PASS"; results+=("$label: PASS"); passed=$((passed + 1))
  else
    echo "  FAIL"; make check 2>&1 | tail -8 || true
    results+=("$label: FAIL"); failed=$((failed + 1))
    [[ "$SCOPE" != "all" && $# -gt 0 ]] && git checkout -- "$@" 2>/dev/null || true
  fi
}

upgrade_python() {
  local dir="$1"
  local name
  name="$(basename "$dir")"

  if is_skipped "$name"; then return; fi
  local mgr=""
  [[ -f "$dir/uv.lock" ]] && mgr="uv"
  [[ -z "$mgr" && -f "$dir/requirements.txt" ]] && mgr="pip"
  [[ -z "$mgr" ]] && return   # no manifest (e.g. empty shell)

  if [[ -n "$PY_FILTER" ]] && ! grep -qiE "$PY_FILTER" "$dir/pyproject.toml" "$dir/requirements.txt" 2>/dev/null; then
    return
  fi

  print_header "python/$name"

  if [[ "$DRY_RUN" == true ]]; then
    local what="all packages"; [[ -n "$PY_FILTER" ]] && what="packages matching /$PY_FILTER/"
    echo "  [dry-run] manager=$mgr; would upgrade $what (minor/patch)"
    results+=("python/$name: DRY-RUN"); skipped=$((skipped + 1)); return
  fi

  cd "$dir" || return
  echo "  Updating ($mgr)..."
  if [[ "$mgr" == "uv" ]]; then
    if [[ -n "$PY_FILTER" ]]; then
      local args="" p
      for p in $(grep -oiE "\"${PY_FILTER}[A-Za-z0-9._-]*" pyproject.toml | tr -d '"' | sort -u); do
        args="$args --upgrade-package $p"
      done
      [[ -n "$args" ]] && uv lock $args >/dev/null 2>&1 || true
    else
      uv lock --upgrade >/dev/null 2>&1 || true
    fi
    # extras + dev groups keep check tooling (mypy/ruff) installed
    uv sync --all-extras --all-groups --quiet >/dev/null 2>&1 || uv sync --all-extras --quiet >/dev/null 2>&1 || true
    verify_make_check "python/$name" pyproject.toml uv.lock
  else
    # pip: upgrade the venv via uv, then rewrite the == pins to resolved versions
    local venv_py=".venv/bin/python"; [[ -x "$venv_py" ]] || venv_py="venv/bin/python"
    # tool dirs (e.g. loadgen) ship no venv; resolve in a throwaway one
    local ephemeral=""
    if [[ ! -x "$venv_py" ]]; then
      ephemeral="/tmp/upgrade-deps-venv-$$"
      uv venv "$ephemeral" >/dev/null 2>&1 && venv_py="$ephemeral/bin/python"
    fi
    local names
    if [[ -n "$PY_FILTER" ]]; then
      names=$(grep -iE "^${PY_FILTER}[A-Za-z0-9._-]*==" requirements.txt | sed 's/[=<>].*//') || true
    else
      names=$(grep -E "==" requirements.txt | sed 's/[=<>].*//') || true
    fi
    if [[ -x "$venv_py" && -n "$names" ]]; then
      uv pip install --python "$venv_py" --upgrade $names >/dev/null 2>&1 || true
      local p v
      for p in $names; do
        v=$("$venv_py" -c "import importlib.metadata as m; print(m.version('$p'))" 2>/dev/null)
        [[ -n "$v" ]] && sed -i '' -E "s/^(${p}==).*/\1${v}/" requirements.txt
      done
    fi
    [[ -n "$ephemeral" ]] && rm -rf "$ephemeral"
    verify_make_check "python/$name" requirements.txt
  fi
}

upgrade_dotnet() {
  local dir="$1"
  local name
  name="$(basename "$dir")"

  if is_skipped "$name"; then return; fi
  local csproj
  csproj=$(find "$dir" -maxdepth 1 -name '*.csproj' | head -1)
  [[ -z "$csproj" ]] && return

  if [[ -n "$DOTNET_FILTER" ]] && ! grep -qiE "$DOTNET_FILTER" "$csproj" 2>/dev/null; then
    return
  fi

  print_header "csharp/$name"

  local pat="${DOTNET_FILTER:-}"
  local pkgs
  pkgs=$(grep -oE 'PackageReference Include="[^"]+"' "$csproj" | sed 's/.*Include="//;s/"//' \
          | { [[ -n "$pat" ]] && grep -iE "$pat" || cat; })

  if [[ "$DRY_RUN" == true ]]; then
    echo "  [dry-run] would 'dotnet add package' (latest) for: $(echo $pkgs | tr '\n' ' ')"
    results+=("csharp/$name: DRY-RUN"); skipped=$((skipped + 1)); return
  fi

  cd "$dir" || return
  echo "  Updating (dotnet add package)..."
  local p
  for p in $pkgs; do
    dotnet add "$csproj" package "$p" >/dev/null 2>&1 || true
  done
  verify_make_check "csharp/$name" "$(basename "$csproj")"
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
  cd "$dir" && { go get -u $get_target 2>&1 | tail -5; go mod tidy 2>&1; } || true

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
  cd "$dir" && { cargo update 2>&1 | tail -5 || true; }

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

# rust/java have no scope filter, so they only run in an unscoped sweep
[[ "$SCOPE" != "all" ]] && run_unscoped_langs=false || run_unscoped_langs=true

if [[ "$LANGUAGE" == "all" || "$LANGUAGE" == "nodejs" ]]; then
  # find (not glob) so nested monorepo packages like trpc-postgres/{app,notify}
  # are reached, not just top-level project dirs
  while IFS= read -r pkg; do
    upgrade_nodejs "$(dirname "$pkg")"
  done < <(find "$REPO_ROOT"/nodejs -maxdepth 3 -name package.json \
            -not -path '*/node_modules/*' -not -path '*/.next/*' \
            -not -path '*/dist/*' -not -path '*/build/*' | sort)
fi

if [[ "$LANGUAGE" == "all" || "$LANGUAGE" == "python" ]]; then
  for dir in "$REPO_ROOT"/python/*/; do
    [[ -d "$dir" ]] || continue
    upgrade_python "$dir"
  done
  # python tool dirs that live outside python/
  for dir in "$REPO_ROOT"/loadgen; do
    [[ -d "$dir" ]] && upgrade_python "$dir"
  done
fi

if [[ "$LANGUAGE" == "all" || "$LANGUAGE" == "go" ]]; then
  for dir in "$REPO_ROOT"/go/*/; do
    [[ -d "$dir" ]] || continue
    upgrade_go "$dir"
  done
fi

if [[ "$LANGUAGE" == "all" || "$LANGUAGE" == "csharp" || "$LANGUAGE" == "dotnet" ]]; then
  for dir in "$REPO_ROOT"/csharp/*/; do
    [[ -d "$dir" ]] || continue
    upgrade_dotnet "$dir"
  done
fi

if [[ "$run_unscoped_langs" == true ]] && [[ "$LANGUAGE" == "all" || "$LANGUAGE" == "rust" ]]; then
  for dir in "$REPO_ROOT"/rust/*/; do
    [[ -d "$dir" ]] || continue
    upgrade_rust "$dir"
  done
fi

if [[ "$run_unscoped_langs" == true ]] && [[ "$LANGUAGE" == "all" || "$LANGUAGE" == "java" ]]; then
  for dir in "$REPO_ROOT"/java/*/; do
    [[ -d "$dir" ]] || continue
    upgrade_java "$dir"
  done
fi

if [[ "$run_unscoped_langs" == false ]]; then
  echo ""
  echo "  (scope=$SCOPE: rust/java skipped — no scoped filter defined for them yet)"
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
