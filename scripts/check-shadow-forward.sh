#!/usr/bin/env bash
# Score the shadow run forward each week, and say when its verdict can be read.
#
# The rule in docs/findings/shadow-run.md reads once, after the last forward window has
# matured — weeks after the last shadow week, on a date set by two exchange calendars rather
# than by anything a person would remember to check. This runs the scorer weekly so the day it
# becomes readable is not missed, and so a lost week is found while the window is still open:
# the rule makes a lost week an engineering problem, and one found only at the end can no
# longer be fixed for the weeks after it.
#
# Until the rule can be read the scorer withholds every score, so this log holds health and
# progress only. It notifies when something needs a person — the verdict became readable, a
# week was lost, or the scorer failed — and is otherwise silent, because not-yet-readable is
# the normal state for most of the window.
#
# The first readable run is the reading. Its output is saved with the other durable evidence
# and that market is not scored again, so the verdict cannot move with a later data revision
# or with when someone happens to look.
#
# The fits run in a throwaway container built from the daemon's service definition — its
# image, env and memory cap — and never inside the live daemon, which hosts the scheduler.
set -uo pipefail

REPO="/Users/nathankindo/nathan_playground/projects/quantpulse"
cd "$REPO" || exit 0

# Outside the repo, which is public, and outside any scratch directory, which gets wiped.
OUT="${SHADOW_FORWARD_DIR:-$HOME/quantpulse-experiments/shadow-run}"

DEDUP_LIB="${DEDUP_LIB:-$REPO/scripts/lib/dedup.sh}"
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
    # Not a notification: the readiness check already reports a down stack, and a skipped week
    # loses nothing here, because every run scores every week again from the start.
    printf '%s stack is down (%s/6) — shadow run not scored this week\n' "$(stamp)" "$RUNNING"
    exit 0
fi

# The markets come from the code rather than a list here, so adding one cannot leave it unscored.
MARKETS=$(docker compose exec -T dagster-daemon python -c \
    "from quantpulse.data.calendar import EXCHANGES; print(' '.join(sorted(EXCHANGES)))" \
    2>/dev/null | tr -d '\r')

score() {
    docker compose run --rm --no-deps -T --entrypoint python dagster-daemon \
        -m quantpulse.cli shadow-forward --exchange "$1" 2>&1 | grep -v '^ *Container '
    return "${PIPESTATUS[0]}"
}

mkdir -p "$OUT"
problems=()
readable=()
pending=0

for ex in $MARKETS; do
    verdict_file="$OUT/$ex.verdict.txt"
    if [ -f "$verdict_file" ]; then
        printf '%s %s: verdict read %s — not scored again\n' \
            "$(stamp)" "$ex" "$(sed -n 's/.*, read \([0-9-]* [0-9:]*\) by .*/\1/p' "$verdict_file")"
        continue
    fi
    pending=$((pending + 1))

    out=$(score "$ex")
    rc=$?
    printf '%s %s:\n' "$(stamp)" "$ex"
    printf '%s\n' "$out" | sed 's/^/  /'

    # Judged on content, not the exit status alone: a run that exits 0 without stating a verdict
    # has not scored anything.
    line=$(printf '%s\n' "$out" | grep " INFO $ex shadow run: " | tail -1)
    state=$(printf '%s\n' "$line" | sed -n "s/.* shadow run: \([a-z_]*\) — .*/\1/p")
    action=$(printf '%s\n' "$line" | sed -n "s/.* shadow run: [a-z_]* — \(.*\)/\1/p")
    if [ "$rc" -ne 0 ]; then
        problems+=("$ex scorer failed (exit $rc) — no result this week")
        continue
    fi
    if [ -z "$state" ]; then
        problems+=("$ex scorer finished without stating a verdict — no result this week")
        continue
    fi

    # Any week neither scored nor maturing has lost its evidence, whatever the scorer calls it.
    lost=$(printf '%s\n' "$out" | awk '$3 == "INFO" && $4 ~ /^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]$/ &&
        $6 != "scored" && $6 != "maturing" { printf "%s%s %s", sep, $4, $6; sep = ", " }')

    case "$state" in
        harm_shown | no_harm_shown)
            {
                printf 'Shadow run verdict for %s, read %s by scripts/check-shadow-forward.sh\n' \
                    "$ex" "$(stamp)"
                printf 'repo %s, image %s\n\n' \
                    "$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo '?')" \
                    "$(docker image inspect quantpulse-dagster:latest --format '{{.Id}}' 2>/dev/null \
                        | cut -c8-19)"
                printf '%s\n' "$out"
            } >"$verdict_file.tmp" && mv "$verdict_file.tmp" "$verdict_file"
            readable+=("$ex: $state — $action")
            ;;
        not_clean)
            problems+=("$ex shadow run not clean ($lost) — $action")
            ;;
        not_yet_readable)
            [ -n "$lost" ] && problems+=("$ex lost week(s): $lost — two make the run not clean")
            ;;
        *)
            problems+=("$ex scorer stated an unknown verdict '$state'")
            ;;
    esac
done

if [ -z "$MARKETS" ]; then
    problems+=("could not list the markets — nothing scored")
elif [ "$pending" -eq 0 ]; then
    printf '%s all verdicts have been read — nothing left to score, and this job can be unloaded\n' \
        "$(stamp)"
fi

for r in "${readable[@]-}"; do
    [ -n "$r" ] || continue
    printf '%s VERDICT READABLE %s (saved to %s)\n' "$(stamp)" "$r" "$OUT"
    notify "QuantPulse: shadow run verdict" "$r"
done

due=()
for p in "${problems[@]-}"; do
    [ -n "$p" ] || continue
    printf '%s PROBLEM %s\n' "$(stamp)" "$p"
    if qp_alert_due shadow-forward "$p"; then
        if [ "${QP_ALERT_NEW:-1}" = "1" ]; then
            due+=("$p")
        else
            due+=("$p [standing ${QP_ALERT_AGE_D}d]")
        fi
    fi
done
resolved="$(qp_alert_sweep shadow-forward)"
[ -n "$resolved" ] && printf '%s\n' "$resolved" | sed "s/^/$(stamp) /"

if [ ${#due[@]} -gt 0 ]; then
    notify "QuantPulse: shadow run" "$(printf '%s; ' "${due[@]}" | sed 's/; $//')"
fi
[ ${#problems[@]} -eq 0 ] || exit 1
exit 0
