#!/usr/bin/env bash
# Evening readiness check, run before the option-chain capture window opens.
#
# Everything else the pipeline does is recoverable: a missed ingest is backfilled by the
# catch-up sensor, a missed process run re-runs. Option chains are not — they are live-only,
# so an evening spent with the stack down or the Mac asleep is a permanent hole in the
# history. On 2026-07-29 the stack was down at 21:00 and the whole night would have been
# lost unnoticed; this is that near-miss turned into a notification.
#
# Notifies, never acts. Bringing the stack up automatically would override a deliberate
# `make down` before travel — the judgement of whether tonight matters is the operator's.
set -uo pipefail

RUNNING=$(docker ps --filter "name=quantpulse-" --format '{{.Names}}' 2>/dev/null | wc -l | tr -d ' ')
EXPECTED=6
problems=()

[ "$RUNNING" -lt "$EXPECTED" ] && problems+=("stack is down ($RUNNING/$EXPECTED containers)")
pmset -g ps 2>/dev/null | head -1 | grep -q "AC Power" || problems+=("on battery")

if [ ${#problems[@]} -eq 0 ]; then
    printf '%s ready: %s containers, on AC\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$RUNNING"
    exit 0
fi

message="$(
    IFS='; '
    echo "${problems[*]}"
)"
printf '%s NOT READY: %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$message"
osascript -e "display notification \"${message//\"/\'} — option chains are live-only\" \
    with title \"QuantPulse: not ready for tonight\"" 2>/dev/null || true
