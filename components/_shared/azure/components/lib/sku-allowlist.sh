# shellcheck shell=bash
# SKU allow-list, session cost ceiling, and region SKU probe.
#
# Centralindia on-demand pricing as of 2026-05. Update when pricing
# changes materially (>10%). Costs are USD/hr per single instance.

# sku_validate <kind> <sku>
#   kind in {aks-node, windows-vm}
sku_validate() {
  local kind="$1" sku="$2"
  local allowed=""
  case "$kind" in
    aks-node)    allowed="Standard_D4s_v3 Standard_D8s_v3" ;;
    windows-vm)  allowed="Standard_D2s_v3" ;;
    *)
      echo "sku_validate: unknown kind '$kind'" >&2
      return 2
      ;;
  esac
  for ok in $allowed; do
    if [ "$ok" = "$sku" ]; then
      return 0
    fi
  done
  echo "SKU '$sku' not in allow-list for kind '$kind' (allowed: $allowed)" >&2
  return 1
}

# sku_cost_per_hour <kind> <sku> <count>
#   prints total $/hr (count * unit price) to stdout
sku_cost_per_hour() {
  local kind="$1" sku="$2" count="$3"
  local unit=""
  case "${kind}:${sku}" in
    aks-node:Standard_D4s_v3)   unit="0.192" ;;
    aks-node:Standard_D8s_v3)   unit="0.384" ;;
    aks-lb:standard)            unit="0.025" ;;
    windows-vm:Standard_D2s_v3) unit="0.17"  ;;
    *)
      echo "sku_cost_per_hour: no price for '${kind}:${sku}'" >&2
      return 2
      ;;
  esac
  printf '%.2f\n' "$(echo "$unit * $count" | bc -l)"
}

# cost_ceiling_check <total_hourly_usd> <description>
#   prints + fails if total > $2.50/hr (per-substrate ceiling from the design spec).
#   Override via COST_CEILING_USD_PER_HR for one-off testing.
COST_CEILING_USD_PER_HR="${COST_CEILING_USD_PER_HR:-2.50}"
cost_ceiling_check() {
  local total="$1" desc="$2"
  local over
  over="$(echo "$total > $COST_CEILING_USD_PER_HR" | bc -l)"
  if [ "$over" = "1" ]; then
    echo "Cost ceiling exceeded: $desc => \$$total/hr (limit \$$COST_CEILING_USD_PER_HR/hr)" >&2
    return 1
  fi
}

# region_probe <sku> <substrate>
#   Iterates AZURE_REGION (default centralindia), then southindia, then eastus.
#   Sets REGION (lowercased) to the first region where az reports the SKU as
#   available. alert_provision_deviation + exit 1 if none succeed.
#   Caller must source alerting.sh.
region_probe() {
  local sku="$1" substrate="$2"
  local cand
  local candidates=("${AZURE_REGION:-centralindia}" "southindia" "eastus")
  REGION=""
  for cand in "${candidates[@]}"; do
    if az vm list-skus --location "$cand" --size "$sku" --query '[0].name' -o tsv 2>/dev/null | grep -q "$sku"; then
      REGION="$(echo "$cand" | tr '[:upper:]' '[:lower:]')"
      break
    fi
  done
  if [ -z "$REGION" ]; then
    alert_provision_deviation "$substrate" "no region has $sku available (tried: ${candidates[*]})"
    exit 1
  fi
}
