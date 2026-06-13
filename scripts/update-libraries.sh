#!/usr/bin/env bash
# Curated, targeted library bumps (typically majors) driven by a manifest.
#
# Unlike upgrade-deps.sh (blanket ncu sweep) this applies a hand-picked list of
# package@version bumps per project, verifies build/lint, and can either probe
# (apply -> build -> REVERT, leaving the tree untouched) or apply (keep changes).
#
# Manifest format (default: scripts/library-updates.txt), one bump-set per line:
#   <ecosystem>|<relpath>|<spec> [<spec> ...]
#   ecosystem = npm | go | python | dotnet   (# comments and blank lines ignored)
#   spec      = name@version  (python/dotnet @ is mapped to ==/--version internally)
# Example:
#   npm|nodejs/fastify-postgres|typescript@6 @fastify/rate-limit@11
#   go|go/go-temporal-postgres|buf.build/go/protovalidate@v1.2.0
#   python|python/fastapi-postgres|fastapi@0.118.0 sqlalchemy@2.0.40
#   dotnet|csharp/hello-world|OpenTelemetry@1.16.0
#
# Usage:
#   ./scripts/update-libraries.sh --probe [manifest]   # dry-run + classify, reverts
#   ./scripts/update-libraries.sh --apply [manifest]   # apply + verify, keeps changes
#
# Build/lint is the gate (deterministic, no external services); tests are NOT run
# because several examples need a live DB. Run tests / e2e separately after apply.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODE=""
MANIFEST="$REPO_ROOT/scripts/library-updates.txt"

usage() {
  echo "Usage: $0 --probe|--apply [manifest-file]"
  echo "  --probe   apply each bump-set, run build/lint, then REVERT (classify CLEAN/BREAKS)"
  echo "  --apply   apply each bump-set, run build/lint, KEEP changes"
  echo "  manifest  defaults to scripts/library-updates.txt"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --probe) MODE="probe"; shift ;;
    --apply) MODE="apply"; shift ;;
    --help|-h) usage ;;
    *) MANIFEST="$1"; shift ;;
  esac
done
[[ -z "$MODE" ]] && usage
[[ -f "$MANIFEST" ]] || { echo "Manifest not found: $MANIFEST"; exit 1; }

# macOS ships bash 3.2 (no ${var^^}); uppercase via tr.
MODE_UP="$(printf '%s' "$MODE" | tr '[:lower:]' '[:upper:]')"
RESULTS=()

