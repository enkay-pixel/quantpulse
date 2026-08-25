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
# ageing with no rejections to count.
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
    # Not an exit: a champion ages just as fast whether it was challenged or forgotten, so
    # this is exactly when the stall check below matters.
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
# same number:
#
#   loses to the momentum baseline  not beating a trivial competitor
#   beat the champion anyway        some other criterion is binding
#   beat neither                    the gate is right and the model is stuck
#
# Judged on the LATEST rejection, because the verdict describes where things stand now.
# Quoting the best of the streak instead let a near-miss from three weeks and four rejections
# ago stand in for today; it is still carried, dated, and only when it beats the current one.
#
# Demotions are excluded: run_type='demotion' also records decision='rejected', and counting
# a rollback as a failed challenge would inflate the streak with the opposite kind of event.
STALL=$(psql_q "
    WITH promoted AS (
        -- A promotion that was later withdrawn is not a champion. Deriving the champion from
        -- promotions alone reported a demoted version as the incumbent: XNYS v2 was promoted
        -- and demoted the same day, and this said \"champion v2\" for four weeks while the
        -- alias pointed at v1. Drop any promotion whose version was demoted afterwards.
        SELECT m.exchange, m.model_version, m.created_at, m.metrics
        FROM model_runs m
        WHERE m.run_type = 'train' AND m.decision = 'promoted'
          AND NOT EXISTS (
              SELECT 1 FROM model_runs d
              WHERE d.run_type = 'demotion' AND d.exchange = m.exchange
                AND d.model_version = m.model_version AND d.created_at > m.created_at)),
    promo AS (
        SELECT exchange, max(created_at) AS ts FROM promoted GROUP BY exchange),
    champ AS (
        SELECT DISTINCT ON (m.exchange) m.exchange, m.model_version, m.created_at,
               (m.metrics->>'holdout_ic')::numeric AS ic
        FROM promoted m JOIN promo p ON p.exchange = m.exchange AND p.ts = m.created_at),
    rej AS (
        SELECT m.exchange, m.created_at,
               (m.metrics->>'holdout_ic')::numeric AS ic,
               (m.metrics->>'baseline_momentum_ic')::numeric AS mom
        FROM model_runs m LEFT JOIN promo p ON p.exchange = m.exchange
        WHERE m.run_type = 'train' AND m.decision = 'rejected'
          AND (p.ts IS NULL OR m.created_at > p.ts)),
    streak AS (SELECT exchange, count(*) AS n FROM rej GROUP BY exchange),
    -- The verdict describes the CURRENT position, so it reads the newest rejection. The best
    -- of the streak is carried separately as dated context: quoting the maximum alone let a
    -- near-miss from three weeks and four rejections ago stand in for today.
    latest AS (SELECT DISTINCT ON (exchange) exchange, ic, mom, created_at
               FROM rej ORDER BY exchange, created_at DESC),
    best AS (SELECT DISTINCT ON (exchange) exchange, ic, created_at
             FROM rej ORDER BY exchange, ic DESC)
    SELECT s.exchange || '|' || s.n
           || '|' || coalesce((current_date - c.created_at::date)::text, '9999')
           || '|' || coalesce(to_char(c.created_at, 'YYYY-MM-DD'), 'never')
           || '|' || coalesce('v' || c.model_version, 'none')
           || '|' || coalesce(round(c.ic, 4)::text, 'n/a')
           || '|' || coalesce(round(l.ic, 4)::text, 'n/a')
           || '|' || coalesce(round(l.mom, 4)::text, 'n/a')
           || '|' || coalesce(round(b.ic, 4)::text, 'n/a')
           || '|' || coalesce(to_char(b.created_at, 'MM-DD'), '-')
    FROM streak s
    LEFT JOIN champ c ON c.exchange = s.exchange
    LEFT JOIN latest l ON l.exchange = s.exchange
    LEFT JOIN best b ON b.exchange = s.exchange
    ORDER BY s.exchange;")

STALLED=0
gt() { awk -v a="$1" -v b="$2" 'BEGIN { exit !(a > b) }'; }

while IFS='|' read -r ex n age since ver champ_ic last_ic last_mom best_ic best_on; do
    [ -n "${ex:-}" ] || continue
    [ "${n:-0}" -ge "$STALL_RUNS" ] || [ "${age:-0}" -gt "$STALL_DAYS" ] || continue
    STALLED=$((STALLED + 1))
    if [ "$ver" = "none" ]; then
        # A market added but never promoted anything: no champion exists to have been
        # beaten, and the age bound is what fires.
        verdict="no champion has ever been promoted for this market"
    elif [ "$last_mom" != "n/a" ] && [ "$last_ic" != "n/a" ] && gt "$last_mom" "$last_ic"; then
        # Momentum is a standing competitor in the gate, and where it is recorded it has been
        # the binding constraint — roughly double every candidate. Checked before the
        # incumbent because losing to a trivial baseline says something the champion
        # comparison does not, and the value sits in the same row.
        verdict="the latest candidate loses to the momentum baseline (ic $last_ic vs $last_mom) — it is not beating a trivial competitor"
    elif [ "$champ_ic" != "n/a" ] && [ "$last_ic" != "n/a" ] && gt "$last_ic" "$champ_ic"; then
        verdict="the latest candidate beat the champion (ic $last_ic vs $champ_ic) and was rejected anyway — another criterion is binding"
    else
        verdict="the latest candidate has not beaten the champion (ic $last_ic vs $champ_ic) — the gate is right and the model is stuck"
    fi
    # Only when the streak once did better than it is doing now, so a live near-miss is not
    # restated as history.
    if [ "$best_ic" != "n/a" ] && [ "$last_ic" != "n/a" ] && gt "$best_ic" "$last_ic"; then
        verdict="$verdict; best in this streak was $best_ic on $best_on"
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
