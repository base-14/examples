# shellcheck shell=bash
# Common Azure CLI helpers + fail-loud delete primitives shared across
# components in this tree (currently windows-vm; reusable by future
# linux-vm / standalone-aks substrates).
#
# Source from a consumer's provision.sh or teardown.sh:
#
#     LIB="$SCRIPT_DIR/../lib"
#     source "$LIB/az-shared.sh"
#     az_shared_check_tools az jq bc curl openssl
#     az_shared_check_az_login
#
# Pure function library - must be sourced, not executed. Does not call
# `set -e`; the consumer chooses pipeline strictness.

# az_shared_check_tools <cmd1> [<cmd2> ...]
#   Verifies each named command exists on PATH. Emits one error per missing
#   tool and returns 1 if anything is missing.
az_shared_check_tools() {
  local missing=0
  for cmd in "$@"; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
      echo "ERROR: $cmd not found in PATH" >&2
      missing=1
    fi
  done
  if [ "$missing" = "1" ]; then
    return 1
  fi
}

# az_shared_check_az_login
#   Verifies `az` has a valid session. Returns 1 with a hint if not.
az_shared_check_az_login() {
  if ! az account show >/dev/null 2>&1; then
    echo "ERROR: az not logged in. Run 'az login' first." >&2
    return 1
  fi
}

# az_shared_delete_rg <rg-name>
#   Idempotent async resource-group delete via safe_delete (no-op if RG
#   already absent). Returns the underlying delete's exit code.
az_shared_delete_rg() {
  local rg="$1"
  safe_delete "Resource group $rg (async)" \
    az group show --name "$rg" -- \
    az group delete --name "$rg" --yes --no-wait
}

# az_shared_verify_zero_residue <rg-name>
#   Confirms the RG is gone. Returns 1 (with detail to stderr) if any residue
#   remains. Run AFTER az_shared_delete_rg's async delete has completed.
az_shared_verify_zero_residue() {
  local rg="$1"
  verify_zero_residue "Resource group $rg" \
    az group show --name "$rg" --query name -o tsv
}

# safe_delete <desc> <probe-cmd...> -- <delete-cmd...>
#   Cloud-agnostic fail-loud delete:
#   - Runs the probe command silently. If it fails (resource already gone),
#     emits "(already gone)" and returns 0 - idempotent.
#   - If the probe succeeds, runs the delete command. On non-zero exit,
#     emits the captured stderr inline and returns the delete's exit code
#     so the caller can decide whether to continue or abort.
#   - The literal `--` separator between probe args and delete args is
#     required; usage error returns 2.
safe_delete() {
  local desc="$1"
  shift
  local -a probe=() del=()
  local seen_sep=0
  local arg
  for arg in "$@"; do
    if [ "$seen_sep" = "0" ] && [ "$arg" = "--" ]; then
      seen_sep=1
      continue
    fi
    if [ "$seen_sep" = "0" ]; then
      probe+=("$arg")
    else
      del+=("$arg")
    fi
  done

  if [ "$seen_sep" != "1" ] || [ "${#probe[@]}" -eq 0 ] || [ "${#del[@]}" -eq 0 ]; then
    echo "ERROR: safe_delete usage: safe_delete <desc> <probe...> -- <delete...>" >&2
    return 2
  fi

  if ! "${probe[@]}" >/dev/null 2>&1; then
    echo "==> (already gone) $desc"
    return 0
  fi

  echo "==> deleting: $desc"
  local err_file rc
  err_file="$(mktemp)"
  if "${del[@]}" 2>"$err_file"; then
    rc=0
    echo "==> deleted: $desc"
  else
    rc=$?
    {
      echo "ERROR: delete FAILED: $desc (exit $rc)"
      echo "  delete command stderr:"
      sed 's/^/  | /' "$err_file"
      echo "  Resource may still exist and bill. Local state kept for retry."
    } >&2
  fi
  rm -f "$err_file"
  return "$rc"
}

# verify_zero_residue <label> <probe-cmd...>
#   Cloud-agnostic post-delete assertion. Runs the probe; if it succeeds
#   (resource still present) emits residue detail to stderr and returns 1.
#   If the probe fails (resource is gone), emits a confirmation and returns 0.
verify_zero_residue() {
  local label="$1"
  shift
  if [ "$#" -eq 0 ]; then
    echo "ERROR: verify_zero_residue usage: verify_zero_residue <label> <probe...>" >&2
    return 2
  fi
  local out
  if out="$("$@" 2>/dev/null)"; then
    {
      echo "ERROR: residue REMAINS: $label"
      if [ -n "$out" ]; then
        while IFS= read -r line; do echo "  | $line"; done <<<"$out"
      fi
      echo "  Teardown is NOT complete - investigate before declaring done."
    } >&2
    return 1
  fi
  echo "==> zero residue confirmed: $label"
  return 0
}
