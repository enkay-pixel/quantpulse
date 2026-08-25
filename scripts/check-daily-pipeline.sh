#!/usr/bin/env bash
# Did last night's run actually produce anything, for both markets?
#
# check-jse-close.sh runs at 19:47 SAST and asks whether the JSE *ingest* landed. Nothing
# asked the same of the NYSE, or of anything downstream: the US process job finishes around
# 01:15 SAST, hours after that check, and a run that ingests prices but writes no predictions
# leaves the dashboard looking a day stale with no alert anywhere.
#
# The failure this is built for is a market silently stopping. A champion demoted or promoted
# on a day with no new features leaves nothing to score, which is correct — but so does a
# scoring step that crashed, and from the outside those look identical the next morning. This
# separates them by reporting which stage each market reached and which model version did the
# scoring.
#
# Notifies, never acts. Same rule as the other checks: re-running the pipeline from a script
# is how a partial day gets written twice, and the catch-up sensor already retries on its own.
set -uo pipefail

REPO="/Users/nathankindo/nathan_playground/projects/quantpulse"
cd "$REPO" || exit 0

stamp() { date '+%Y-%m-%d %H:%M:%S'; }
problems=()

# A market that has stopped stays stopped until someone looks, so the notification decays
# rather than repeating identically every weekday. The log keeps every run.
DEDUP_LIB="$(dirname "$0")/lib/dedup.sh"
# shellcheck source=scripts/lib/dedup.sh
[ -r "$DEDUP_LIB" ] && . "$DEDUP_LIB"
if ! command -v qp_alert_due >/dev/null 2>&1; then
    qp_alert_due() { return 0; }
    qp_alert_sweep() { :; }
fi

RUNNING=$(docker ps --filter "name=quantpulse-" --format '{{.Names}}' 2>/dev/null | wc -l | tr -d ' ')
if [ "${RUNNING:-0}" -lt 6 ]; then
    printf '%s stack is down (%s/6) — last night'"'"'s run unverified\n' "$(stamp)" "$RUNNING"
    if qp_alert_due daily-pipeline "stack down ($RUNNING/6)"; then
        osascript -e "display notification \"stack is down ($RUNNING/6) — last night's run unverified\" \
            with title \"QuantPulse: daily pipeline\"" 2>/dev/null || true
    fi
    exit 0
fi

# `docker compose exec` reads stdin even with -T, and this runs inside a `while read`
# loop fed by a heredoc. Without </dev/null the first query swallows the remaining
# markets and only the first one is ever checked — silently, which is the exact
# failure mode this script exists to catch.
psql_q() { docker compose exec -T postgres psql -U quantpulse -d market -tAc "$1" </dev/null 2>/dev/null; }

# The last session each exchange has actually *finished* and had its ingest run for, in its
# own calendar. Not last_trading_day() alone: run at 08:00 SAST that is 02:00 in New York, so
# it would name a session the NYSE has not opened yet, and every market would look stalled
# every morning.
#
# is_post_close is necessary but not sufficient. Between the close and the ingest — two hours
# for both markets — the session is finished while its data legitimately has not arrived, and
# expecting it there reports a stall against a schedule that has not had its turn. Same
# distinction check-jse-close.sh draws, and ingest_overdue is the same clock predicate it
# uses. It can only be true where is_post_close already is, so this narrows that window and
# leaves the 08:00 run, where both are false and the previous session is named, untouched.
EXPECTED=$(docker compose exec -T dagster-daemon python -c '
import datetime as dt
from quantpulse.data.calendar import EXCHANGES, is_post_close, is_trading_day, last_trading_day, market_today
from quantpulse.orchestration.catchup import ingest_overdue
for code in sorted(EXCHANGES):
    day = market_today(code)
    ready = is_trading_day(day, code) and is_post_close(exchange=code) and ingest_overdue(exchange=code)
    if not ready:
        day = last_trading_day(day - dt.timedelta(days=1), code)
    print(f"{code} {day}")
' 2>/dev/null | tr -d '\r')

if [ -z "$EXPECTED" ]; then
    printf '%s could not resolve the trading calendar — skipping\n' "$(stamp)"
    exit 0
fi

printf '%s daily pipeline:\n' "$(stamp)"
while read -r code expected; do
    [ -n "${code:-}" ] || continue
    # predictions carries no exchange column, so every stage scopes through universe. An
    # unscoped max() here would report whichever market ingested last for both of them.
    row=$(psql_q "
        SELECT coalesce((SELECT max(p.date)::text FROM prices p JOIN universe u
                         ON u.ticker=p.ticker AND u.exchange='$code'),'none')||'|'||
               coalesce((SELECT max(f.date)::text FROM features f JOIN universe u
                         ON u.ticker=f.ticker AND u.exchange='$code'),'none')||'|'||
               coalesce((SELECT max(pr.date)::text FROM predictions pr JOIN universe u
                         ON u.ticker=pr.ticker AND u.exchange='$code'),'none')||'|'||
               coalesce((SELECT max(pr.model_version) FROM predictions pr JOIN universe u
                         ON u.ticker=pr.ticker AND u.exchange='$code'
                         WHERE pr.date=(SELECT max(pr2.date) FROM predictions pr2 JOIN universe u2
                                        ON u2.ticker=pr2.ticker AND u2.exchange='$code')),'?');")
    IFS='|' read -r prices feats preds ver <<<"$row"
    printf '  %-5s expected %s | prices %s | features %s | predictions %s (v%s)\n' \
        "$code" "$expected" "$prices" "$feats" "$preds" "$ver"
    # Prices are what everything downstream depends on, so a stale price date explains the
    # rest and is reported once rather than as three separate findings.
    if [ "$prices" != "$expected" ]; then
        problems+=("$code has no prices for $expected (latest $prices)")
    elif [ "$preds" != "$expected" ]; then
        problems+=("$code ingested $expected but wrote no predictions for it")
    fi
done <<EOF
$EXPECTED
EOF

if [ "${#problems[@]}" -gt 0 ]; then
    for p in "${problems[@]}"; do printf '  STALLED %s\n' "$p"; done
    if qp_alert_due daily-pipeline "${problems[*]}"; then
        osascript -e "display notification \"${#problems[@]} market(s) did not complete last night\" \
            with title \"QuantPulse: daily pipeline\"" 2>/dev/null || true
    fi
    exit 1
fi
qp_alert_sweep daily-pipeline
exit 0
