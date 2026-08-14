#!/usr/bin/env bash
# Evening readiness check, run before the option-chain capture window opens.
#
# Everything else the pipeline does is recoverable: a missed ingest is backfilled by the
# catch-up sensor, a missed process run re-runs. Option chains are not — they are live-only,
# so an evening spent with the stack down or the Mac asleep is a permanent hole in the
# history. A stack left down through the evening loses the whole night unnoticed; this
# turns that into a notification.
#
# Notifies, never acts. Bringing the stack up automatically would override a deliberate
# `make down` before travel — the judgement of whether tonight matters is the operator's.
set -uo pipefail

RUNNING=$(docker ps --filter "name=quantpulse-" --format '{{.Names}}' 2>/dev/null | wc -l | tr -d ' ')
EXPECTED=6
problems=()
caveats=()

[ "$RUNNING" -lt "$EXPECTED" ] && problems+=("stack is down ($RUNNING/$EXPECTED containers)")
pmset -g ps 2>/dev/null | head -1 | grep -q "AC Power" || problems+=("on battery")

# A stack that is up is worth nothing if the Mac sleeps through the window, and only
# SleepDisabled=1 actually prevents that. The assertions that keep it awake day to day —
# "prevent sleep while display is on", Handoff, audio — all drop the moment the lid
# closes, and the idle timer on battery here is one minute.
#
# Worth checking rather than assuming: `pmset -a disablesleep 1` needs sudo and fails
# quietly without it, so belief and state can diverge with nothing reporting the difference.
sleep_disabled=$(pmset -g 2>/dev/null | awk '/SleepDisabled/ {print $2}')
if [ "${sleep_disabled:-0}" != "1" ]; then
    lid=$(ioreg -r -k AppleClamshellState 2>/dev/null |
        awk -F'= ' '/AppleClamshellState/ {gsub(/ /, "", $2); print $2; exit}')
    if [ "$lid" = "Yes" ]; then
        problems+=("lid is closed and sleep is enabled — the Mac will sleep through the window")
    else
        # Open lid is holding it awake, so this is not a failure yet. But a bare "ready"
        # invites the one action that breaks it, so state the contingency. Self-
        # extinguishing: it stops once disablesleep is actually set.
        caveats+=("sleep is enabled — keep the lid open, or run: sudo pmset -a disablesleep 1 (on AC)")
    fi
fi

if [ ${#problems[@]} -eq 0 ]; then
    line="ready: $RUNNING containers, on AC"
    if [ ${#caveats[@]} -gt 0 ]; then
        caveat="$(
            IFS='; '
            echo "${caveats[*]}"
        )"
        line="$line — CAVEAT: $caveat"
        # Notified, unlike a plain ready: the log is read after the fact, and the whole
        # point is to prompt before the window rather than explain afterwards.
        osascript -e "display notification \"${caveat//\"/\'}\" \
            with title \"QuantPulse: ready, but the Mac can still sleep\"" 2>/dev/null || true
    fi
    printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$line"
    exit 0
fi

message="$(
    IFS='; '
    echo "${problems[*]}"
)"
printf '%s NOT READY: %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$message"
osascript -e "display notification \"${message//\"/\'} — option chains are live-only\" \
    with title \"QuantPulse: not ready for tonight\"" 2>/dev/null || true
