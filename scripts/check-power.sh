#!/usr/bin/env bash
# Warn when sleep is disabled *and* the Mac is on battery.
#
# `pmset disablesleep 1` is what lets the stack run overnight with the lid closed, but the
# setting is system-wide — macOS stores it under SystemPowerSettings, not per power source,
# so `-c` does not scope it to AC no matter what the flag suggests. Unplugged, it means the
# machine will run itself flat and, lid closed, do so with no airflow.
#
# Individually both states are fine and common; only the combination is a problem, which is
# exactly the kind of thing a human stops noticing. It recurred twice in two days here.
set -uo pipefail

# Running every two hours, this had produced 47 identical notifications over 17 days for one
# unchanged setting. The log still records every check; only the notification decays.
DEDUP_LIB="$(dirname "$0")/lib/dedup.sh"
# shellcheck source=scripts/lib/dedup.sh
[ -r "$DEDUP_LIB" ] && . "$DEDUP_LIB"
# A missing library degrades to notifying every time, never to silence. Suppression is the
# dangerous direction to fail in: the loud version is annoying, the quiet one hides a flat
# battery.
if ! command -v qp_alert_due >/dev/null 2>&1; then
    qp_alert_due() { return 0; }
    qp_alert_sweep() { :; }
fi

sleep_disabled=$(pmset -g 2>/dev/null | awk '/SleepDisabled/ {print $2}')
on_battery=$(pmset -g ps 2>/dev/null | head -1 | grep -qv "AC Power" && echo yes || echo no)

if [ "$sleep_disabled" = "1" ] && [ "$on_battery" = "yes" ]; then
    charge=$(pmset -g batt 2>/dev/null | grep -o '[0-9]*%' | head -1)
    printf '%s WARN: sleep disabled on battery (%s)\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$charge"
    if qp_alert_due power "sleep disabled on battery ($charge)"; then
        # After the first, say how long it has stood — a reminder that reads identically to
        # the original alert is what taught you to ignore it.
        context=""
        [ "${QP_ALERT_NEW:-1}" = "1" ] || context=" Standing ${QP_ALERT_AGE_D}d over \
${QP_ALERT_COUNT} checks."
        osascript -e "display notification \"Sleep is disabled and you are on battery ($charge). \
Plug in, or run: sudo pmset -a disablesleep 0.$context\" \
            with title \"QuantPulse: power warning\"" 2>/dev/null || true
    fi
    exit 0
fi

# Nothing has ever told you the condition stopped, which is half of what makes a standing
# alert readable: you could not tell "still true" from "fixed and forgotten".
resolved=$(qp_alert_sweep power)
if [ -n "$resolved" ]; then
    printf '%s resolved: %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$resolved"
    osascript -e "display notification \"Power warning cleared — $resolved\" \
        with title \"QuantPulse: power ok\"" 2>/dev/null || true
fi

printf '%s ok (SleepDisabled=%s, battery=%s)\n' "$(date '+%Y-%m-%d %H:%M:%S')" \
    "${sleep_disabled:-?}" "$on_battery"
