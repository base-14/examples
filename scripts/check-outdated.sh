#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Legacy projects to skip
SKIP_PROJECTS="go119-gin191-postgres|ruby27-rails52-mysql8|php8-laravel8-sqlite|ruby30-rails61-mysql"

LANGUAGE="all"
MAJOR_ONLY=false

usage() {
  echo "Usage: $0 [--language nodejs|python|go|rust|java|csharp|ruby|php|elixir|all] [--major-only]"
  echo ""
  echo "Check outdated packages across all example projects."
  echo ""
  echo "Options:"
  echo "  --language    Filter by language (default: all)"
  echo "  --major-only  Show only major version bumps"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --language) LANGUAGE="$2"; shift 2 ;;
    --major-only) MAJOR_ONLY=true; shift ;;
    --help|-h) usage ;;
    *) echo "Unknown option: $1"; usage ;;
  esac
done

total_outdated=0
total_major=0

print_header() {
  local project="$1"
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  $project"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

is_skipped() {
  local dir="$1"
  echo "$dir" | grep -qE "$SKIP_PROJECTS"
}

check_nodejs() {
  local dir="$1"
  local name
  name="$(basename "$dir")"

  if is_skipped "$name"; then return; fi
  if [[ ! -f "$dir/package.json" ]]; then return; fi

  print_header "nodejs/$name"

  local output
  if [[ -f "$dir/bun.lock" ]] || grep -q '"bun-types"' "$dir/package.json" 2>/dev/null; then
    output=$(cd "$dir" && npx npm-check-updates 2>/dev/null || true)
  else
    output=$(cd "$dir" && npx npm-check-updates 2>/dev/null || true)
  fi

  if echo "$output" | grep -q "All dependencies match"; then
    echo "  All up to date"
    return
  fi

  local count=0
  local majors=0

  while IFS= read -r line; do
    # ncu output format: " package  ^current  →  ^latest"
    if [[ "$line" =~ ^[[:space:]]+[^[:space:]].*→ ]]; then
      local pkg current latest
      pkg=$(echo "$line" | awk '{print $1}')
      current=$(echo "$line" | awk '{print $2}' | sed 's/[\^~]//')
      # latest = first token after the → arrow; newer ncu appends a trailing
      # annotation (e.g. "[missing time]") that must not be read as the version.
      latest=$(echo "$line" | sed 's/.*→[[:space:]]*//' | awk '{print $1}' | sed 's/[\^~]//')

      local cur_major lat_major bump_type
      cur_major="${current%%.*}"
      lat_major="${latest%%.*}"

      if [[ "$cur_major" != "$lat_major" ]]; then
        bump_type="MAJOR"
        majors=$((majors + 1))
      elif [[ "${current%.*}" != "${latest%.*}" ]]; then
        bump_type="minor"
      else
        bump_type="patch"
      fi

      if [[ "$MAJOR_ONLY" == true && "$bump_type" != "MAJOR" ]]; then
        continue
      fi

      count=$((count + 1))
      if [[ "$bump_type" == "MAJOR" ]]; then
        printf "  ⚠ MAJOR  %-45s %s → %s\n" "$pkg" "$current" "$latest"
      else
        printf "  %-8s %-45s %s → %s\n" "$bump_type" "$pkg" "$current" "$latest"
      fi
    fi
  done <<< "$output"

  total_outdated=$((total_outdated + count))
  total_major=$((total_major + majors))
}

check_python() {
  local dir="$1"
  local name
  name="$(basename "$dir")"

  if is_skipped "$name"; then return; fi

  local specs
  if [[ -f "$dir/requirements.txt" ]]; then
    specs=$(cat "$dir/requirements.txt")
  elif [[ -f "$dir/pyproject.toml" ]]; then
    specs=$(python3 - "$dir/pyproject.toml" <<'PY'
import sys, tomllib
d = tomllib.load(open(sys.argv[1], 'rb')).get('project', {})
out = list(d.get('dependencies', []))
for group in d.get('optional-dependencies', {}).values():
    out.extend(group)
print('\n'.join(out))
PY
)
  else
    return
  fi
  [[ -z "$specs" ]] && return

  print_header "python/$name"

  local pip_bin
  pip_bin=$(command -v pip || command -v pip3 || true)
  if [[ -z "$pip_bin" ]]; then
    echo "  SKIP: no pip on PATH"
    return
  fi

  local count=0
  local majors=0

  while IFS= read -r line; do
    [[ -z "$line" || "$line" =~ ^# ]] && continue
    local pkg current
    pkg=$(echo "$line" | sed 's/[>=<~!;].*//; s/\[.*\]//; s/[[:space:]]*$//')
    current=$(echo "$line" | grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?' | head -1)
    [[ -z "$current" ]] && continue

    local latest
    latest=$("$pip_bin" index versions "$pkg" 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?' | head -1 || true)
    [[ -z "$latest" || "$latest" == "$current" ]] && continue

    local cur_major lat_major bump_type
    cur_major="${current%%.*}"
    lat_major="${latest%%.*}"

    if [[ "$cur_major" != "$lat_major" ]]; then
      bump_type="MAJOR"
      majors=$((majors + 1))
    elif [[ "${current%.*}" != "${latest%.*}" ]]; then
      bump_type="minor"
    else
      bump_type="patch"
    fi

    if [[ "$MAJOR_ONLY" == true && "$bump_type" != "MAJOR" ]]; then
      continue
    fi

    count=$((count + 1))
    if [[ "$bump_type" == "MAJOR" ]]; then
      printf "  ⚠ MAJOR  %-45s %s → %s\n" "$pkg" "$current" "$latest"
    else
      printf "  %-8s %-45s %s → %s\n" "$bump_type" "$pkg" "$current" "$latest"
    fi
  done <<< "$specs"

  if [[ $count -eq 0 ]]; then
    echo "  All up to date"
  fi

  total_outdated=$((total_outdated + count))
  total_major=$((total_major + majors))
}

check_go() {
  local dir="$1"
  local name
  name="$(basename "$dir")"

  if is_skipped "$name"; then return; fi
  if [[ ! -f "$dir/go.mod" ]]; then return; fi

  print_header "go/$name"

  local output
  output=$(cd "$dir" && go list -m -u all 2>/dev/null | grep '\[' || true)

  if [[ -z "$output" ]]; then
    echo "  All up to date"
    return
  fi

  local count=0
  local majors=0

  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    local pkg current latest
    pkg=$(echo "$line" | awk '{print $1}')
    current=$(echo "$line" | awk '{print $2}')
    latest=$(echo "$line" | grep -oE '\[v[^]]+\]' | tr -d '[]' || true)
    [[ -z "$latest" ]] && continue

    local cur_major lat_major bump_type
    cur_major=$(echo "$current" | grep -oE '^v[0-9]+' | tr -d 'v' || true)
    lat_major=$(echo "$latest" | grep -oE '^v[0-9]+' | tr -d 'v' || true)

    if [[ "$cur_major" != "$lat_major" ]]; then
      bump_type="MAJOR"
      majors=$((majors + 1))
    else
      bump_type="minor"
    fi

    if [[ "$MAJOR_ONLY" == true && "$bump_type" != "MAJOR" ]]; then
      continue
    fi

    count=$((count + 1))
    if [[ "$bump_type" == "MAJOR" ]]; then
      printf "  ⚠ MAJOR  %-55s %s → %s\n" "$pkg" "$current" "$latest"
    else
      printf "  %-8s %-55s %s → %s\n" "$bump_type" "$pkg" "$current" "$latest"
    fi
  done <<< "$output"

  if [[ $count -eq 0 ]]; then
    echo "  All up to date"
  fi

  total_outdated=$((total_outdated + count))
  total_major=$((total_major + majors))
}

check_rust() {
  local dir="$1"
  local name
  name="$(basename "$dir")"

  if is_skipped "$name"; then return; fi
  if [[ ! -f "$dir/Cargo.toml" ]]; then return; fi

  print_header "rust/$name"

  if ! command -v cargo-outdated &>/dev/null; then
    echo "  cargo-outdated not installed (cargo install cargo-outdated)"
    return
  fi

  local output
  output=$(cd "$dir" && cargo outdated --root-deps-only 2>/dev/null || true)

  if echo "$output" | grep -q "All dependencies are up to date"; then
    echo "  All up to date"
    return
  fi

  local count=0
  local majors=0

  while IFS= read -r line; do
    [[ "$line" =~ ^Name|^-|^$ ]] && continue
    local pkg current latest
    pkg=$(echo "$line" | awk '{print $1}')
    current=$(echo "$line" | awk '{print $2}')
    latest=$(echo "$line" | awk '{print $NF}')
    [[ "$current" == "$latest" || -z "$latest" || "$latest" == "---" ]] && continue

    local cur_major lat_major bump_type
    cur_major="${current%%.*}"
    lat_major="${latest%%.*}"

    if [[ "$cur_major" != "$lat_major" ]]; then
      bump_type="MAJOR"
      majors=$((majors + 1))
    elif [[ "${current%.*}" != "${latest%.*}" ]]; then
      bump_type="minor"
    else
      bump_type="patch"
    fi

    if [[ "$MAJOR_ONLY" == true && "$bump_type" != "MAJOR" ]]; then
      continue
    fi

    count=$((count + 1))
    if [[ "$bump_type" == "MAJOR" ]]; then
      printf "  ⚠ MAJOR  %-45s %s → %s\n" "$pkg" "$current" "$latest"
    else
      printf "  %-8s %-45s %s → %s\n" "$bump_type" "$pkg" "$current" "$latest"
    fi
  done <<< "$output"

  if [[ $count -eq 0 ]]; then
    echo "  All up to date"
  fi

  total_outdated=$((total_outdated + count))
  total_major=$((total_major + majors))
}

check_java() {
  local dir="$1"
  local name
  name="$(basename "$dir")"

  if is_skipped "$name"; then return; fi

  print_header "java/$name"

  local raw output
  if [[ -f "$dir/gradlew" ]]; then
    # a failed build and a clean report both produce no matches, so check the
    # exit status before calling it up to date
    if ! raw=$(cd "$dir" && ./gradlew dependencyUpdates --no-daemon 2>&1); then
      echo "  CANNOT CHECK: gradlew dependencyUpdates failed (ben-manes versions plugin not applied?)"
      return
    fi
    output=$(grep -E '^\s+-' <<< "$raw" || true)
  elif [[ -f "$dir/pom.xml" ]]; then
    # processDependencyManagement=false keeps this to direct dependencies; the
    # default walks the whole managed BOM (1700+ lines on quarkus)
    if ! raw=$(cd "$dir" && mvn versions:display-dependency-updates \
                 -DprocessDependencyManagement=false 2>&1); then
      echo "  CANNOT CHECK: mvn versions:display-dependency-updates failed"
      return
    fi
    output=$(grep -E '^\[INFO\].*->' <<< "$raw" || true)
  else
    echo "  No build tool detected"
    return
  fi

  if [[ -z "$output" ]]; then
    echo "  All up to date"
  else
    echo "$output"
  fi
}

classify_bump() {
  local cur="${1#v}" lat="${2#v}"
  if [[ "${cur%%.*}" != "${lat%%.*}" ]]; then echo "MAJOR"
  elif [[ "${cur%.*}" != "${lat%.*}" ]]; then echo "minor"
  else echo "patch"; fi
}

# Prints one bump line and updates the caller's `count` / `majors`.
emit_bump() {
  local pkg="$1" current="$2" latest="$3" bump_type
  bump_type=$(classify_bump "$current" "$latest")
  [[ "$bump_type" == "MAJOR" ]] && majors=$((majors + 1))
  [[ "$MAJOR_ONLY" == true && "$bump_type" != "MAJOR" ]] && return 0
  count=$((count + 1))
  if [[ "$bump_type" == "MAJOR" ]]; then
    printf "  ⚠ MAJOR  %-45s %s → %s\n" "$pkg" "$current" "$latest"
  else
    printf "  %-8s %-45s %s → %s\n" "$bump_type" "$pkg" "$current" "$latest"
  fi
}

check_ruby() {
  local dir="$1"
  local name
  name="$(basename "$dir")"

  if is_skipped "$name"; then return; fi
  if [[ ! -f "$dir/Gemfile" ]]; then return; fi

  print_header "ruby/$name"

  local output rc=0
  output=$(cd "$dir" && bundle outdated --parseable 2>&1) || rc=$?
  # `bundle outdated` exits 1 when outdated gems exist, so only treat a nonzero
  # exit with no parseable rows as a real failure
  if [[ $rc -ne 0 ]] && ! grep -q '(newest ' <<< "$output"; then
    echo "  Check failed: $(grep -v '^$' <<< "$output" | tail -1)"
    return
  fi

  local count=0 majors=0
  while IFS= read -r line; do
    [[ "$line" =~ ^([a-zA-Z0-9._-]+)\ \(newest\ ([^,]+),\ installed\ ([^,\)]+) ]] || continue
    emit_bump "${BASH_REMATCH[1]}" "${BASH_REMATCH[3]}" "${BASH_REMATCH[2]}"
  done <<< "$output"

  [[ $count -eq 0 ]] && echo "  All up to date"
  total_outdated=$((total_outdated + count))
  total_major=$((total_major + majors))
}

check_php() {
  local dir="$1"
  local name
  name="$(basename "$dir")"

  if is_skipped "$name"; then return; fi
  if [[ ! -f "$dir/composer.json" ]]; then return; fi

  print_header "php/$name"

  if ! command -v docker >/dev/null 2>&1; then
    echo "  Skipped: docker required (composer runs in the composer:2 image)"
    return
  fi

  local output errfile rc=0
  errfile=$(mktemp)
  output=$(cd "$dir" && docker run --rm -v "$PWD":/app -w /app composer:2 \
            outdated --format=json --ignore-platform-reqs --no-interaction 2>"$errfile") || rc=$?
  if [[ $rc -ne 0 ]] || ! grep -q '"installed"' <<< "$output"; then
    echo "  Check failed: $(grep -v '^$' "$errfile" | tail -1)"
    rm -f "$errfile"
    return
  fi
  rm -f "$errfile"

  local count=0 majors=0
  while IFS=$'\t' read -r pkg cur lat; do
    [[ -z "$pkg" ]] && continue
    emit_bump "$pkg" "$cur" "$lat"
  done < <(printf '%s' "$output" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
for p in data.get('installed', []):
    latest = p.get('latest')
    if latest and latest != p.get('version'):
        print(f\"{p['name']}\t{p['version']}\t{latest}\")
")

  [[ $count -eq 0 ]] && echo "  All up to date"
  total_outdated=$((total_outdated + count))
  total_major=$((total_major + majors))
}

check_elixir() {
  local dir="$1"
  local name
  name="$(basename "$dir")"

  if is_skipped "$name"; then return; fi
  if [[ ! -f "$dir/mix.exs" ]]; then return; fi

  print_header "elixir/$name"

  local output
  output=$(cd "$dir" && mix deps.get >/dev/null 2>&1; mix hex.outdated 2>&1 || true)
  if ! grep -q '^Dependency' <<< "$output"; then
    echo "  Check failed: $(grep -v '^$' <<< "$output" | head -1)"
    return
  fi

  local count=0 majors=0
  while IFS= read -r line; do
    local pkg versions cur lat
    pkg="${line%% *}"
    [[ "$pkg" =~ ^[a-z][a-z0-9_]*$ ]] || continue
    versions=$(awk '{for (i=2; i<=NF; i++) if ($i ~ /^[0-9]+\./) print $i}' <<< "$line")
    cur=$(sed -n 1p <<< "$versions")
    lat=$(sed -n 2p <<< "$versions")
    [[ -z "$cur" || -z "$lat" || "$cur" == "$lat" ]] && continue
    emit_bump "$pkg" "$cur" "$lat"
  done <<< "$output"

  [[ $count -eq 0 ]] && echo "  All up to date"
  total_outdated=$((total_outdated + count))
  total_major=$((total_major + majors))
}

check_dotnet() {
  local dir="${1%/}"
  local name
  name="$(basename "$dir")"

  if is_skipped "$name"; then return; fi

  local csprojs
  csprojs=$(find "$dir" -maxdepth 3 -name '*.csproj' \
             -not -path '*/bin/*' -not -path '*/obj/*' | sort)
  [[ -z "$csprojs" ]] && return

  print_header "csharp/$name"

  if ! command -v dotnet >/dev/null 2>&1; then
    echo "  Check failed: dotnet CLI not installed"
    return
  fi

  local csproj output rows="" rc
  for csproj in $csprojs; do
    rc=0
    dotnet restore "$csproj" >/dev/null 2>&1 || rc=$?
    if [[ $rc -ne 0 ]]; then
      echo "  ${csproj#$dir/}: restore failed"
      continue
    fi
    rc=0
    output=$(dotnet list "$csproj" package --outdated 2>&1) || rc=$?
    if [[ $rc -ne 0 ]]; then
      echo "  ${csproj#$dir/}: $(grep -v '^$' <<< "$output" | tail -1)"
      continue
    fi
    rows+=$(awk '$1 == ">" && $NF ~ /^[0-9]/ {print $2, $(NF-1), $NF}' <<< "$output")
    rows+=$'\n'
  done

  rows=$(grep -v '^[[:space:]]*$' <<< "$rows" | sort -u || true)

  local count=0 majors=0 pkg cur lat
  while read -r pkg cur lat; do
    [[ -z "$pkg" ]] && continue
    emit_bump "$pkg" "$cur" "$lat"
  done <<< "$rows"

  [[ $count -eq 0 ]] && echo "  All up to date"
  total_outdated=$((total_outdated + count))
  total_major=$((total_major + majors))
}

echo "Checking outdated dependencies..."
echo "Language: $LANGUAGE | Major only: $MAJOR_ONLY"

if [[ "$LANGUAGE" == "all" || "$LANGUAGE" == "nodejs" ]]; then
  while IFS= read -r pkg; do
    check_nodejs "$(dirname "$pkg")"
  done < <(find "$REPO_ROOT"/nodejs -maxdepth 3 -name package.json \
            -not -path '*/node_modules/*' -not -path '*/.next/*' \
            -not -path '*/dist/*' -not -path '*/build/*' | sort)
fi

if [[ "$LANGUAGE" == "all" || "$LANGUAGE" == "python" ]]; then
  while IFS= read -r dir; do
    check_python "$dir"
  done < <(find "$REPO_ROOT"/python -maxdepth 3 \
            \( -name pyproject.toml -o -name requirements.txt \) \
            -not -path '*/.venv/*' -not -path '*/node_modules/*' \
            -exec dirname {} \; | sort -u)
fi

if [[ "$LANGUAGE" == "all" || "$LANGUAGE" == "go" ]]; then
  while IFS= read -r mod; do
    check_go "$(dirname "$mod")"
  done < <(find "$REPO_ROOT"/go -maxdepth 3 -name go.mod \
            -not -path '*/vendor/*' | sort)
fi

if [[ "$LANGUAGE" == "all" || "$LANGUAGE" == "rust" ]]; then
  for dir in "$REPO_ROOT"/rust/*/; do
    [[ -d "$dir" ]] || continue
    check_rust "$dir"
  done
fi

if [[ "$LANGUAGE" == "all" || "$LANGUAGE" == "java" ]]; then
  while IFS= read -r build; do
    check_java "$(dirname "$build")"
  done < <(find "$REPO_ROOT"/java -maxdepth 3 \
            \( -name pom.xml -o -name build.gradle -o -name build.gradle.kts \) \
            -not -path '*/build/*' -not -path '*/target/*' | sort)
fi

if [[ "$LANGUAGE" == "all" || "$LANGUAGE" == "ruby" ]]; then
  while IFS= read -r manifest; do
    check_ruby "$(dirname "$manifest")"
  done < <(find "$REPO_ROOT"/ruby -maxdepth 3 -name Gemfile \
            -not -path '*/vendor/*' -not -path '*/.*/*' | sort)
fi

if [[ "$LANGUAGE" == "all" || "$LANGUAGE" == "php" ]]; then
  while IFS= read -r manifest; do
    check_php "$(dirname "$manifest")"
  done < <(find "$REPO_ROOT"/php -maxdepth 3 -name composer.json \
            -not -path '*/vendor/*' -not -path '*/.*/*' | sort)
fi

if [[ "$LANGUAGE" == "all" || "$LANGUAGE" == "elixir" ]]; then
  while IFS= read -r manifest; do
    check_elixir "$(dirname "$manifest")"
  done < <(find "$REPO_ROOT"/elixir -maxdepth 3 -name mix.exs \
            -not -path '*/deps/*' -not -path '*/_build/*' -not -path '*/.*/*' | sort)
fi

if [[ "$LANGUAGE" == "all" || "$LANGUAGE" == "csharp" ]]; then
  for dir in "$REPO_ROOT"/csharp/*/; do
    [[ -d "$dir" ]] || continue
    check_dotnet "$dir"
  done
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Summary"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Total outdated: $total_outdated"
echo "  Major bumps:    $total_major"
