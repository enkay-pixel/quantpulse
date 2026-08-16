#!/usr/bin/env bash
# Report the weekly retrain's outcome, per market.
#
# A retrain that promotes and a retrain that rejects both finish quietly, and a retrain that
# never ran looks the same as one that rejected everything. This says which happened, and on
# what evidence: the candidate's IC, the incumbent it had to beat, and the baseline it had
# to beat as well.
#
# Notifies, never acts. Whether a rejection streak means the gate is right or the model is
# stuck is a judgement, and the answer changes what you would do next — so the streak is
# reported with the evidence needed to tell those apart, not just its length.
set -uo pipefail

REPO="/Users/nathankindo/nathan_playground/projects/quantpulse"
cd "$REPO" || exit 0

# Retrains are weekly, so three consecutive rejections is three weeks of producing nothing.
# The age bound catches the other stall: a schedule that stopped firing leaves the champion
# ageing with no rejections at all to count.
STALL_RUNS="${RETRAIN_STALL_RUNS:-3}"
STALL_DAYS="${RETRAIN_STALL_DAYS:-28}"

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
    # Not an exit: a retrain that never ran is the case where the stall check below matters
    # most, since a champion ages just as fast whether it was challenged or forgotten.
    printf '%s no retrain recorded today — the schedule may not have fired\n' "$(stamp)"
    osascript -e "display notification \"no retrain recorded today\" \
        with title \"QuantPulse: retrain check\"" 2>/dev/null || true
else
    printf '%s retrain outcome:\n' "$(stamp)"
    printf '  %s\n' "$ROWS"
fi

# A promotion changes what scores from now on, so it is the case worth interrupting for.
PROMOTED=$(printf '%s\n' "$ROWS" | grep -c "promoted")
if [ "${PROMOTED:-0}" -gt 0 ]; then
    osascript -e "display notification \"$PROMOTED market(s) promoted a new champion\" \
        with title \"QuantPulse: retrain promoted\"" 2>/dev/null || true
fi

# --- promotion stall ---------------------------------------------------------------------
# One rejection is the gate working. A run of them is the pipeline producing nothing, and no
# single week's report can show that — each rejection reads as normal on its own.
#
# Streak length alone does not say what to do, because two opposite situations produce the
# same number. Measured 2026-08-16, both markets at three rejections since 07-25:
#
#   XNYS  champion ic 0.1000, best rejected 0.0852   nothing beat it — gate right, model stuck
#   XJSE  champion ic 0.0625, best rejected 0.0684   one beat it and was rejected anyway
#
# The second is the one worth reading: some criterion other than the incumbent's IC is
# binding, which since 1681ccf is momentum standing as a competitor. So the best rejected
# candidate is carried alongside the champion it failed to displace, and the two cases are
# named rather than collapsed into a count.
#
# Demotions are excluded: run_type='demotion' also records decision='rejected', and counting
# a rollback as a failed challenge would inflate the streak with the opposite kind of event.
STALL=$(psql_q "
    WITH promo AS (
        SELECT exchange, max(created_at) AS ts
        FROM model_runs WHERE run_type = 'train' AND decision = 'promoted'
        GROUP BY exchange),
    champ AS (
        SELECT DISTINCT ON (m.exchange) m.exchange, m.model_version, m.created_at,
               (m.metrics->>'holdout_ic')::numeric AS ic
        FROM model_runs m JOIN promo p ON p.exchange = m.exchange AND p.ts = m.created_at
        WHERE m.run_type = 'train' AND m.decision = 'promoted'),
    streak AS (
        SELECT m.exchange, count(*) AS n,
               max((m.metrics->>'holdout_ic')::numeric) AS best_ic
        FROM model_runs m LEFT JOIN promo p ON p.exchange = m.exchange
        WHERE m.run_type = 'train' AND m.decision = 'rejected'
          AND (p.ts IS NULL OR m.created_at > p.ts)
        GROUP BY m.exchange)
    SELECT s.exchange || '|' || s.n
           || '|' || coalesce((current_date - c.created_at::date)::text, '9999')
           || '|' || coalesce(to_char(c.created_at, 'YYYY-MM-DD'), 'never')
           || '|' || coalesce('v' || c.model_version, 'none')
           || '|' || coalesce(round(c.ic, 4)::text, 'n/a')
           || '|' || coalesce(round(s.best_ic, 4)::text, 'n/a')
    FROM streak s LEFT JOIN champ c ON c.exchange = s.exchange
    ORDER BY s.exchange;")

STALLED=0
while IFS='|' read -r ex n age since ver champ_ic best_ic; do
    [ -n "${ex:-}" ] || continue
    [ "${n:-0}" -ge "$STALL_RUNS" ] || [ "${age:-0}" -gt "$STALL_DAYS" ] || continue
    STALLED=$((STALLED + 1))
    if [ "$ver" = "none" ]; then
        # A market added but never promoted anything: there is no champion to have beaten,
        # and the age bound is what fires. XJSE would have read this way before 07-23.
        verdict="no champion has ever been promoted for this market"
    elif [ "$champ_ic" != "n/a" ] && [ "$best_ic" != "n/a" ] \
       && awk -v a="$best_ic" -v b="$champ_ic" 'BEGIN { exit !(a > b) }'; then
        verdict="a candidate beat the champion (ic $best_ic vs $champ_ic) and was rejected anyway — another criterion is binding"
    else
        verdict="nothing has beaten the champion (best $best_ic vs $champ_ic) — the gate is right and the model is stuck"
    fi
    printf '  STALL %s: %s rejection(s) since %s, champion %s is %sd old — %s\n' \
        "$ex" "$n" "$since" "$ver" "$age" "$verdict"
done <<EOF
$STALL
EOF

if [ "$STALLED" -gt 0 ]; then
    osascript -e "display notification \"$STALLED market(s) have promoted nothing in \
${STALL_RUNS}+ retrains\" with title \"QuantPulse: promotion stalled\"" 2>/dev/null || true
    exit 1
fi
exit 0
