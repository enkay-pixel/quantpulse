#!/usr/bin/env bash
# Everything a check-in asks, in one place: the stack, the scheduled jobs, GitHub, and then the
# data — freshness, recent coverage and gaps, champions, the shadow run, standing decisions and
# the dates ahead.
#
# Read-only. The data half is `quantpulse status`, run from the working tree against the stack's
# database, so it describes the code as checked out rather than whatever image is running.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${VENV_PYTHON:-$REPO/.venv/bin/python}"
LOGS="${QP_LOG_DIR:-$HOME/Library/Logs}"
cd "$REPO" || exit 1

printf 'QuantPulse status — %s (New York %s)\n' "$(date '+%a %Y-%m-%d %H:%M %Z')" \
    "$(TZ=America/New_York date '+%a %H:%M')"

running=$(docker ps --filter "name=quantpulse-" --format '{{.Names}}' 2>/dev/null | wc -l | tr -d ' ')
printf 'stack: %s/6 containers up\n' "$running"

# A job is flagged when its latest run says so in its own words. The jobs report by exception,
# so the words they use for a problem are the ones to look for — but only in the latest run: every
# line from the first one stamped with that run's minute. Reading the log's tail instead flags a
# problem an earlier run reported and a later one cleared.
PROBLEM_WORDS='PROBLEM|ATTENTION|STALL|NOT READY|could not|unreachable|FAILED|EXPIRED|REJECTED|is down|not running'
flagged=0
for log in "$LOGS"/quantpulse-*.log; do
    [ -f "$log" ] || continue
    job="$(basename "$log" .log)"
    job="${job#quantpulse-}"
    minute=$(grep -oE '^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}' "$log" | tail -1)
    [ -n "$minute" ] || continue
    run=$(awk -v t="$minute" 'index($0, t) == 1 { found = 1 } found' "$log")
    # A "PROBLEMS (n):" header says how many, the line under it says what — show that one.
    hit=$(printf '%s\n' "$run" | grep -E -A1 "$PROBLEM_WORDS" | grep -vE 'PROBLEMS \([0-9]+\):$' |
        grep -vE '^--$' | head -1)
    if [ -n "$hit" ]; then
        flagged=$((flagged + 1))
        printf '  %s: %s\n' "$job" "$(printf '%s' "$hit" | sed -E 's/^[0-9-]+ [0-9:]+ +//' | cut -c1-150)"
    fi
done
health=$(grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9:]+ (ok|PROBLEMS)' "$LOGS/quantpulse-launchd-health.log" 2>/dev/null | tail -1)
printf 'scheduled jobs: %s flagged; launchd audit: %s\n' "$flagged" "${health:-no audit yet}"

if prs=$(gh pr list --repo enkay-pixel/quantpulse --json number,title,autoMergeRequest \
        --jq '.[] | "  #\(.number) \(.title)\(if .autoMergeRequest then " (auto-merge on)" else "" end)"' 2>/dev/null); then
    alerts=$(gh api 'repos/enkay-pixel/quantpulse/dependabot/alerts?state=open' --jq length 2>/dev/null || echo "?")
    printf 'github: %s open PR(s), %s open Dependabot alert(s)\n' "$(printf '%s' "$prs" | grep -c '#')" "$alerts"
    [ -n "$prs" ] && printf '%s\n' "$prs"
else
    printf 'github: unreadable (is gh signed in?)\n'
fi

if [ "${running:-0}" -lt 1 ]; then
    printf 'data: stack is down — nothing to read\n'
    exit 0
fi
set -a
# shellcheck source=/dev/null
. ./.env
set +a
PYTHONPATH="$REPO/src" "$PYTHON" -m quantpulse.cli status
