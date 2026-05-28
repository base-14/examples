# shellcheck shell=bash
# Auto-shutdown via launchd LaunchAgent (macOS-native scheduling).
#
# Each substrate schedules a single-fire LaunchAgent at provision time that
# invokes the substrate's teardown.sh at the expiry deadline. Default 8h.
#
# The LaunchAgent invokes teardown with --yes --force so the auto-shutdown
# unconditionally bypasses the components-still-installed guard
# (helm-releases-present / iis-marker-present). At expiry, cost-protection
# trumps in-flight state: a stuck cluster with scout-collector still installed
# is exactly the scenario auto-shutdown exists to prevent.
#
# Sleep-at-deadline behavior: launchd catches up on wake within the calendar
# match window. If the laptop is asleep past the exact minute, launchd fires
# the job as soon as the laptop wakes inside the same Hour:Minute slot. If
# the laptop stays asleep past that hour entirely, the agent re-fires at
# the next match (next day same Hour:Minute). For 8h deadlines this is
# acceptable; for longer ones the operator should manually verify on wake.

LAUNCHAGENTS_DIR_DEFAULT="$HOME/Library/LaunchAgents"

_plist_path() {
  local substrate="$1"
  local dir="${LAUNCHAGENTS_DIR_OVERRIDE:-$LAUNCHAGENTS_DIR_DEFAULT}"
  echo "$dir/com.base14.${substrate}.expire.plist"
}

_label() {
  echo "com.base14.${1}.expire"
}

# schedule_teardown <substrate-dir> <substrate-name> <hours>
schedule_teardown() {
  local substrate_dir="$1" substrate_name="$2" hours="$3"
  local expiry epoch_now
  epoch_now="$(date +%s)"
  expiry=$((epoch_now + hours * 3600))

  cat > "$substrate_dir/.state" <<EOF
SUBSTRATE=$substrate_name
PROVISIONED_AT=$(date -u -r "$epoch_now" +%Y-%m-%dT%H:%M:%SZ)
EXPIRES_AT=$expiry
EXPIRES_AT_HUMAN=$(date -u -r "$expiry" +%Y-%m-%dT%H:%M:%SZ)
EOF

  local plist
  plist="$(_plist_path "$substrate_name")"
  mkdir -p "$(dirname "$plist")"
  local Y M D h m
  Y="$(date -r "$expiry" +%Y)"
  M="$(date -r "$expiry" +%-m)"
  D="$(date -r "$expiry" +%-d)"
  h="$(date -r "$expiry" +%-H)"
  m="$(date -r "$expiry" +%-M)"
  cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$(_label "$substrate_name")</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>-lc</string>
    <string>cd "$substrate_dir" &amp;&amp; ./teardown.sh --yes --force &gt;&gt; "$substrate_dir/auto-shutdown.log" 2&gt;&amp;1</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Year</key>   <integer>$Y</integer>
    <key>Month</key>  <integer>$M</integer>
    <key>Day</key>    <integer>$D</integer>
    <key>Hour</key>   <integer>$h</integer>
    <key>Minute</key> <integer>$m</integer>
  </dict>
  <key>StandardErrorPath</key>
  <string>$substrate_dir/auto-shutdown.log</string>
  <key>StandardOutPath</key>
  <string>$substrate_dir/auto-shutdown.log</string>
</dict>
</plist>
EOF

  if [ -z "${LAUNCHCTL_DRY_RUN:-}" ]; then
    launchctl bootstrap "gui/$(id -u)" "$plist" || {
      echo "WARN: launchctl bootstrap failed for $plist; agent NOT scheduled." >&2
      echo "Run 'launchctl bootstrap gui/$(id -u) \"$plist\"' manually." >&2
    }
  fi
  echo "Auto-shutdown scheduled for $substrate_name at $(date -r "$expiry")"
}

# check_deadline <substrate-dir>
#   returns 0 if state file says we still have time; 1 if expired or missing
check_deadline() {
  local substrate_dir="$1"
  [ -f "$substrate_dir/.state" ] || return 1
  local EXPIRES_AT
  EXPIRES_AT="$(grep '^EXPIRES_AT=' "$substrate_dir/.state" | cut -d= -f2)"
  local now
  now="$(date +%s)"
  [ "$now" -lt "$EXPIRES_AT" ]
}

# cancel_teardown <substrate-dir> <substrate-name>
cancel_teardown() {
  local substrate_dir="$1" substrate_name="$2"
  local plist
  plist="$(_plist_path "$substrate_name")"
  if [ -f "$plist" ] && [ -z "${LAUNCHCTL_DRY_RUN:-}" ]; then
    launchctl bootout "gui/$(id -u)" "$plist" 2>/dev/null || true
  fi
  rm -f "$plist" "$substrate_dir/.state"
}
