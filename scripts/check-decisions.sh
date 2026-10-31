#!/usr/bin/env bash
# Notify when a standing decision's reopen condition fires.
#
# The roadmap ends each standing decision with what would reopen it: so many live sessions, a
# Sharpe turning negative, a promotion, a saved verdict. Written only as prose, those are kept by
# whoever happens to reread the roadmap at the right time. configs/decisions.yaml holds them as
# data, and this evaluates them each morning after the night's processing.
#
# A fired condition notifies, then keeps reminding — weekly, through the dedup library — until the
# decision is revisited and its entry updated. That persistence is the point: a reopened decision
# that nobody looked at is the failure this exists for. Notifies, never acts.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${VENV_PYTHON:-$REPO/.venv/bin/python}"
cd "$REPO" || exit 0

DEDUP_LIB="$(dirname "$0")/lib/dedup.sh"
# shellcheck source=scripts/lib/dedup.sh
[ -r "$DEDUP_LIB" ] && . "$DEDUP_LIB"
if ! command -v qp_alert_due >/dev/null 2>&1; then
    qp_alert_due() { return 0; }
    qp_alert_sweep() { :; }
fi

stamp() { date '+%Y-%m-%d %H:%M:%S'; }
notify() {
    osascript -e "display notification \"${2//\"/\'}\" with title \"${1//\"/\'}\"" \
        2>/dev/null || true
}

RUNNING=$(docker ps --filter "name=quantpulse-" --format '{{.Names}}' 2>/dev/null | wc -l | tr -d ' ')
if [ "${RUNNING:-0}" -lt 6 ]; then
    # The stack check reports a down stack; a skipped morning here only delays a reminder.
    printf '%s stack is down (%s/6) — decisions not evaluated\n' "$(stamp)" "$RUNNING"
    exit 0
fi

out=$(
    set -a
    # shellcheck source=/dev/null
    . ./.env
    set +a
    PYTHONPATH="$REPO/src" "$PYTHON" -m quantpulse.cli decisions 2>&1
)
rc=$?
printf '%s decisions:\n' "$(stamp)"
printf '%s\n' "$out" | sed -E 's/^[0-9-]+ [0-9:,]+ INFO /  /'

problems=()
# Judged on content as well as the exit status: a run that exits 0 without its summary line has
# evaluated nothing, and silence from it would read as every decision still standing.
if [ "$rc" -ne 0 ] || ! printf '%s\n' "$out" | grep -q 'decision(s),'; then
    problems+=("the decisions check failed (exit $rc) — nothing was evaluated")
fi
while IFS= read -r line; do
    [ -n "$line" ] && problems+=("revisit: $line")
done <<EOF
$(printf '%s\n' "$out" | sed -nE 's/^.* INFO FIRED +//p')
EOF

due=()
for p in "${problems[@]-}"; do
    [ -n "$p" ] || continue
    if qp_alert_due decisions "$p"; then
        if [ "${QP_ALERT_NEW:-1}" = "1" ]; then
            due+=("$p")
        else
            due+=("$p [standing ${QP_ALERT_AGE_D}d]")
        fi
    fi
done
resolved="$(qp_alert_sweep decisions)"
[ -n "$resolved" ] && printf '%s\n' "$resolved" | sed "s/^/$(stamp) cleared: /"

if [ ${#due[@]} -gt 0 ]; then
    banner="$(printf '%s; ' "${due[@]}")"
    notify "QuantPulse: decisions" "${banner%; }"
fi
[ ${#problems[@]} -eq 0 ] || exit 1
exit 0
