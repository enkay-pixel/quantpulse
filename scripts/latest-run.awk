# Print a scheduled job's latest run from its log: the last group of lines whose timestamps follow
# each other within `gap` minutes (default 20), plus the unstamped lines among and after them.
#
# A run is not one minute long. A job can stamp a problem at 08:00 and append a diagnosis of it at
# 08:04 or later; reading only the lines stamped with the log's last minute dropped the problem and
# kept the diagnosis, so `make status` showed a stopped paper book as healthy for two days
# (incident 41). The gap must outlast the longest run (about 15 minutes) and fall short of the most
# frequent job's interval (30 minutes).
#
# Timestamps are `YYYY-MM-DD HH:MM` at the start of a line. Minutes are counted from a day number,
# so a run that crosses midnight stays one run.
function day_number(y, m, d,    a, yy, mm) {
    a = int((14 - m) / 12)
    yy = y + 4800 - a
    mm = m + 12 * a - 3
    return d + int((153 * mm + 2) / 5) + 365 * yy + int(yy / 4) - int(yy / 100) + int(yy / 400)
}
BEGIN { if (gap == "") gap = 20 }
{ line[NR] = $0 }
/^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:[0-9][0-9]/ {
    t = day_number(substr($0, 1, 4) + 0, substr($0, 6, 2) + 0, substr($0, 9, 2) + 0) * 1440 \
        + substr($0, 12, 2) * 60 + substr($0, 15, 2)
    if (!stamped || t - last > gap) start = NR
    last = t
    stamped = 1
}
END { if (stamped) for (i = start; i <= NR; i++) print line[i] }
