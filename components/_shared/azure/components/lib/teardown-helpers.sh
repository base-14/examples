# shellcheck shell=bash
# Common teardown helpers shared across substrates.

# wait_rg_gone <substrate> <rg> <timeout_seconds> <poll_seconds>
#   Polls `az group show $rg` until it 404s or timeout. On timeout: emits
#   alert_teardown_failure (substrate-name) + exit 1.
#
#   Optional: caller may define a shell function `wait_rg_gone_diag` that
#   prints a one-line diagnostic (e.g., AKS provisioningState). Its output is
#   appended to the timeout alert message.
wait_rg_gone() {
  local substrate="$1" rg="$2" timeout_s="$3" poll_s="$4"
  local elapsed=0 diag=""
  while az group show --name "$rg" >/dev/null 2>&1; do
    if [ "$elapsed" -ge "$timeout_s" ]; then
      if declare -F wait_rg_gone_diag >/dev/null 2>&1; then
        diag="; $(wait_rg_gone_diag 2>/dev/null || true)"
      fi
      alert_teardown_failure "$substrate" "RG $rg still present after ${timeout_s}s${diag}"
      exit 1
    fi
    sleep "$poll_s"
    elapsed=$((elapsed + poll_s))
  done
}
