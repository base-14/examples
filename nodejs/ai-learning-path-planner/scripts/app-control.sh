#!/usr/bin/env bash

# ---------------------------------------------------------------------------
# app-control.sh - start, stop and restart the planner for the three scripts
# that need to change its configuration mid-run.
#
# Sourced, never executed. test-api.sh, verify-scout.sh and measure-catalogue.sh
# all have to bring the app back up with one variable changed: TOOL_CATALOGUE for
# the measurement, PRICE_MODEL so cost is a real number, OLLAMA_BASE_URL for the
# model-unreachable case. Example 1 carries its own copy of that logic in each of
# its two scripts; there are three here, so it lives in one file instead.
#
# Two ways to run the service, and both are supported because both are real:
#
#   compose  the app runs as the `app` Compose service. Restarted with
#            `docker compose up -d app` and the overrides passed through env.
#   host     the app runs as a node process this script started, from dist/.
#            Restarted by sending SIGTERM, which flushes the pending span batch
#            and the pending metric interval, then launching it again.
#
# APP_MODE picks one. Left unset, compose wins when `docker compose ps` shows a
# running app service, and host otherwise.
#
# Every caller must call app_control_init before anything else, and should run
# restore_app from an EXIT trap: an interrupted run otherwise leaves the app on a
# shortened catalogue or pointing at a port nothing listens on.
# ---------------------------------------------------------------------------

APP_PID_FILE="${APP_PID_FILE:-/tmp/ai-learning-path-planner-app.pid}"
APP_LOG_FILE="${APP_LOG_FILE:-/tmp/ai-learning-path-planner-app.log}"

# The overrides restore_app puts back, captured by app_control_init. Empty until
# then, which is what makes restore_app a no-op on a script that never restarted
# anything.
APP_BASELINE_SET=0
APP_BASELINE=()
APP_MODE_RESOLVED=""

app_is_composed() {
    docker compose ps --status running --services 2>/dev/null | grep -qx app
}

app_health_url() {
    echo "${API_URL:-http://localhost:3000}/health"
}

app_is_up() {
    curl -sf "$(app_health_url)" >/dev/null 2>&1
}

# Waits for the app to answer /health. 120 seconds: a cold start reads and
# decompresses the corpus artifact before it listens.
app_wait_healthy() {
    local retries=60
    while [ "$retries" -gt 0 ]; do
        if app_is_up; then
            return 0
        fi
        retries=$((retries - 1))
        sleep 2
    done
    return 1
}

app_control_init() {
    if [ -n "${APP_MODE:-}" ]; then
        APP_MODE_RESOLVED="$APP_MODE"
    elif app_is_composed; then
        APP_MODE_RESOLVED="compose"
    else
        APP_MODE_RESOLVED="host"
    fi

    # The settings every restart goes back to. Passed explicitly on every start so
    # nothing depends on what happens to be exported in the caller's shell.
    #
    # OLLAMA_BASE_URL is per mode, and it has to be: Ollama runs on the host, so a
    # container reaches it at host.docker.internal while the host itself cannot
    # resolve that name, and localhost inside a container is the container. A single
    # baseline of localhost restarted the composed app onto an address nothing
    # answers, which failed every model call for the rest of the run. The /api suffix
    # is on both forms because ollama-ai-provider-v2 appends its paths straight onto
    # this value, so without it every call answers 404.
    local default_base_url="http://localhost:11434/api"
    if [ "$APP_MODE_RESOLVED" = "compose" ]; then
        default_base_url="http://host.docker.internal:11434/api"
    fi

    APP_BASELINE=(
        "OLLAMA_BASE_URL=${OLLAMA_BASE_URL:-$default_base_url}"
        "TOOL_CATALOGUE=${TOOL_CATALOGUE:-deferred}"
        # Left empty so the service applies its own default. Naming a row here would measure
        # a cost the shipped configuration never produces. A borrowed rate carries
        # base14.gen_ai.cost.simulated=true; it is a stand-in, not a bill.
        "PRICE_MODEL=${PRICE_MODEL:-}"
    )
    APP_BASELINE_SET=1
}

app_mode() {
    echo "$APP_MODE_RESOLVED"
}

