#!/usr/bin/env bash
# Turn a standing condition into a decaying reminder instead of a metronome.
#
# Measured 2026-08-16: check-power had emitted 47 identical notifications over 17 days for
# one unchanged setting, and pipeline_alerts held 50 rows over 10 days that were 1 job and
# 1 distinct error. Neither is 47 or 50 problems. Each is one problem, restated on a timer.
#
# The failure that causes is not noise for its own sake — it is that a notification stops
# carrying information. When every banner says the same thing, the one that says something
# new looks identical to the forty before it.
#
# Deliberately NOT silence after the first alert. A condition that is still true after two
# weeks still matters; it just does not matter every two hours. So the interval doubles —
# immediately, +1d, +2d, +4d — and then caps, which keeps a standing problem on a weekly
# heartbeat rather than letting it disappear. Suppression that never expires is how a real
# problem gets forgotten, which would be a worse bug than the one this fixes.
#
# Resolution is reported too, and that is new: nothing here has ever told you a condition
# stopped. `qp_alert_sweep` treats any key the caller did not raise this run as cleared.
#
# Usage:
#   . scripts/lib/dedup.sh
#   if qp_alert_due power "sleep disabled on battery ($charge)"; then notify; fi
#   qp_alert_sweep power     # prints one line per condition that has now cleared

QP_ALERT_DIR="${QP_ALERT_DIR:-$HOME/.quantpulse/alerts}"
# Cap the backoff so a standing condition still speaks weekly.
QP_ALERT_CAP_D="${QP_ALERT_CAP_D:-7}"
QP_ALERT_RUN_TS="$(date +%s)"

# Strip the volatile parts so the same condition keeps one identity across runs. Without
# this the battery percentage and the gap date make every occurrence a brand-new condition
# and nothing ever dedupes: "STX40.JO missing: 2026-08-12" and "...: 2026-08-13" are one
# standing gap, not two, and "on battery (88%)" is the same warning as "(97%)".
#
# Digits glued to letters are KEPT, so STX40.JO and STX50.JO stay distinct conditions —
# stripping every number collapsed them to the same key. BSD sed has no \b, hence the
# explicit non-alphanumeric prefix rather than a word boundary.
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
    mkdir -p "$QP_ALERT_DIR/$ns" 2>/dev/null || return 0   # unwritable state: never suppress

    first=""; last=""; n=0; occ=0
    [ -f "$f" ] && read -r first last n occ <"$f"
    occ=$((occ + 1))

    if [ -z "$first" ]; then
        export QP_ALERT_NEW=1 QP_ALERT_AGE_D=0 QP_ALERT_COUNT="$occ"
        printf '%s %s %s %s\n' "$now" "$now" 1 "$occ" >"$f"
        return 0
    fi

    # Exported because they are this library's output interface, read by the caller to
    # build its message — not incidental locals.
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
    local ns="$1" d f first last n occ mt
    d="$QP_ALERT_DIR/$ns"
    [ -d "$d" ] || return 0
    for f in "$d"/*; do
        [ -f "$f" ] || continue
        mt="$(stat -f %m "$f" 2>/dev/null || echo 0)"
        # Raised this run means the file was just written, so its mtime is not older than
        # the run stamp taken when this library was sourced.
        [ "$mt" -lt "$QP_ALERT_RUN_TS" ] || continue
        first=""; last=""; n=0; occ=0
        read -r first last n occ <"$f"
        printf 'cleared after %sd and %s occurrence(s): %s\n' \
            "$(( (QP_ALERT_RUN_TS - ${first:-QP_ALERT_RUN_TS}) / 86400 ))" \
            "${occ:-?}" "$(basename "$f")"
        rm -f "$f"
    done
}
