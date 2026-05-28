#!/usr/bin/env bats

bats_require_minimum_version 1.5.0

setup() {
  LIB_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
  source "$LIB_DIR/sku-allowlist.sh"
}

@test "sku_validate accepts allowed AKS SKUs" {
  run sku_validate aks-node Standard_D4s_v3
  [ "$status" -eq 0 ]
  run sku_validate aks-node Standard_D8s_v3
  [ "$status" -eq 0 ]
}

@test "sku_validate rejects too-large AKS SKU" {
  run --separate-stderr sku_validate aks-node Standard_D32s_v5
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"not in allow-list"* ]]
}

@test "sku_validate accepts Standard_D2s_v3 for windows-vm" {
  run sku_validate windows-vm Standard_D2s_v3
  [ "$status" -eq 0 ]
}

@test "sku_validate rejects other SKUs for windows-vm" {
  run sku_validate windows-vm Standard_D4s_v3
  [ "$status" -ne 0 ]
}

@test "sku_validate rejects retired ACI kind" {
  run --separate-stderr sku_validate aci aci-1vcpu-1.5gb
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"unknown kind"* ]]
}

@test "sku_cost_per_hour returns numeric centralindia hourly cost" {
  run sku_cost_per_hour aks-node Standard_D4s_v3 3
  [ "$status" -eq 0 ]
  [[ "$output" =~ ^0\.[4-7][0-9]$ ]]
}

@test "sku_cost_per_hour priced aks-lb standard (N2)" {
  run sku_cost_per_hour aks-lb standard 1
  [ "$status" -eq 0 ]
  [[ "$output" == "0.03" ]] || [[ "$output" == "0.02" ]]
}

@test "cost_ceiling_check fails above 2.50 USD/hr" {
  run --separate-stderr cost_ceiling_check 2.75 "AKS Standard_D8s_v3 x6"
  [ "$status" -ne 0 ]
  [[ "$stderr" == *"AKS Standard_D8s_v3 x6"* ]]
  [[ "$stderr" == *"2.50"* ]]
}

@test "cost_ceiling_check passes at or below 2.50 USD/hr" {
  run cost_ceiling_check 2.49 "single substrate"
  [ "$status" -eq 0 ]
}

@test "region_probe picks the first region whose az list-skus matches" {
  TMP_BIN="$(mktemp -d)"
  cat > "$TMP_BIN/az" <<EOF
#!/usr/bin/env bash
# Stub: only southindia reports the SKU as available.
case "\$*" in
  *"--location southindia --size Standard_D4s_v3"*) echo "Standard_D4s_v3"; exit 0 ;;
  *) exit 0 ;;
esac
EOF
  chmod +x "$TMP_BIN/az"
  PATH="$TMP_BIN:$PATH" \
  AZURE_REGION=centralindia \
  ALERTS_LOG_OVERRIDE="$(mktemp)" ALERT_OSASCRIPT_STUB=1 \
  run bash -c "source $LIB_DIR/alerting.sh; source $LIB_DIR/sku-allowlist.sh; region_probe Standard_D4s_v3 test-substrate; echo \$REGION"
  [ "$status" -eq 0 ]
  [[ "$output" == *"southindia"* ]]
  rm -rf "$TMP_BIN"
}

@test "region_probe alerts + exits when no region has the SKU" {
  TMP_BIN="$(mktemp -d)"
  cat > "$TMP_BIN/az" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
  chmod +x "$TMP_BIN/az"
  PATH="$TMP_BIN:$PATH" \
  ALERTS_LOG_OVERRIDE="$(mktemp)" ALERT_OSASCRIPT_STUB=1 \
  run bash -c "source $LIB_DIR/alerting.sh; source $LIB_DIR/sku-allowlist.sh; region_probe Standard_D32s_v5 test-substrate"
  [ "$status" -ne 0 ]
  rm -rf "$TMP_BIN"
}
