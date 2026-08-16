#!/usr/bin/env bash
# Turn a standing condition into a decaying reminder instead of a metronome.
#
# A check on a short interval restates an unchanged condition every run. The cost is not
# noise for its own sake: when every banner says the same thing, the one that says something
# new looks like all the others.
#
# Not silence after the first alert. A condition still true after two weeks still matters,
# it just does not matter every two hours — so the interval doubles and then caps, keeping a
# standing problem on a weekly heartbeat. Suppression that never expires is how a real
# problem gets forgotten, which is worse than the noise.
#
# Resolution is reported too: without it, "still true" and "fixed" look identical.
#
# Usage:
#   . scripts/lib/dedup.sh
#   if qp_alert_due power "sleep disabled on battery ($charge)"; then notify; fi
#   qp_alert_sweep power     # one line per condition that has now cleared

QP_ALERT_DIR="${QP_ALERT_DIR:-$HOME/.quantpulse/alerts}"
# Cap the backoff so a standing condition still speaks weekly.
QP_ALERT_CAP_D="${QP_ALERT_CAP_D:-7}"
QP_ALERT_RUN_TS="$(date +%s)"
# Keys raised during this run, newline separated. Inferring this from file mtime against the
# run stamp works only while both are real wall-clock time, which makes the rule impossible
# to exercise with a simulated clock — and therefore impossible to test.
QP_ALERT_RAISED=""

# Strip the volatile parts so a condition keeps one identity across runs. A battery
# percentage or a gap date otherwise mints a new condition every run and nothing dedupes.
#
# Digits glued to letters are KEPT: stripping every number collapses tickers that differ only
# in digits into one key. BSD sed has no \b, hence the explicit non-alphanumeric prefix.
qp_alert_key() {
    printf '%s' "$1" \
        | sed -E 's/[0-9]{4}-[0-9]{2}-[0-9]{2}/D/g; s/(^|[^A-Za-z0-9])[0-9]+(\.[0-9]+)?/\1N/g' \
        | tr -cs 'A-Za-z0-9' '-' \
        | tr '[:upper:]' '[:lower:]' \
        | sed -E 's/^-+//; s/-+$//' \
        | cut -c1-80
}

# qp_alert_due <namespace> <text>
# Records that the condition is firing, and returns 0 only when this occurrence is worth a
# notification. Sets QP_ALERT_NEW / QP_ALERT_AGE_D / QP_ALERT_COUNT for the caller's message.
qp_alert_due() {
    local ns="$1" text="$2" key f first last n occ iv i now="$QP_ALERT_RUN_TS"
    key="$(qp_alert_key "$text")"
    f="$QP_ALERT_DIR/$ns/$key"
    QP_ALERT_RAISED="$QP_ALERT_RAISED
$ns/$key"
    mkdir -p "$QP_ALERT_DIR/$ns" 2>/dev/null || return 0   # unwritable state: never suppress

    first=""; last=""; n=0; occ=0
    [ -f "$f" ] && read -r first last n occ <"$f"
    occ=$((occ + 1))

    if [ -z "$first" ]; then
        export QP_ALERT_NEW=1 QP_ALERT_AGE_D=0 QP_ALERT_COUNT="$occ"
        printf '%s %s %s %s\n' "$now" "$now" 1 "$occ" >"$f"
        return 0
    fi

    # Exported: this is the output interface the caller reads, not incidental locals.
    export QP_ALERT_NEW=0
    export QP_ALERT_AGE_D=$(( (now - first) / 86400 ))
    export QP_ALERT_COUNT="$occ"

    # nth notification waits 2^(n-1) days, capped.
    iv=1; i=1
    while [ "$i" -lt "${n:-1}" ] && [ "$iv" -lt "$QP_ALERT_CAP_D" ]; do
        iv=$((iv * 2)); i=$((i + 1))
    done
    [ "$iv" -gt "$QP_ALERT_CAP_D" ] && iv="$QP_ALERT_CAP_D"

    if [ $(( now - last )) -ge $(( iv * 86400 )) ]; then
        printf '%s %s %s %s\n' "$first" "$now" "$((n + 1))" "$occ" >"$f"
        return 0
    fi
    printf '%s %s %s %s\n' "$first" "$last" "$n" "$occ" >"$f"
    return 1
}

# qp_alert_sweep <namespace>
# Any key not raised this run has cleared. Prints one line each and forgets it, so the next
# occurrence is genuinely new rather than resuming a stale backoff.
qp_alert_sweep() {
    local ns="$1" d f key first last n occ
    d="$QP_ALERT_DIR/$ns"
    [ -d "$d" ] || return 0
    # `find` rather than "$d"/*: an empty directory makes the glob expand to a literal path
    # under bash and abort under zsh, and this library is sourced by both.
    while IFS= read -r f; do
        [ -n "$f" ] && [ -f "$f" ] || continue
        key="$(basename "$f")"
        printf '%s\n' "$QP_ALERT_RAISED" | grep -qxF "$ns/$key" && continue
        first=""; last=""; n=0; occ=0
        read -r first last n occ <"$f"
        printf 'cleared after %sd and %s occurrence(s): %s\n' \
            "$(( (QP_ALERT_RUN_TS - ${first:-QP_ALERT_RUN_TS}) / 86400 ))" \
            "${occ:-?}" "$key"
        rm -f "$f"
    done <<EOF
$(find "$d" -maxdepth 1 -type f 2>/dev/null)
EOF
}
