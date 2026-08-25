#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Legacy projects to skip
SKIP_PROJECTS="go119-gin191-postgres|ruby27-rails52-mysql8|ruby30-rails61-mysql|php8-laravel8-sqlite|php84-slim3-mongodb|express-typescript-mongodb"

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
  echo "Usage: $0 [--language nodejs|python|go|rust|java|csharp|ruby|php|elixir|all] [--scope all|otel] [--skip-major] [--dry-run]"
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
    [[ $# -gt 0 ]] && git checkout -- "$@" 2>/dev/null || true
  fi
}

# Rewrite requirements.txt "==" pins to the versions uv resolved into uv.lock.
# No-op when the project has no requirements.txt.
sync_requirements_from_lock() {
  [[ -f requirements.txt && -f uv.lock ]] || return 0
  python3 - <<'PYSYNC'
import re
lock = open('uv.lock').read()
resolved = {n.lower(): v for n, v in
            re.findall(r'^name = "([^"]+)"\nversion = "([^"]+)"', lock, re.M)}
out, changed = [], 0
for line in open('requirements.txt'):
    m = re.match(r'^([A-Za-z0-9._-]+)(\[[^\]]*\])?==(\S+)(.*)$', line.rstrip('\n'))
    if m:
        name, extras, cur, rest = m.groups()
        new = resolved.get(name.lower())
        if new and new != cur:
            out.append(f"{name}{extras or ''}=={new}{rest}\n"); changed += 1; continue
    out.append(line)
if changed:
    open('requirements.txt', 'w').writelines(out)
    print(f"  Synced {changed} requirements.txt pins from uv.lock")
PYSYNC
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
  local before_py=""
  [[ "$mgr" == "uv" ]] && before_py=$(lock_majors python uv.lock)
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
    if ! guard_major_bump "python/$name" "$before_py" python uv.lock pyproject.toml uv.lock; then return 0; fi
    # extras + dev groups keep check tooling (mypy/ruff) installed
    uv sync --all-extras --all-groups --quiet >/dev/null 2>&1 || uv sync --all-extras --quiet >/dev/null 2>&1 || true
    # a project carrying BOTH uv.lock and requirements.txt would otherwise keep its
    # stale == pins forever: the uv branch never touches them, and check-outdated
    # reads requirements.txt, so the same bumps get reported every week
    sync_requirements_from_lock
    verify_make_check "python/$name" pyproject.toml uv.lock requirements.txt
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
      # bound the install: a wheel-less pin (e.g. psycopg2-binary on a Python
      # with no published wheel) falls into a source build that can hang the sweep
      local to=""; command -v timeout >/dev/null 2>&1 && to="timeout 240"
      command -v gtimeout >/dev/null 2>&1 && to="gtimeout 240"
      $to uv pip install --python "$venv_py" --upgrade $names >/dev/null 2>&1 || true
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
  local dir="${1%/}"
  local name
  name="$(basename "$dir")"

  if is_skipped "$name"; then return; fi
  local csprojs
  csprojs=$(find "$dir" -maxdepth 3 -name '*.csproj' \
             -not -path '*/bin/*' -not -path '*/obj/*' | sort)
  [[ -z "$csprojs" ]] && return

  if [[ -n "$DOTNET_FILTER" ]] && ! grep -qliE "$DOTNET_FILTER" $csprojs 2>/dev/null; then
    return
  fi

  print_header "csharp/$name"

  local pat="${DOTNET_FILTER:-}"
  local csproj pkgs p changed=()
  for csproj in $csprojs; do
    pkgs=$(grep -oE 'PackageReference Include="[^"]+"' "$csproj" | sed 's/.*Include="//;s/"//' \
            | { [[ -n "$pat" ]] && grep -iE "$pat" || cat; } || true)
    [[ -z "$pkgs" ]] && continue
    changed+=("${csproj#$dir/}")

    if [[ "$DRY_RUN" == true ]]; then
      echo "  [dry-run] ${csproj#$dir/}: would 'dotnet add package' (latest) for: $(echo $pkgs | tr '\n' ' ')"
      continue
    fi

    echo "  Updating ${csproj#$dir/} (dotnet add package)..."
    for p in $pkgs; do
      dotnet add "$csproj" package "$p" >/dev/null 2>&1 || true
    done
  done

  if [[ ${#changed[@]} -eq 0 ]]; then
    results+=("csharp/$name: NO_PACKAGES"); skipped=$((skipped + 1)); return
  fi

  if [[ "$DRY_RUN" == true ]]; then
    results+=("csharp/$name: DRY-RUN"); skipped=$((skipped + 1)); return
  fi

  cd "$dir" || return
  verify_make_check "csharp/$name" "${changed[@]}"
}

# Emit "name major" per locked dependency, so a sweep can tell whether an
# update crossed a major boundary that a loose manifest constraint allowed.
# A lockfile git does not track cannot be reverted or committed, so the sweep has
# nothing to deliver for that project.
lock_tracked() {
  git ls-files --error-unmatch "$1" >/dev/null 2>&1
}

lock_majors() {
  local eco="$1" file="$2"
  [[ -f "$file" ]] || return 0
  case "$eco" in
    ruby)
      sed -nE 's/^    ([A-Za-z0-9_.-]+) \(([0-9]+)\..*/\1 \2/p' "$file" | sort -u ;;
    php)
      python3 -c "
import json, sys
d = json.load(open(sys.argv[1]))
for section in ('packages', 'packages-dev'):
    for p in d.get(section, []):
        v = p['version'].lstrip('v')
        print(p['name'], v.split('.')[0])
" "$file" 2>/dev/null | sort -u ;;
    elixir)
      sed -nE 's/^[[:space:]]*"([A-Za-z0-9_]+)": \{:hex, :[A-Za-z0-9_]+, "([0-9]+)\..*/\1 \2/p' "$file" | sort -u ;;
    python)
      python3 -c "
import re, sys
t = open(sys.argv[1]).read()
for m in re.finditer(r'^name = \"([^\"]+)\"\nversion = \"([0-9]+)\.', t, re.M):
    print(m.group(1), m.group(2))
" "$file" 2>/dev/null | sort -u ;;
  esac
}