# True when this script can put the app back the way it found it. Callers use it to
# skip a section rather than fail it, the way example 1 skips its error matrix.
app_can_restart() {
    if [ "$APP_MODE_RESOLVED" = "compose" ]; then
        docker compose config --services 2>/dev/null | grep -qx app
        return $?
    fi
    [ -d dist ] && [ -f dist/index.js ]
}

app_stop_host() {
    if [ ! -f "$APP_PID_FILE" ]; then
        return 0
    fi
    local pid
    pid=$(cat "$APP_PID_FILE" 2>/dev/null)
    rm -f "$APP_PID_FILE"
    if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
        return 0
    fi
    # SIGTERM, not SIGKILL. src/telemetry.ts shuts the SDK down on SIGTERM and
    # SIGINT, and that shutdown is what flushes the pending span batch and the
    # pending metric interval. Killing it any other way drops both silently and the
    # assertions then fail on data that was never exported.
    kill -TERM "$pid" 2>/dev/null
    local retries=30
    while [ "$retries" -gt 0 ] && kill -0 "$pid" 2>/dev/null; do
        retries=$((retries - 1))
        sleep 1
    done
    return 0
}

# Brings the app up with the baseline settings and the overrides given as
# NAME=VALUE arguments. The overrides come last so they win: `env A=1 A=2` keeps
# the last assignment.
app_start() {
    if [ "$APP_MODE_RESOLVED" = "compose" ]; then
        # --force-recreate because `up -d` is a no-op when nothing about the service
        # changed. Two runs of a script that passes the same overrides then leave the
        # first run's process in place, still holding its cumulative metric state, and
        # every later export carries points from a run the caller is not looking at.
        # A recreate stops the old container with SIGTERM first, so the outgoing
        # process still flushes what it had.
        #
        # --no-deps keeps this to the app. Recreating the collector as well would throw
        # away the debug log the verification reads.
        env "${APP_BASELINE[@]}" "$@" docker compose up -d --force-recreate --no-deps app >/dev/null 2>&1
    else
        app_stop_host
        env "${APP_BASELINE[@]}" "$@" \
            OTEL_EXPORTER_OTLP_ENDPOINT="${OTEL_EXPORTER_OTLP_ENDPOINT:-http://localhost:4318}" \
            OTEL_SERVICE_NAME="${OTEL_SERVICE_NAME:-ai-learning-path-planner}" \
            node --import ./dist/telemetry.js dist/index.js >"$APP_LOG_FILE" 2>&1 &
        echo $! >"$APP_PID_FILE"
    fi
    app_wait_healthy
}

restart_app() {
    app_start "$@"
}

# Runs from an EXIT trap as well as at the end of a section. Returns non-zero when
# the app did not come back, and leaves it to the caller to say what that means:
# the normal path fails a check, the trap prints the command to run by hand.
restore_app() {
    if [ "$APP_BASELINE_SET" != "1" ]; then
        return 0
    fi
    app_start
}

# Reads one setting out of the running app, from the process rather than from what
# this script believes it started: the point of a check that reads this back after a
# restore is that it is independent of the restore reporting success. Compose is asked
# through the container; a host process is read out of its own environment with
# `ps eww`, which both macOS and Linux support.
#
# Returning the baseline array instead would have made the "the app came back on the
# settings it started with" check compare a value to itself, which is an assertion
# that cannot fail.
app_setting() {
    local name="$1"
    if [ "$APP_MODE_RESOLVED" = "compose" ]; then
        docker compose exec -T app printenv "$name" 2>/dev/null || echo ""
        return 0
    fi
    local pid=""
    [ -f "$APP_PID_FILE" ] && pid=$(cat "$APP_PID_FILE" 2>/dev/null)
    if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
        echo ""
        return 0
    fi
    ps eww -p "$pid" 2>/dev/null | tr ' ' '\n' | awk -F= -v n="$name" \
        '$1 == n { sub(/^[^=]*=/, ""); print; exit }'
}

# The value app_setting should report once restore_app has run. Read from the baseline
# rather than from the process, so a caller can compare the two.
app_baseline_setting() {
    local name="$1" entry
    for entry in "${APP_BASELINE[@]}"; do
        case "$entry" in
            "$name"=*) echo "${entry#*=}"; return 0 ;;
        esac
    done
    echo ""
}
