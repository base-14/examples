#!/usr/bin/env bash
# Provisions Windows Server 2022 VM with IIS feature for the IIS component
# example. Wires in the shared guardrails: auto-shutdown, SKU allow-list +
# cost ceiling, region SKU probe, owner allow-list, operator alerting on
# deviation.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SCRIPT_DIR/../lib"

# shellcheck source=../lib/alerting.sh
source "$LIB/alerting.sh"
# shellcheck source=../lib/sku-allowlist.sh
source "$LIB/sku-allowlist.sh"
# shellcheck source=../lib/owner-gate.sh
source "$LIB/owner-gate.sh"
# shellcheck source=../lib/auto-shutdown.sh
source "$LIB/auto-shutdown.sh"
# shellcheck source=../lib/az-shared.sh
source "$LIB/az-shared.sh"

SKIP_CONFIRM=0
AUTO_SHUTDOWN_HOURS=8
while [ $# -gt 0 ]; do
  case "$1" in
    --yes)               SKIP_CONFIRM=1; shift ;;
    --no-auto-shutdown)  AUTO_SHUTDOWN_HOURS=0; shift ;;
    --extend)
      AUTO_SHUTDOWN_HOURS="$2"
      if ! echo "$AUTO_SHUTDOWN_HOURS" | grep -qE '^[0-9]+$'; then
        echo "ERROR: --extend requires a positive integer (got '$AUTO_SHUTDOWN_HOURS')" >&2
        exit 2
      fi
      shift 2 ;;
    -h|--help)
      cat <<USAGE
Usage: $(basename "$0") [--yes] [--no-auto-shutdown] [--extend HOURS]

Env overrides:
  OWNER_ALLOWLIST          Space-separated allow-list (default: nilakanta@base14.io).
  COST_CEILING_USD_PER_HR  Per-substrate ceiling (default: 2.50).
  OPERATOR_PUBLIC_IP       Override operator IP for NSG RDP rule (default: probed via ifconfig.me).
  EXAMPLES_REPO_PATH       Path to the base14/examples repo (default: \$HOME/dev/base14/examples).
  EXAMPLES_REPO_SHA        Git SHA of base-14/examples to fetch setup-vm.ps1 from
                           (default: HEAD of EXAMPLES_REPO_PATH). Rejected if not a SHA.
  SETUP_SCRIPT_URI         Override the resolved URL entirely (last resort; bypasses SHA check).
USAGE
      exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

az_shared_check_tools az jq bc curl openssl
az_shared_check_az_login

resolve_owner_email
gate_check_owner "$OWNER_EMAIL"

resolve_operator_ip "windows-vm"

SUB_ID="$(az account show --query id -o tsv)"
SUB_NAME="$(az account show --query name -o tsv)"
NAME_PREFIX="${NAME_PREFIX:-b14winvm}"
DATE_STAMP="$(date -u +%Y%m%d)"
RG="${AZURE_RESOURCE_GROUP:-rg-${NAME_PREFIX}-${DATE_STAMP}}"
VM_SIZE="${VM_SIZE:-Standard_D2s_v3}"

# Pin the setup script to an immutable commit SHA, not a moving branch ref.
# `main` would let an in-flight merge change what the VM runs mid-provision.
EXAMPLES_REPO_PATH="${EXAMPLES_REPO_PATH:-$HOME/dev/base14/examples}"
EXAMPLES_REPO_SHA="${EXAMPLES_REPO_SHA:-$(cd "$EXAMPLES_REPO_PATH" && git rev-parse HEAD)}"
SETUP_SCRIPT_URI="${SETUP_SCRIPT_URI:-https://raw.githubusercontent.com/base-14/examples/${EXAMPLES_REPO_SHA}/components/_shared/azure/components/windows-vm/bicep/scripts/setup-vm.ps1}"

if ! echo "$EXAMPLES_REPO_SHA" | grep -qE '^[0-9a-f]{7,40}$'; then
  echo "ERROR: EXAMPLES_REPO_SHA='$EXAMPLES_REPO_SHA' does not look like a git SHA. Refusing to pull setup-vm.ps1 from a moving ref." >&2
  exit 1
fi