# Reverts $3.. and returns 1 when --skip-major is set and a major moved.
guard_major_bump() {
  local label="$1" before="$2"; shift 2
  local eco="$1" lockfile="$2"; shift 2
  [[ "$SKIP_MAJOR" == true ]] || return 0

  local after crossed
  after=$(lock_majors "$eco" "$lockfile")
  crossed=$(awk 'NR==FNR{b[$1]=$2; next} ($1 in b) && b[$1]!=$2 {print $1}' \
            <(printf '%s\n' "$before") <(printf '%s\n' "$after") | sort -u)
  [[ -z "$crossed" ]] && return 0

  echo "  MAJOR CROSSED (reverting): $(tr '\n' ' ' <<< "$crossed")"
  git checkout -- "$@" 2>/dev/null || true
  results+=("$label: REVERTED (major bump under --skip-major)")
  skipped=$((skipped + 1))
  return 1
}

upgrade_ruby() {
  local dir="${1%/}"
  local name
  name="$(basename "$dir")"

  if is_skipped "$name"; then return; fi
  if [[ ! -f "$dir/Gemfile" ]]; then return; fi
  if [[ -n "$SCOPE_GREP" ]] && ! grep -qE "$SCOPE_GREP" "$dir/Gemfile"; then return; fi

  print_header "ruby/$name"

  if [[ "$DRY_RUN" == true ]]; then
    echo "  [dry-run] Would run: bundle update"
    results+=("ruby/$name: DRY-RUN"); skipped=$((skipped + 1)); return
  fi

  cd "$dir" || return
  if ! lock_tracked Gemfile.lock; then
    echo "  Skipped: Gemfile.lock is not tracked by git"
    results+=("ruby/$name: SKIPPED (untracked Gemfile.lock)"); skipped=$((skipped + 1)); return
  fi
  local before
  before=$(lock_majors ruby Gemfile.lock)

  echo "  Updating gems..."
  if ! bundle update >/tmp/ud-ruby.log 2>&1; then
    echo "  UPDATE FAIL"; tail -4 /tmp/ud-ruby.log
    results+=("ruby/$name: UPDATE_FAIL"); failed=$((failed + 1))
    git checkout -- Gemfile.lock 2>/dev/null || true
    return
  fi

  if ! guard_major_bump "ruby/$name" "$before" ruby Gemfile.lock Gemfile.lock; then return 0; fi

  local verify_cmd="bundle install"
  [[ -f Makefile ]] && grep -q '^check:' Makefile && verify_cmd="make check"

  echo "  Verifying: $verify_cmd"
  if eval "$verify_cmd" >/dev/null 2>&1; then
    echo "  PASS"; results+=("ruby/$name: PASS"); passed=$((passed + 1))
  else
    echo "  FAIL"; eval "$verify_cmd" 2>&1 | tail -6 || true
    results+=("ruby/$name: FAIL"); failed=$((failed + 1))
    git checkout -- Gemfile.lock 2>/dev/null || true
  fi
}

