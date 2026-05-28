# shellcheck shell=bash
# Operator alerting on provisioning deviation or teardown failure.
#
# Three channels: macOS notification (osascript), stderr ALERT line,
# append-only alerts.log. Source from substrate scripts.

ALERTS_LOG_DEFAULT="${HOME}/.local/state/base14-substrate/alerts.log"
mkdir -p "$(dirname "$ALERTS_LOG_DEFAULT")" 2>/dev/null || true

# alert <class> <substrate> <message>
alert() {
  local class="$1" substrate="$2" message="$3"
  local log="${ALERTS_LOG_OVERRIDE:-$ALERTS_LOG_DEFAULT}"
  local ts
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

  echo "ALERT: ${class}: ${substrate}: ${message}" >&2

  printf '%s\t%s\t%s\t%s\n' "$ts" "$class" "$substrate" "$message" >> "$log"

  if [ -z "${ALERT_OSASCRIPT_STUB:-}" ] && command -v osascript >/dev/null 2>&1; then
    osascript -e "display notification \"${substrate}: ${message}\" with title \"${class}\" sound name \"Sosumi\"" >/dev/null 2>&1 || true
  fi
}

alert_provision_deviation() { alert PROVISION-DEVIATION "$1" "$2"; }
alert_teardown_failure()    { alert TEARDOWN-FAILURE    "$1" "$2"; }
alert_residue()             { alert RESIDUE             "$1" "$2"; }
