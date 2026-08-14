#!/usr/bin/env bash
# Report the weekly retrain's outcome, per market.
#
# A retrain that promotes and a retrain that rejects both finish quietly, and a retrain that
# never ran looks the same as one that rejected everything. This says which happened, and on
# what evidence: the candidate's IC, the incumbent it had to beat, and the baseline it had
# to beat as well.
#
# Notifies, never acts. Whether a rejection streak means the gate is right or the model is
# stuck is a judgement, and the answer changes what you would do next.
set -uo pipefail

REPO="/Users/nathankindo/nathan_playground/projects/quantpulse"
cd "$REPO" || exit 0

stamp() { date '+%Y-%m-%d %H:%M:%S'; }

RUNNING=$(docker ps --filter "name=quantpulse-" --format '{{.Names}}' 2>/dev/null | wc -l | tr -d ' ')
if [ "${RUNNING:-0}" -lt 6 ]; then
    printf '%s stack is down (%s/6) — retrain outcome unknown\n' "$(stamp)" "$RUNNING"
    osascript -e "display notification \"stack is down — weekly retrain outcome unknown\" \
        with title \"QuantPulse: retrain check\"" 2>/dev/null || true
    exit 0
fi

psql_q() { docker compose exec -T postgres psql -U quantpulse -d market -tAc "$1" 2>/dev/null; }

# Today's training rows, newest per market. The baseline IC is stored beside the candidate's
# so a rejection can be read without re-running anything.
ROWS=$(psql_q "
    SELECT exchange || ' v' || model_version || ' ' || decision
           || ' | ic ' || coalesce(round((metrics->>'holdout_ic')::numeric, 4)::text, 'n/a')
           || ' vs baseline ' || coalesce(round((metrics->>'baseline_momentum_ic')::numeric, 4)::text, 'n/a')
           || ' | sharpe ' || coalesce(round((metrics->>'holdout_sharpe')::numeric, 2)::text, 'n/a')
           || ' | holdout ' || coalesce(metrics->>'holdout_days', '?') || 'd'
    FROM model_runs
    WHERE run_type = 'train' AND created_at::date = current_date
    ORDER BY exchange, id;")

if [ -z "$ROWS" ]; then
    printf '%s no retrain recorded today — the schedule may not have fired\n' "$(stamp)"
    osascript -e "display notification \"no retrain recorded today\" \
        with title \"QuantPulse: retrain check\"" 2>/dev/null || true
    exit 0
fi

printf '%s retrain outcome:\n' "$(stamp)"
printf '  %s\n' "$ROWS"

# A promotion changes what scores from now on, so it is the case worth interrupting for.
PROMOTED=$(printf '%s\n' "$ROWS" | grep -c "promoted")
if [ "${PROMOTED:-0}" -gt 0 ]; then
    osascript -e "display notification \"$PROMOTED market(s) promoted a new champion\" \
        with title \"QuantPulse: retrain promoted\"" 2>/dev/null || true
fi
exit 0