upgrade_php() {
  local dir="${1%/}"
  local name
  name="$(basename "$dir")"

  if is_skipped "$name"; then return; fi
  if [[ ! -f "$dir/composer.json" ]]; then return; fi
  if [[ -n "$SCOPE_GREP" ]] && ! grep -qE "$SCOPE_GREP" "$dir/composer.json"; then return; fi

  print_header "php/$name"

  if ! command -v docker >/dev/null 2>&1; then
    echo "  Skipped: docker required (composer runs in the composer:2 image)"
    results+=("php/$name: SKIPPED (no docker)"); skipped=$((skipped + 1)); return
  fi

  if [[ "$DRY_RUN" == true ]]; then
    echo "  [dry-run] Would run: composer update --with-all-dependencies (composer:2)"
    results+=("php/$name: DRY-RUN"); skipped=$((skipped + 1)); return
  fi

  cd "$dir" || return
  if ! lock_tracked composer.lock; then
    echo "  Skipped: composer.lock is not tracked by git"
    results+=("php/$name: SKIPPED (untracked composer.lock)"); skipped=$((skipped + 1)); return
  fi
  local before
  before=$(lock_majors php composer.lock)

  echo "  Updating packages..."
  if ! docker run --rm -v "$PWD":/app -w /app composer:2 \
        update --with-all-dependencies --ignore-platform-reqs --no-scripts \
        --no-interaction >/tmp/ud-php.log 2>&1; then
    echo "  UPDATE FAIL"; tail -4 /tmp/ud-php.log
    results+=("php/$name: UPDATE_FAIL"); failed=$((failed + 1))
    git checkout -- composer.json composer.lock 2>/dev/null || true
    return
  fi

  if ! guard_major_bump "php/$name" "$before" php composer.lock composer.json composer.lock; then return 0; fi

  echo "  Verifying: composer validate"
  if docker run --rm -v "$PWD":/app -w /app composer:2 \
       validate --no-check-publish --no-interaction >/dev/null 2>&1; then
    echo "  PASS"; results+=("php/$name: PASS"); passed=$((passed + 1))
  else
    echo "  FAIL"
    docker run --rm -v "$PWD":/app -w /app composer:2 \
      validate --no-check-publish --no-interaction 2>&1 | tail -6 || true
    results+=("php/$name: FAIL"); failed=$((failed + 1))
    git checkout -- composer.json composer.lock 2>/dev/null || true
  fi
}

