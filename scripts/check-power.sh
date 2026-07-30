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

sleep_disabled=$(pmset -g 2>/dev/null | awk '/SleepDisabled/ {print $2}')
on_battery=$(pmset -g ps 2>/dev/null | head -1 | grep -qv "AC Power" && echo yes || echo no)

if [ "$sleep_disabled" = "1" ] && [ "$on_battery" = "yes" ]; then
    charge=$(pmset -g batt 2>/dev/null | grep -o '[0-9]*%' | head -1)
    printf '%s WARN: sleep disabled on battery (%s)\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$charge"
    osascript -e "display notification \"Sleep is disabled and you are on battery ($charge). \
Plug in, or run: sudo pmset -a disablesleep 0\" \
        with title \"QuantPulse: power warning\"" 2>/dev/null || true
    exit 0
fi

printf '%s ok (SleepDisabled=%s, battery=%s)\n' "$(date '+%Y-%m-%d %H:%M:%S')" \
    "${sleep_disabled:-?}" "$on_battery"
