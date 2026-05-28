#!/usr/bin/env bash
# Tears down the Windows VM substrate. Asserts zero-residue, refuses to run
# if the IIS-component .installed marker is present (override with --force),
# alerts on teardown failure.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SCRIPT_DIR/../lib"

# shellcheck source=../lib/alerting.sh
source "$LIB/alerting.sh"
# shellcheck source=../lib/auto-shutdown.sh
source "$LIB/auto-shutdown.sh"
# shellcheck source=../lib/owner-gate.sh
source "$LIB/owner-gate.sh"
# shellcheck source=../lib/teardown-helpers.sh
source "$LIB/teardown-helpers.sh"
# shellcheck source=../lib/az-shared.sh
source "$LIB/az-shared.sh"

SKIP_CONFIRM=0 FORCE=0
for arg in "$@"; do
  case "$arg" in
    --yes)   SKIP_CONFIRM=1 ;;
    --force) FORCE=1 ;;
    -h|--help) echo "Usage: $(basename "$0") [--yes] [--force]"; exit 0 ;;
    *) echo "Unknown arg: $arg" >&2; exit 2 ;;
  esac
done

ENDPOINT_FILE="$SCRIPT_DIR/.endpoint"
if [ ! -f "$ENDPOINT_FILE" ]; then
  echo "No .endpoint; nothing to tear down."
  cancel_teardown "$SCRIPT_DIR" "windows-vm"
  exit 0
fi
# shellcheck disable=SC1090
source "$ENDPOINT_FILE"
RG="${WINVM_RG:?missing}"
VM_NAME="${WINVM_NAME:?missing}"

# Refuse teardown if the IIS example is still installed against this VM.
# Without RDP'ing in to inspect the VM, the closest proxy is the local
# .installed marker that iis-telemetry/provision.sh writes alongside itself.
# Path resolution: SCRIPT_DIR = examples/components/_shared/azure/components/windows-vm.
# COMPONENTS_ROOT = up 4 from SCRIPT_DIR = examples/components.
# Marker = examples/components/iis-telemetry/.installed.
COMPONENTS_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
IIS_MARKER="$COMPONENTS_ROOT/iis-telemetry/.installed"
if [ "$FORCE" != "1" ] && [ -f "$IIS_MARKER" ]; then
  echo "ERROR: examples/components/iis-telemetry appears installed (marker: $IIS_MARKER)." >&2
  echo "       Run its teardown.sh first, or pass --force." >&2
  exit 1
fi

if [ "$SKIP_CONFIRM" != "1" ]; then
  echo "About to delete Windows VM RG: $RG"
  printf "Type 'yes' to confirm: "
  gate_confirm
fi

TEARDOWN_START="$(date +%s)"

if ! az_shared_delete_rg "$RG"; then
  alert_teardown_failure "windows-vm" "az_shared_delete_rg failed for $RG"
  exit 1
fi

wait_rg_gone_diag() {
  local state
  state="$(az vm show --resource-group "$RG" --name "$VM_NAME" --query 'provisioningState' -o tsv 2>/dev/null || echo "(query failed)")"
  echo "VM provisioningState=$state"
}
wait_rg_gone "windows-vm" "$RG" 600 15

TEARDOWN_ELAPSED=$(($(date +%s) - TEARDOWN_START))
if [ "$TEARDOWN_ELAPSED" -gt 300 ]; then
  alert_teardown_failure "windows-vm" "Teardown took ${TEARDOWN_ELAPSED}s (>5min)"
fi

if ! az_shared_verify_zero_residue "$RG"; then
  alert_residue "windows-vm" "verify_zero_residue failed for RG $RG"
  exit 1
fi

cancel_teardown "$SCRIPT_DIR" "windows-vm"
rm -f "$ENDPOINT_FILE"

echo "==> Torn down."
