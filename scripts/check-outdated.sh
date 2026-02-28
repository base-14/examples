#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Legacy projects to skip
SKIP_PROJECTS="go119-gin191-postgres|ruby27-rails52-mysql8|php8-laravel8-sqlite"

LANGUAGE="all"
MAJOR_ONLY=false

usage() {
  echo "Usage: $0 [--language nodejs|python|go|rust|java|all] [--major-only]"
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
      latest=$(echo "$line" | awk '{print $NF}' | sed 's/[\^~]//')

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
  if [[ ! -f "$dir/requirements.txt" ]]; then return; fi

  print_header "python/$name"

  local count=0
  local majors=0

  while IFS= read -r line; do
    [[ -z "$line" || "$line" =~ ^# ]] && continue
    local pkg current
    pkg=$(echo "$line" | sed 's/[>=<~!].*//')
    current=$(echo "$line" | grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?' | head -1)
    [[ -z "$current" ]] && continue

    local latest
    latest=$(pip index versions "$pkg" 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?' | head -1 || true)
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
  done < "$dir/requirements.txt"

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
    latest=$(echo "$line" | grep -oE '\[v[^\]]+\]' | tr -d '[]')
    [[ -z "$latest" ]] && continue

    local cur_major lat_major bump_type
    cur_major=$(echo "$current" | grep -oE '^v[0-9]+' | tr -d 'v')
    lat_major=$(echo "$latest" | grep -oE '^v[0-9]+' | tr -d 'v')

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

  if [[ -f "$dir/gradlew" ]]; then
    local output
    output=$(cd "$dir" && ./gradlew dependencyUpdates --no-daemon 2>/dev/null | grep -E '^\s+-' || true)
    if [[ -z "$output" ]]; then
      echo "  All up to date (or run manually to verify)"
    else
      echo "$output"
    fi
  elif [[ -f "$dir/pom.xml" ]]; then
    local output
    output=$(cd "$dir" && mvn versions:display-dependency-updates -q 2>/dev/null | grep -E '^\[INFO\].*->' || true)
    if [[ -z "$output" ]]; then
      echo "  All up to date (or run manually to verify)"
    else
      echo "$output"
    fi
  else
    echo "  No build tool detected"
  fi
}

echo "Checking outdated dependencies..."
echo "Language: $LANGUAGE | Major only: $MAJOR_ONLY"

if [[ "$LANGUAGE" == "all" || "$LANGUAGE" == "nodejs" ]]; then
  for dir in "$REPO_ROOT"/nodejs/*/; do
    [[ -d "$dir" ]] || continue
    check_nodejs "$dir"
  done
fi

if [[ "$LANGUAGE" == "all" || "$LANGUAGE" == "python" ]]; then
  for dir in "$REPO_ROOT"/python/*/; do
    [[ -d "$dir" ]] || continue
    check_python "$dir"
  done
fi

if [[ "$LANGUAGE" == "all" || "$LANGUAGE" == "go" ]]; then
  for dir in "$REPO_ROOT"/go/*/; do
    [[ -d "$dir" ]] || continue
    check_go "$dir"
  done
fi

if [[ "$LANGUAGE" == "all" || "$LANGUAGE" == "rust" ]]; then
  for dir in "$REPO_ROOT"/rust/*/; do
    [[ -d "$dir" ]] || continue
    check_rust "$dir"
  done
fi

if [[ "$LANGUAGE" == "all" || "$LANGUAGE" == "java" ]]; then
  for dir in "$REPO_ROOT"/java/*/; do
    [[ -d "$dir" ]] || continue
    check_java "$dir"
  done
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Summary"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Total outdated: $total_outdated"
echo "  Major bumps:    $total_major"