print_header() {
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  $MODE_UP: $1"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

is_bun() { [[ -f bun.lock ]] || grep -q '"bun-types"' package.json 2>/dev/null; }

node_build_script() {
  node -e "const s=require('./package.json').scripts||{};
    process.stdout.write(s['check']?'check':s['build-lint']?'build-lint':s['build']?'build':'')"
}

# returns 'lint' only when the build gate fell back to bare 'build' (check /
# build-lint already include linting) and a standalone 'lint' script exists, so
# lint regressions like an eslint-plugin crash can't slip through build-only.
node_lint_script() {
  node -e "const s=require('./package.json').scripts||{};
    const b=s['check']?'check':s['build-lint']?'build-lint':s['build']?'build':'';
    process.stdout.write(b==='build'&&s['lint']?'lint':'')"
}

# build/lint gate via `make check`; absent target counts as a pass.
make_check_gate() {
  local step="$1"
  if [[ -f Makefile ]] && grep -q '^check:' Makefile; then
    make check >"$step" 2>&1; return $?
  fi
  echo "no make check target" >"$step"; return 0
}

# revert only the tracked files that actually exist (avoids git checkout aborting
# on a non-existent pathspec), then restore deps to the committed lock.
revert_npm() {
  local f=()
  for p in package.json package-lock.json bun.lock; do [[ -f "$p" ]] && f+=("$p"); done
  git checkout -- "${f[@]}" 2>/dev/null
  if is_bun; then bun install >/dev/null 2>&1; else npm install >/dev/null 2>&1; fi
}
revert_go() {
  local f=()
  for p in go.mod go.sum; do [[ -f "$p" ]] && f+=("$p"); done
  git checkout -- "${f[@]}" 2>/dev/null
}
revert_python() {
  local f=()
  for p in pyproject.toml uv.lock requirements.txt; do [[ -f "$p" ]] && f+=("$p"); done
  [[ ${#f[@]} -gt 0 ]] && git checkout -- "${f[@]}" 2>/dev/null
  if [[ -f uv.lock ]]; then
    uv sync --all-extras --all-groups --quiet >/dev/null 2>&1 || uv sync --all-extras --quiet >/dev/null 2>&1 || true
  else
    local venv_py=".venv/bin/python"; [[ -x "$venv_py" ]] || venv_py="venv/bin/python"
    [[ -x "$venv_py" && -f requirements.txt ]] && uv pip install --python "$venv_py" -r requirements.txt >/dev/null 2>&1 || true
  fi
}
revert_dotnet() {
  local csproj="$1"
  [[ -n "$csproj" && -f "$csproj" ]] && git checkout -- "$csproj" 2>/dev/null
  dotnet restore >/dev/null 2>&1 || true
}

process_entry() {
  local eco="$1" rel="$2" specs="$3"
  print_header "$rel  ($specs)"
  local rc verdict step="/tmp/update-libraries.step"
  pushd "$REPO_ROOT/$rel" >/dev/null || { RESULTS+=("MISSING | $rel"); return; }

  if [[ "$eco" == "npm" ]]; then
    local runner="npm"; is_bun && runner="bun"
    if [[ "$runner" == "bun" ]]; then bun add $specs >"$step" 2>&1; else npm install $specs --save-exact=false >"$step" 2>&1; fi
    if [[ $? -ne 0 ]]; then verdict="INSTALL_FAIL"; tail -8 "$step"; RESULTS+=("$verdict | $rel | $specs"); revert_npm; popd >/dev/null; return; fi
    local b; b="$(node_build_script)"
    if [[ -z "$b" ]]; then RESULTS+=("NO_BUILD_SCRIPT | $rel | $specs"); revert_npm; popd >/dev/null; return; fi
    "$runner" run "$b" >"$step" 2>&1; rc=$?
    if [[ $rc -eq 0 ]]; then
      local l; l="$(node_lint_script)"
      [[ -n "$l" ]] && { "$runner" run "$l" >>"$step" 2>&1; rc=$?; }
    fi
  elif [[ "$eco" == "go" ]]; then
    go get $specs >"$step" 2>&1 && go mod tidy >>"$step" 2>&1 && go build ./... >>"$step" 2>&1; rc=$?
  elif [[ "$eco" == "python" ]]; then
    local mgr=""
    [[ -f uv.lock ]] && mgr="uv"
    [[ -z "$mgr" && -f requirements.txt ]] && mgr="pip"
    if [[ -z "$mgr" ]]; then RESULTS+=("NO_MANIFEST | $rel | $specs"); popd >/dev/null; return; fi
    local irc=0 s name ver; : >"$step"
    if [[ "$mgr" == "uv" ]]; then
      local pyspecs=""
      for s in $specs; do pyspecs="$pyspecs ${s/@/==}"; done
      uv add $pyspecs >>"$step" 2>&1 || irc=$?
    else
      local venv_py=".venv/bin/python"; [[ -x "$venv_py" ]] || venv_py="venv/bin/python"
      for s in $specs; do
        name="${s%@*}"; ver="${s#*@}"
        uv pip install --python "$venv_py" "${name}==${ver}" >>"$step" 2>&1 || irc=$?
        sed -i '' -E "s/^(${name}==).*/\1${ver}/" requirements.txt 2>/dev/null || true
      done
    fi
    if [[ $irc -ne 0 ]]; then verdict="INSTALL_FAIL"; tail -8 "$step"; RESULTS+=("$verdict | $rel | $specs"); revert_python; popd >/dev/null; return; fi
    make_check_gate "$step"; rc=$?
  elif [[ "$eco" == "dotnet" ]]; then
    local csproj; csproj=$(find . -maxdepth 1 -name '*.csproj' | head -1)
    if [[ -z "$csproj" ]]; then RESULTS+=("NO_CSPROJ | $rel | $specs"); popd >/dev/null; return; fi
    local irc=0 s name ver; : >"$step"
    for s in $specs; do
      name="${s%@*}"; ver="${s#*@}"
      dotnet add "$csproj" package "$name" --version "$ver" >>"$step" 2>&1 || irc=$?
    done
    if [[ $irc -ne 0 ]]; then verdict="INSTALL_FAIL"; tail -8 "$step"; RESULTS+=("$verdict | $rel | $specs"); revert_dotnet "$csproj"; popd >/dev/null; return; fi
    if [[ -f Makefile ]] && grep -q '^check:' Makefile; then make_check_gate "$step"; rc=$?; else dotnet build >"$step" 2>&1; rc=$?; fi
  fi

  if [[ $rc -eq 0 ]]; then verdict="CLEAN"; else verdict="BREAKS(rc=$rc)"; tail -12 "$step"; fi
  echo "  -> $verdict"
  RESULTS+=("$verdict | $rel | $specs")

  if [[ "$MODE" == "probe" ]] || [[ $rc -ne 0 ]]; then
    # always revert in probe mode; in apply mode revert failures so the tree stays buildable
    case "$eco" in
      npm) revert_npm ;;
      go) revert_go ;;
      python) revert_python ;;
      dotnet) revert_dotnet "${csproj:-}" ;;
    esac
  fi
  popd >/dev/null
}

echo "Mode: $MODE | Manifest: $MANIFEST"
while IFS= read -r line; do
  line="${line%%#*}"; line="$(echo "$line" | xargs)"; [[ -z "$line" ]] && continue
  IFS='|' read -r eco rel specs <<< "$line"
  process_entry "$eco" "$rel" "$specs"
done < "$MANIFEST"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  $MODE_UP SUMMARY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
printf '%s\n' ${RESULTS[@]+"${RESULTS[@]}"} | sort
echo ""
echo "  applied/breaking entries above; tree status:"
git -C "$REPO_ROOT" status --short | sed 's/^/    /' | head -20