#!/usr/bin/env bash
# Post-close data check for the JSE, run after its 19:30 SAST ingest has had its turn.
#
# Distinct from check-readiness.sh, which asks whether the machine is *able* to capture
# tonight's option chains. This asks whether today's JSE data actually landed, and whether
# anything is quietly missing from it.
#
# Exists because the failures worth catching here are the silent ones. A session that never
# ingested is loud (the catch-up sensor says so, the dashboard goes stale), but a session
# that ingested *almost* completely is not: a single absent benchmark ticker is a fraction
# of coverage and trips no threshold, while the CAPM marts inner-join it and lose the whole
# day. That kind of gap goes unnoticed until someone compares mart day counts by hand.
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

# A benchmark gap and the pipeline-alert count are both standing conditions — the same hole
# reports every evening until it is filled, and the alert count is usually one failure
# repeated. The log still records every finding on every run; only the notification decays.
DEDUP_LIB="$(dirname "$0")/lib/dedup.sh"
# shellcheck source=scripts/lib/dedup.sh
[ -r "$DEDUP_LIB" ] && . "$DEDUP_LIB"
if ! command -v qp_alert_due >/dev/null 2>&1; then
    qp_alert_due() { return 0; }
    qp_alert_sweep() { :; }
fi

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
# The catch-up floor comes from the sensor's own constant, so the line this reports on is
# the line the sensor acts on.
STATE=$(docker compose exec -T dagster-daemon python -c \
    "from quantpulse.data.calendar import market_today, is_trading_day
from quantpulse.orchestration.catchup import MIN_COVERAGE, ingest_overdue
d = market_today('XJSE')
print(f'{d}|{int(is_trading_day(d, \"XJSE\"))}|{int(ingest_overdue(exchange=\"XJSE\"))}|{round(MIN_COVERAGE * 100)}')" \
    2>/dev/null | tr -d '\r')
IFS='|' read -r DAY TRADING OVERDUE FLOOR <<<"$STATE"
FLOOR="${FLOOR:-80}"

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
else
    # A partial session is reported below, with the tickers it is missing.
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

    # 2b. Every other ticker the same way. The catch-up sensor judges a session done once the
    #     floor share of the universe has arrived, and the scheduled ingest fetches only its own
    #     day, so a session that lands just above the floor is never retried by anything. Its
    #     missing tickers also skew the features around it, which shift by row, not by session.
    #     Only tickers already trading before the day count, so a new listing is not a gap; the
    #     benchmark is left to the check above.
    while IFS='|' read -r day covered universe missing tickers; do
        [ -n "${day:-}" ] || continue
        if [ $((covered * 100)) -lt $((FLOOR * universe)) ]; then
            retry="below the catch-up floor, so the sensor retries it within its attempt limit"
        else
            retry="above the catch-up floor, so nothing will retry it"
        fi
        problems+=("$ex $day missing $missing of $universe ($tickers) — $retry")
    done <<EOF
$(psql_q "
    WITH recent AS (
        SELECT p.date AS d, count(*) AS covered FROM prices p
        JOIN universe u ON u.ticker = p.ticker AND u.exchange = '$ex'
        GROUP BY p.date ORDER BY p.date DESC LIMIT 5)
    SELECT r.d || '|' || r.covered || '|'
           || (SELECT count(*) FROM universe WHERE active AND exchange = '$ex') || '|'
           || count(*) || '|' || string_agg(u.ticker, ', ' ORDER BY u.ticker)
    FROM recent r JOIN universe u ON u.exchange = '$ex' AND u.active AND u.ticker <> '$bench'
    WHERE NOT EXISTS (SELECT 1 FROM prices p WHERE p.ticker = u.ticker AND p.date = r.d)
      AND EXISTS (SELECT 1 FROM prices p WHERE p.ticker = u.ticker AND p.date < r.d)
    GROUP BY r.d, r.covered ORDER BY r.d;")
EOF
done

# 3. Anything the pipeline itself reported today.
ALERTS=$(psql_q "SELECT count(*) FROM pipeline_alerts WHERE created_at::date = current_date;")
[ "${ALERTS:-0}" -gt 0 ] && problems+=("$ALERTS pipeline alert(s) today")

# Joins with "; ". An IFS join uses only the separator's first character, which ran the items
# together. `set -u` treats an empty array as unbound on expansion, so callers default it —
# otherwise the only path that reports nothing good (every check a problem) dies before printing.
join() {
    local out
    out="$(printf '%s; ' "$@")"
    printf '%s' "${out%; }"
}
summary="$(join "${notes[@]-}")"
# Raise every current problem before sweeping, so conditions still true are not read as
# resolved. The early exits above never reach here by design: a stack that is down or a
# non-session day means the checks did not run, and reporting "cleared" for a condition
# nobody looked at would be a lie.
due=()
for p in "${problems[@]-}"; do
    [ -n "$p" ] || continue
    if qp_alert_due jse "$p"; then
        if [ "${QP_ALERT_NEW:-1}" = "1" ]; then
            due+=("$p")
        else
            due+=("$p [standing ${QP_ALERT_AGE_D}d]")
        fi
    fi
done
resolved="$(qp_alert_sweep jse)"

if [ ${#problems[@]} -eq 0 ]; then
    printf '%s ok: %s\n' "$(stamp)" "$summary"
    if [ -n "$resolved" ]; then
        printf '%s resolved: %s\n' "$(stamp)" "$resolved"
        osascript -e "display notification \"${resolved//\"/\'}\" \
            with title \"QuantPulse: JSE check cleared\"" 2>/dev/null || true
    fi
    exit 0
fi

message="$(join "${problems[@]}")"
printf '%s ATTENTION: %s%s\n' "$(stamp)" "$message" "${summary:+ ($summary)}"
[ -n "$resolved" ] && printf '%s resolved: %s\n' "$(stamp)" "$resolved"

# Only what is new or due goes to the banner. A known gap restated every evening is what
# trains you to dismiss this notification unread.
if [ ${#due[@]} -gt 0 ]; then
    banner="$(join "${due[@]}")"
    # A benchmark gap is usually a late bar that fixes itself, so the notification says what
    # to do rather than implying breakage: the sensor retries on tomorrow's budget.
    osascript -e "display notification \"${banner//\"/\'}\" \
        with title \"QuantPulse: JSE post-close check\"" 2>/dev/null || true
fi
exit 0
