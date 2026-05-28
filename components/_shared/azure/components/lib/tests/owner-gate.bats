#!/usr/bin/env bats

bats_require_minimum_version 1.5.0

setup() {
  LIB_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
  source "$LIB_DIR/owner-gate.sh"
}

@test "gate_check_owner accepts allow-listed email" {
  run gate_check_owner "nilakanta@base14.io"
  [ "$status" -eq 0 ]
}

@test "gate_check_owner rejects non-allow-listed email" {
  run --separate-stderr gate_check_owner "someone@example.com"
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"not in owner allow-list"* ]]
}

@test "gate_confirm accepts literal 'yes'" {
  run bash -c "source $LIB_DIR/owner-gate.sh; echo yes | gate_confirm"
  [ "$status" -eq 0 ]
}

@test "gate_confirm rejects 'y'" {
  run bash -c "source $LIB_DIR/owner-gate.sh; echo y | gate_confirm"
  [ "$status" -ne 0 ]
}

@test "gate_confirm rejects empty input" {
  run bash -c "source $LIB_DIR/owner-gate.sh; echo '' | gate_confirm"
  [ "$status" -ne 0 ]
}

@test "gate_print_plan emits all expected fields" {
  run gate_print_plan \
    "Subscription" "Base14-Sandbox" \
    "Owner" "nilakanta@base14.io" \
    "Region" "centralindia" \
    "Cost" "\$0.80/hr"
  [ "$status" -eq 0 ]
  [[ "$output" == *"Subscription"* ]]
  [[ "$output" == *"Base14-Sandbox"* ]]
  [[ "$output" == *"centralindia"* ]]
}

@test "gate_provision with skip=1 does NOT prompt or consume stdin" {
  run bash -c "source $LIB_DIR/owner-gate.sh; printf 'no\n' | { gate_provision 1 Subscription Base14 Region eastus >/dev/null; read leftover; echo \"leftover=\$leftover\"; }"
  [ "$status" -eq 0 ]
  [[ "$output" == *"leftover=no"* ]]
}

@test "gate_provision with skip=0 reads typed 'yes' from stdin" {
  run bash -c "source $LIB_DIR/owner-gate.sh; echo yes | gate_provision 0 Subscription Base14 Region eastus"
  [ "$status" -eq 0 ]
}

@test "gate_provision does NOT call gate_check_owner implicitly" {
  # The substrate provision.sh must call gate_check_owner explicitly before
  # gate_provision so --yes cannot defeat the owner check. This test fails
  # if the helper grows an implicit owner check.
  run bash -c "source $LIB_DIR/owner-gate.sh; type gate_provision | grep -c 'gate_check_owner' || true"
  [ "$status" -eq 0 ]
  [[ "$output" =~ ^0$ ]]
}

@test "resolve_operator_ip honors OPERATOR_PUBLIC_IP env override" {
  export OPERATOR_PUBLIC_IP=203.0.113.42
  run bash -c "source $LIB_DIR/alerting.sh; source $LIB_DIR/owner-gate.sh; resolve_operator_ip test-substrate; echo \$OPERATOR_PUBLIC_IP"
  [ "$status" -eq 0 ]
  [[ "$output" == *"203.0.113.42"* ]]
  unset OPERATOR_PUBLIC_IP
}

@test "resolve_operator_ip rejects non-IPv4 input" {
  ALERTS_LOG_OVERRIDE="$(mktemp)"
  export ALERTS_LOG_OVERRIDE ALERT_OSASCRIPT_STUB=1
  run bash -c "source $LIB_DIR/alerting.sh; source $LIB_DIR/owner-gate.sh; OPERATOR_PUBLIC_IP=not-an-ip resolve_operator_ip test-substrate"
  [ "$status" -ne 0 ]
  rm -f "$ALERTS_LOG_OVERRIDE"
}
