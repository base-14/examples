#!/usr/bin/env bats

bats_require_minimum_version 1.5.0

setup() {
  LIB_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
  TEST_DIR="$(mktemp -d)"
  TEST_PLIST_DIR="$(mktemp -d)"
  LAUNCHCTL_DRY_RUN=1
  export LAUNCHCTL_DRY_RUN LAUNCHAGENTS_DIR_OVERRIDE="$TEST_PLIST_DIR"
  source "$LIB_DIR/auto-shutdown.sh"
}

teardown() { rm -rf "$TEST_DIR" "$TEST_PLIST_DIR"; }

@test "schedule_teardown writes deadline to .state" {
  run schedule_teardown "$TEST_DIR" "test-substrate" 8
  [ "$status" -eq 0 ]
  [ -f "$TEST_DIR/.state" ]
  grep -q "EXPIRES_AT=" "$TEST_DIR/.state"
}

@test "schedule_teardown writes a plist in LAUNCHAGENTS_DIR_OVERRIDE" {
  run schedule_teardown "$TEST_DIR" "test-substrate" 8
  [ "$status" -eq 0 ]
  ls "$TEST_PLIST_DIR"/com.base14.test-substrate.expire.plist
}

@test "scheduled plist invokes teardown.sh with --yes --force so auto-shutdown bypasses the components-still-installed guard" {
  schedule_teardown "$TEST_DIR" "test-substrate" 8
  grep -q -- "--yes --force" "$TEST_PLIST_DIR/com.base14.test-substrate.expire.plist"
}

@test "check_deadline returns 0 when deadline is in future" {
  schedule_teardown "$TEST_DIR" "test-substrate" 8
  run check_deadline "$TEST_DIR"
  [ "$status" -eq 0 ]
}

@test "check_deadline returns 1 when deadline is in past" {
  echo "EXPIRES_AT=$(($(date +%s) - 60))" > "$TEST_DIR/.state"
  run check_deadline "$TEST_DIR"
  [ "$status" -ne 0 ]
}

@test "cancel_teardown removes plist and state" {
  schedule_teardown "$TEST_DIR" "test-substrate" 8
  run cancel_teardown "$TEST_DIR" "test-substrate"
  [ "$status" -eq 0 ]
  [ ! -f "$TEST_DIR/.state" ]
  [ ! -f "$TEST_PLIST_DIR/com.base14.test-substrate.expire.plist" ]
}
