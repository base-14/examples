#!/usr/bin/env bats

bats_require_minimum_version 1.5.0

setup() {
  LIB_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
  COMPONENTS_DIR="$(dirname "$LIB_DIR")"
  TEST_LOG="$(mktemp)"
  ALERTS_LOG_OVERRIDE="$TEST_LOG"
  export ALERTS_LOG_OVERRIDE
  export ALERT_OSASCRIPT_STUB=1
}

teardown() { rm -f "$TEST_LOG"; }

@test "alert writes to stderr with ALERT: prefix" {
  source "$LIB_DIR/alerting.sh"
  run --separate-stderr alert TEARDOWN-FAILURE aks-monitoring "RG not deleted"
  [ "$status" -eq 0 ]
  [[ "$stderr" == *"ALERT: TEARDOWN-FAILURE: aks-monitoring: RG not deleted"* ]]
}

@test "alert appends a timestamped line to alerts.log" {
  source "$LIB_DIR/alerting.sh"
  run alert PROVISION-DEVIATION aks-monitoring "extra resource detected"
  [ "$status" -eq 0 ]
  grep -q "PROVISION-DEVIATION" "$TEST_LOG"
  grep -q "aks-monitoring" "$TEST_LOG"
  grep -q "extra resource detected" "$TEST_LOG"
}

@test "alert_teardown_failure is a shortcut with correct class" {
  source "$LIB_DIR/alerting.sh"
  run alert_teardown_failure windows-vm "az group delete returned 1"
  [ "$status" -eq 0 ]
  grep -q "TEARDOWN-FAILURE" "$TEST_LOG"
}
