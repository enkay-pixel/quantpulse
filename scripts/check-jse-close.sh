#!/usr/bin/env bash
# Post-close data check for the JSE, run after its 19:30 SAST ingest has had its turn.
#
# Distinct from check-readiness.sh, which asks whether the machine is *able* to capture
# tonight's option chains. This asks whether today's JSE data actually landed, and whether
# anything is quietly missing from it.
#
# Exists because the failures worth catching here are the silent ones. A session that never
# ingested is loud (the catch-up sensor says so, the dashboard goes stale), but a session
# that ingested *almost* completely is not: on 2026-08-11 STX40.JO alone was absent, which
# is 1/29th of coverage and trips no threshold, while the CAPM marts inner-join it and lost
# the whole day. That went unnoticed for two days and was found by comparing mart day counts
# by hand.
#
# Notifies, never acts — same rule as check-readiness.sh. Re-fetching from a script is how
# you write a misdated bar into the benchmark (see docs/data-dictionary.md); deciding to
# backfill is the operator's call, and the catch-up sensor already retries on its own.
set -uo pipefail

REPO="/Users/nathankindo/nathan_playground/projects/quantpulse"
cd "$REPO" || exit 0

stamp() { date '+%Y-%m-%d %H:%M:%S'; }
problems=()
notes=()

RUNNING=$(docker ps --filter "name=quantpulse-" --format '{{.Names}}' 2>/dev/null | wc -l | tr -d ' ')
if [ "${RUNNING:-0}" -lt 6 ]; then
    # Nothing below can be trusted without the database, so report and stop rather than
    # emitting a wall of connection errors that all mean this one thing.
    printf '%s stack is down (%s/6 containers) — no data check possible\n' "$(stamp)" "$RUNNING"
    osascript -e "display notification \"stack is down ($RUNNING/6) — today's JSE session unverified\" \
        with title \"QuantPulse: JSE post-close check\"" 2>/dev/null || true
    exit 0
fi

psql_q() { docker compose exec -T postgres psql -U quantpulse -d market -tAc "$1" 2>/dev/null; }

# The exchange's own date, never the container's UTC date.
STATE=$(docker compose exec -T dagster-daemon python -c \
    "from quantpulse.data.calendar import market_today, is_trading_day
from quantpulse.orchestration.catchup import ingest_overdue
d = market_today('XJSE')
print(f'{d}|{int(is_trading_day(d, \"XJSE\"))}|{int(ingest_overdue(exchange=\"XJSE\"))}')" \
    2>/dev/null | tr -d '\r')
IFS='|' read -r DAY TRADING OVERDUE <<<"$STATE"

if [ -z "$DAY" ]; then
    printf '%s could not resolve the JSE trading date — skipping\n' "$(stamp)"
    exit 0
fi
if [ "$TRADING" != "1" ]; then
    printf '%s %s is not a JSE session — nothing expected\n' "$(stamp)" "$DAY"
    exit 0
fi

# 1. Did today's session land, and how completely?
read -r COVERED UNIVERSE <<<"$(psql_q "
    SELECT coalesce(c.n, 0), u.n FROM
      (SELECT count(*) n FROM universe WHERE active AND exchange = 'XJSE') u
      LEFT JOIN (SELECT count(*) n FROM prices p JOIN universe u2 ON u2.ticker = p.ticker
                 AND u2.exchange = 'XJSE' WHERE p.date = '$DAY') c ON true;" | tr '|' ' ')"
if [ "${OVERDUE:-1}" != "1" ]; then
    # Run early (or by hand at midday): the schedule has not had its turn, so an absent
    # session is not yet a missed one. Same distinction catchup.ingest_overdue draws for
    # the sensor — without it this reports a failed ingest every time it runs before 19:30.
    notes+=("XJSE $DAY ingest not due yet")
elif [ "${COVERED:-0}" -eq 0 ]; then
    problems+=("no XJSE bars for $DAY — the 19:30 ingest did not land")
elif [ "${UNIVERSE:-0}" -gt 0 ] && [ "$((COVERED * 100 / UNIVERSE))" -lt 80 ]; then
    problems+=("XJSE $DAY only $COVERED/$UNIVERSE tickers — below the catch-up floor")
else
    notes+=("XJSE $DAY: $COVERED/$UNIVERSE tickers")
fi

# 2. Benchmark gaps — the quiet failure this script exists for. Scoped to the recent window
#    the catch-up sensor can still act on; older holes are the asset check's to report.
for pair in "XJSE:STX40.JO" "XNYS:SPY"; do
    ex="${pair%%:*}"
    bench="${pair##*:}"
    gaps=$(psql_q "
        SELECT string_agg(d::text, ', ' ORDER BY d) FROM (
          SELECT p.date d FROM prices p
          JOIN universe u ON u.ticker = p.ticker AND u.exchange = '$ex'
          GROUP BY p.date ORDER BY p.date DESC LIMIT 5
        ) s WHERE NOT EXISTS (
          SELECT 1 FROM prices b WHERE b.ticker = '$bench' AND b.date = s.d);")
    [ -n "$gaps" ] && problems+=("$ex benchmark $bench missing: $gaps")
done

# 3. Anything the pipeline itself reported today.
ALERTS=$(psql_q "SELECT count(*) FROM pipeline_alerts WHERE created_at::date = current_date;")
[ "${ALERTS:-0}" -gt 0 ] && problems+=("$ALERTS pipeline alert(s) today")

# `set -u` treats an empty array as unbound on expansion, so default it — otherwise the
# only path that reports nothing good (every check a problem) dies before printing.
summary="$(
    IFS='; '
    echo "${notes[*]-}"
)"
if [ ${#problems[@]} -eq 0 ]; then
    printf '%s ok: %s\n' "$(stamp)" "$summary"
    exit 0
fi

message="$(
    IFS='; '
    echo "${problems[*]}"
)"
printf '%s ATTENTION: %s (%s)\n' "$(stamp)" "$message" "$summary"
# A benchmark gap is usually a late bar that fixes itself, so the notification says what to
# do rather than implying breakage: the sensor retries on tomorrow's budget.
osascript -e "display notification \"${message//\"/\'}\" \
    with title \"QuantPulse: JSE post-close check\"" 2>/dev/null || true
exit 0