upgrade_elixir() {
  local dir="${1%/}"
  local name
  name="$(basename "$dir")"

  if is_skipped "$name"; then return; fi
  if [[ ! -f "$dir/mix.exs" ]]; then return; fi
  if [[ -n "$SCOPE_GREP" ]] && ! grep -qE "$SCOPE_GREP" "$dir/mix.exs"; then return; fi

  print_header "elixir/$name"

  if [[ "$DRY_RUN" == true ]]; then
    echo "  [dry-run] Would run: mix deps.update --all"
    results+=("elixir/$name: DRY-RUN"); skipped=$((skipped + 1)); return
  fi

  cd "$dir" || return
  if ! lock_tracked mix.lock; then
    echo "  Skipped: mix.lock is not tracked by git"
    results+=("elixir/$name: SKIPPED (untracked mix.lock)"); skipped=$((skipped + 1)); return
  fi
  if ! mix deps.get >/tmp/ud-elixir.log 2>&1; then
    echo "  SETUP FAIL"; tail -3 /tmp/ud-elixir.log
    results+=("elixir/$name: SETUP_FAIL"); failed=$((failed + 1)); return
  fi

  local before
  before=$(lock_majors elixir mix.lock)

  echo "  Updating deps..."
  if ! mix deps.update --all >/tmp/ud-elixir.log 2>&1; then
    echo "  UPDATE FAIL"; tail -4 /tmp/ud-elixir.log
    results+=("elixir/$name: UPDATE_FAIL"); failed=$((failed + 1))
    git checkout -- mix.lock 2>/dev/null || true
    return
  fi

  if ! guard_major_bump "elixir/$name" "$before" elixir mix.lock mix.lock; then return 0; fi

  local verify_cmd="mix compile --warnings-as-errors"
  [[ -f Makefile ]] && grep -q '^check:' Makefile && verify_cmd="make check"

  echo "  Verifying: $verify_cmd"
  if eval "$verify_cmd" >/dev/null 2>&1; then
    echo "  PASS"; results+=("elixir/$name: PASS"); passed=$((passed + 1))
  else
    echo "  FAIL"; eval "$verify_cmd" 2>&1 | tail -6 || true
    results+=("elixir/$name: FAIL"); failed=$((failed + 1))
    git checkout -- mix.lock 2>/dev/null || true
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
    cd "$dir" && git checkout -- go.mod go.sum 2>/dev/null || true
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
    cd "$dir" && git checkout -- Cargo.lock Cargo.toml 2>/dev/null || true
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
  while IFS= read -r dir; do
    upgrade_python "$dir"
  done < <(find "$REPO_ROOT"/python -maxdepth 3 \
            \( -name pyproject.toml -o -name requirements.txt \) \
            -not -path '*/.venv/*' -not -path '*/node_modules/*' \
            -exec dirname {} \; | sort -u)
  # python tool dirs that live outside python/
  for dir in "$REPO_ROOT"/loadgen; do
    [[ -d "$dir" ]] && upgrade_python "$dir"
  done
fi

if [[ "$LANGUAGE" == "all" || "$LANGUAGE" == "go" ]]; then
  while IFS= read -r mod; do
    upgrade_go "$(dirname "$mod")"
  done < <(find "$REPO_ROOT"/go -maxdepth 3 -name go.mod \
            -not -path '*/vendor/*' | sort)
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

if [[ "$run_unscoped_langs" == true ]] && [[ "$LANGUAGE" == "all" || "$LANGUAGE" == "ruby" ]]; then
  while IFS= read -r manifest; do
    upgrade_ruby "$(dirname "$manifest")"
  done < <(find "$REPO_ROOT"/ruby -maxdepth 3 -name Gemfile \
            -not -path '*/vendor/*' -not -path '*/.*/*' | sort)
fi

if [[ "$run_unscoped_langs" == true ]] && [[ "$LANGUAGE" == "all" || "$LANGUAGE" == "php" ]]; then
  while IFS= read -r manifest; do
    upgrade_php "$(dirname "$manifest")"
  done < <(find "$REPO_ROOT"/php -maxdepth 3 -name composer.json \
            -not -path '*/vendor/*' -not -path '*/.*/*' | sort)
fi

if [[ "$run_unscoped_langs" == true ]] && [[ "$LANGUAGE" == "all" || "$LANGUAGE" == "elixir" ]]; then
  while IFS= read -r manifest; do
    upgrade_elixir "$(dirname "$manifest")"
  done < <(find "$REPO_ROOT"/elixir -maxdepth 3 -name mix.exs \
            -not -path '*/deps/*' -not -path '*/_build/*' -not -path '*/.*/*' | sort)
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