# Remote-reachability check: a local-only HEAD would 404 the CustomScriptExtension
# and leave a provisioned VM with no IIS + no OtelCollector service, taking ~7
# minutes to fail with a confusing trace. Only check the default URL path -- an
# operator-supplied SETUP_SCRIPT_URI (e.g., tunneled localhost for tests)
# bypasses both the SHA shape and remote-reachability checks.
DEFAULT_SETUP_URI="https://raw.githubusercontent.com/base-14/examples/${EXAMPLES_REPO_SHA}/components/_shared/azure/components/windows-vm/bicep/scripts/setup-vm.ps1"
if [ "$SETUP_SCRIPT_URI" = "$DEFAULT_SETUP_URI" ]; then
  if ! git -C "$EXAMPLES_REPO_PATH" branch -r --contains "$EXAMPLES_REPO_SHA" 2>/dev/null | grep -q 'origin/'; then
    echo "ERROR: EXAMPLES_REPO_SHA='$EXAMPLES_REPO_SHA' is not on any origin/* branch." >&2
    echo "       Push your branch first, or set SETUP_SCRIPT_URI to a reachable URL." >&2
    exit 1
  fi
fi

sku_validate windows-vm "$VM_SIZE"
HOURLY="$(sku_cost_per_hour windows-vm "$VM_SIZE" 1)"
cost_ceiling_check "$HOURLY" "Windows VM $VM_SIZE x1"

# Region SKU probe. Lowercased for consistency with aks-monitoring.
region_probe "$VM_SIZE" "windows-vm"

# Generate random admin password. Loop until we have a guaranteed 16+
# char base before the Ab1! complexity suffix; tr -d '/+=' on a base64
# stream can occasionally produce a shorter run.
ADMIN_PASSWORD=""
while [ "${#ADMIN_PASSWORD}" -lt 16 ]; do
  ADMIN_PASSWORD="$(openssl rand -base64 24 | tr -d '/+=' | head -c 16)"
done
ADMIN_PASSWORD="${ADMIN_PASSWORD}Ab1!"

gate_provision "$SKIP_CONFIRM" \
  "Subscription"  "$SUB_NAME ($SUB_ID)" \
  "Owner"         "$OWNER_EMAIL" \
  "Region"        "$REGION (probed)" \
  "Resource"      "Windows Server 2022 ($VM_SIZE) + IIS feature" \
  "Cost"          "\$${HOURLY}/hr (~\$$(printf '%.0f' "$(echo "$HOURLY * 730" | bc -l)")/mo always-on)" \
  "RDP source"    "${OPERATOR_PUBLIC_IP}/32 (NSG-pinned)" \
  "Setup script"  "$SETUP_SCRIPT_URI" \
  "Auto-shutdown" "$([ "$AUTO_SHUTDOWN_HOURS" -gt 0 ] && echo "${AUTO_SHUTDOWN_HOURS}h" || echo "DISABLED")"

echo "==> Creating RG: $RG"
az group create --name "$RG" --location "$REGION" --output none

echo "==> Deploying Bicep (~5 min)"
DEPLOYMENT_NAME="winvm-$(date +%s)"
az deployment group create \
  --resource-group "$RG" \
  --name "$DEPLOYMENT_NAME" \
  --template-file "$SCRIPT_DIR/bicep/main.bicep" \
  --parameters \
      namePrefix="$NAME_PREFIX" \
      vmSize="$VM_SIZE" \
      adminPassword="$ADMIN_PASSWORD" \
      operatorPublicIp="$OPERATOR_PUBLIC_IP" \
      setupScriptUri="$SETUP_SCRIPT_URI" \
  --output none

VM_NAME="$(az deployment group show -g "$RG" -n "$DEPLOYMENT_NAME" --query 'properties.outputs.vmName.value' -o tsv)"
PUBLIC_IP="$(az vm show -d --resource-group "$RG" --name "$VM_NAME" --query publicIps -o tsv)"

cat > "$SCRIPT_DIR/.endpoint" <<EOF
WINVM_NAME=$VM_NAME
WINVM_RG=$RG
WINVM_SUB=$SUB_ID
WINVM_REGION=$REGION
WINVM_PUBLIC_IP=$PUBLIC_IP
WINVM_ADMIN_USER=b14admin
WINVM_ADMIN_PASSWORD=$ADMIN_PASSWORD
EOF
chmod 600 "$SCRIPT_DIR/.endpoint"

# Provisioning-deviation check (Windows VM RG typically ~7: VM, OS disk, NIC,
# NSG, VNet, PIP, VM extension).
ACTUAL="$(az resource list --resource-group "$RG" --query 'length(@)' -o tsv)"
if [ "$ACTUAL" -gt 9 ]; then
  alert_provision_deviation "windows-vm" "RG $RG has $ACTUAL resources, expected ~7"
fi

if [ "$AUTO_SHUTDOWN_HOURS" -gt 0 ]; then
  schedule_teardown "$SCRIPT_DIR" "windows-vm" "$AUTO_SHUTDOWN_HOURS"
fi

echo "==> Provisioned. RDP to $PUBLIC_IP (creds in .endpoint, chmod 600)"
