#!/usr/bin/env bats

bats_require_minimum_version 1.5.0

setup() {
  LIB_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
  source "$LIB_DIR/az-shared.sh"
}

@test "az_shared_check_tools passes when every tool is present" {
  run az_shared_check_tools bash ls
  [ "$status" -eq 0 ]
}

@test "az_shared_check_tools fails and names the missing tool" {
  run --separate-stderr az_shared_check_tools bash totally-not-on-path
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"totally-not-on-path not found"* ]]
}

@test "az_shared_check_az_login fails when az is missing from PATH" {
  run --separate-stderr bash -c "PATH=/usr/bin:/bin; source $LIB_DIR/az-shared.sh; az_shared_check_az_login"
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"az not logged in"* ]]
}

@test "safe_delete returns 0 + 'already gone' when probe fails" {
  run safe_delete "fake-resource" \
    false -- \
    true
  [ "$status" -eq 0 ]
  [[ "$output" == *"already gone"* ]]
}

@test "safe_delete runs delete when probe succeeds" {
  run safe_delete "fake-resource" \
    true -- \
    true
  [ "$status" -eq 0 ]
  [[ "$output" == *"deleting: fake-resource"* ]]
  [[ "$output" == *"deleted: fake-resource"* ]]
}

@test "safe_delete surfaces delete failure with stderr context" {
  run --separate-stderr safe_delete "fake-resource" \
    true -- \
    bash -c "echo 'underlying failure detail' >&2; exit 7"
  [ "$status" -eq 7 ]
  [[ "$stderr" == *"delete FAILED"* ]]
  [[ "$stderr" == *"underlying failure detail"* ]]
}

@test "safe_delete rejects missing -- separator with usage error" {
  run --separate-stderr safe_delete "fake-resource" true true
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"usage"* ]]
}

@test "verify_zero_residue returns 0 when probe fails (resource gone)" {
  run verify_zero_residue "fake-resource" false
  [ "$status" -eq 0 ]
  [[ "$output" == *"zero residue confirmed"* ]]
}

@test "verify_zero_residue returns 1 and emits residue when probe succeeds" {
  run --separate-stderr verify_zero_residue "fake-resource" bash -c "echo lingering-thing; exit 0"
  [ "$status" -eq 1 ]
  [[ "$stderr" == *"residue REMAINS"* ]]
  [[ "$stderr" == *"lingering-thing"* ]]
}

@test "verify_zero_residue rejects missing probe with usage error" {
  run --separate-stderr verify_zero_residue "fake-resource"
  [ "$status" -eq 2 ]
  [[ "$stderr" == *"usage"* ]]
}
