#!/usr/bin/env bats

bats_require_minimum_version 1.5.0

setup() {
  LIB_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
  ALERTS_LOG_OVERRIDE="$(mktemp)"
  export ALERTS_LOG_OVERRIDE ALERT_OSASCRIPT_STUB=1
  TMP_BIN="$(mktemp -d)"
}

teardown() {
  rm -f "$ALERTS_LOG_OVERRIDE"
  rm -rf "$TMP_BIN"
}

@test "wait_rg_gone returns when az group show 404s on first poll" {
  cat > "$TMP_BIN/az" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
  chmod +x "$TMP_BIN/az"
  PATH="$TMP_BIN:$PATH" run bash -c "source $LIB_DIR/alerting.sh; source $LIB_DIR/teardown-helpers.sh; wait_rg_gone test-substrate test-rg 10 1"
  [ "$status" -eq 0 ]
}

@test "wait_rg_gone alerts + exits 1 on timeout" {
  cat > "$TMP_BIN/az" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
  chmod +x "$TMP_BIN/az"
  PATH="$TMP_BIN:$PATH" run bash -c "source $LIB_DIR/alerting.sh; source $LIB_DIR/teardown-helpers.sh; wait_rg_gone test-substrate test-rg 2 1"
  [ "$status" -ne 0 ]
  grep -q "TEARDOWN-FAILURE" "$ALERTS_LOG_OVERRIDE"
  grep -q "still present after 2s" "$ALERTS_LOG_OVERRIDE"
}

@test "wait_rg_gone appends caller-provided diagnostic on timeout" {
  cat > "$TMP_BIN/az" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
  chmod +x "$TMP_BIN/az"
  export PATH="$TMP_BIN:$PATH"
  run bash -c "
    source $LIB_DIR/alerting.sh
    source $LIB_DIR/teardown-helpers.sh
    wait_rg_gone_diag() { echo 'state=Stuck'; }
    wait_rg_gone test-substrate test-rg 2 1
  " || true
  grep -q 'state=Stuck' "$ALERTS_LOG_OVERRIDE"
}
