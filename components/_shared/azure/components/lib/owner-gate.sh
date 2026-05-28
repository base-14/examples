# shellcheck shell=bash
# Owner-gated provisioning (substrate only).

OWNER_ALLOWLIST_DEFAULT="nilakanta@base14.io"

# gate_check_owner <email>
gate_check_owner() {
  local email="$1"
  local allowed="${OWNER_ALLOWLIST:-$OWNER_ALLOWLIST_DEFAULT}"
  for ok in $allowed; do
    if [ "$ok" = "$email" ]; then
      return 0
    fi
  done
  echo "Owner '$email' not in owner allow-list (allowed: $allowed)" >&2
  return 1
}

# gate_confirm  (reads stdin, requires literal 'yes')
gate_confirm() {
  local input
  read -r input
  if [ "$input" != "yes" ]; then
    echo "Aborted (got '$input', expected literal 'yes')." >&2
    return 1
  fi
}

# gate_print_plan <key> <value> [<key> <value>...]
gate_print_plan() {
  local box='═══════════════════════════════════════════════════'
  echo "$box"
  echo "Provision plan"
  echo "$box"
  while [ $# -ge 2 ]; do
    printf '  %-15s %s\n' "${1}:" "$2"
    shift 2
  done
  echo "$box"
  echo ""
}

# gate_provision <skip-confirm> <plan-args...>
#   Prints the plan, then prompts for typed 'yes' unless skip-confirm is '1'.
#   Does NOT call gate_check_owner — substrate scripts must call that first,
#   so --yes cannot defeat the owner check.
gate_provision() {
  local skip="$1"
  shift
  gate_print_plan "$@"
  if [ "$skip" = "1" ]; then
    echo "(--yes bypass active; skipping interactive confirmation)"
    return 0
  fi
  printf "Type 'yes' to confirm: "
  gate_confirm
}

# resolve_operator_ip <substrate>
#   Resolves OPERATOR_PUBLIC_IP from env or curl ifconfig.me. Validates IPv4.
#   alert_provision_deviation + exit 1 on failure. Caller must source alerting.sh.
resolve_operator_ip() {
  local substrate="$1"
  OPERATOR_PUBLIC_IP="${OPERATOR_PUBLIC_IP:-$(curl -s --max-time 5 https://ifconfig.me)}"
  if ! echo "$OPERATOR_PUBLIC_IP" | grep -qE '^[0-9]{1,3}(\.[0-9]{1,3}){3}$'; then
    echo "ERROR: could not resolve operator public IP (got '$OPERATOR_PUBLIC_IP'). Set OPERATOR_PUBLIC_IP manually." >&2
    alert_provision_deviation "$substrate" "operator IP probe failed; provision aborted"
    exit 1
  fi
}

# resolve_owner_email
#   Sets OWNER_EMAIL via `az ad signed-in-user show` (mail, falling back to UPN).
#   Uses JMESPath `||` so a null `mail` field falls through to userPrincipalName
#   in a single az call. Shell-level `||` doesn't work here because az exits 0
#   with empty stdout when the queried field is null (e.g. Personal tenants
#   without a mail value). Empty result is left to gate_check_owner to reject.
resolve_owner_email() {
  # shellcheck disable=SC2034  # OWNER_EMAIL is consumed by the caller
  OWNER_EMAIL="$(az ad signed-in-user show --query "mail || userPrincipalName" -o tsv)"
}
