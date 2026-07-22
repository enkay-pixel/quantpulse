"""Resource headroom: how much room is left, and how long it lasts.

Bytes are a poor alarm — 180 MB means nothing without knowing the rate. This reports
**runway in days**, computed from the observed growth of the only table that meaningfully
grows, so the signal is "you have years" or "you have a fortnight" rather than a number
that has to be interpreted every time.

Deliberately dependency-free: no Prometheus, no cAdvisor, no Docker socket. A stack whose
defining constraint is a ≤2.5 GB footprint should not spend a gigabyte watching itself.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine, text

logger = logging.getLogger(__name__)

# A ceiling for the market database. Nothing enforces it; it is the denominator that
# turns growth into runway. Generous on a 512 GB disk with ~277 GB free.
DATABASE_CEILING_BYTES = 20 * 1024**3

# Warn while there is still time to act, not once the disk is full.
MIN_RUNWAY_DAYS = 90
# Containers sit well under their caps; flag sustained pressure before the OOM killer.
MAX_MEMORY_FRACTION = 0.85

TRACKED_DATABASES = ("market", "dagster", "mlflow")


@dataclass(frozen=True)
class ResourceReport:
    database_bytes: dict[str, int]
    market_rows: dict[str, int]
    bytes_per_day: float | None  # observed growth of option_quotes, the only real grower
    runway_days: float | None  # until DATABASE_CEILING_BYTES at that rate
    memory_used_bytes: int | None
    memory_limit_bytes: int | None

    @property
    def memory_fraction(self) -> float | None:
        if not self.memory_used_bytes or not self.memory_limit_bytes:
            return None
        return self.memory_used_bytes / self.memory_limit_bytes


@dataclass(frozen=True)
class Breach:
    name: str
    detail: str


def process_rss_bytes() -> int | None:
    """Resident memory of the current process, or None off Linux (e.g. macOS host)."""
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def cgroup_memory_limit_bytes() -> int | None:
    """The container's own memory cap, read from cgroup v2 then v1.

    Read rather than hardcoded so that raising a limit in docker-compose.yml is picked up
    without touching this file — the usual failure mode for capacity checks is a threshold
    that silently disagrees with reality.
    """
    for path in (
        Path("/sys/fs/cgroup/memory.max"),
        Path("/sys/fs/cgroup/memory/memory.limit_in_bytes"),
    ):
        try:
            raw = path.read_text().strip()
        except OSError:
            continue
        if raw == "max":  # cgroup v2 for "no limit"
            return None
        try:
            value = int(raw)
        except ValueError:
            continue
        # An unlimited v1 cgroup reports a sentinel near 2^63; treat that as no cap.
        return None if value > 2**62 else value
    return None


def _options_growth(engine: Engine) -> float | None:
    """Bytes per day, from option_quotes' own size over its distinct snapshot days.

    Uses complete days only: the in-progress snapshot for today would drag the average
    down and overstate the runway.
    """
    with engine.connect() as conn:
        total = conn.execute(text("SELECT pg_total_relation_size('option_quotes')")).scalar_one()
        days = conn.execute(
            text(
                "SELECT count(*) FROM (SELECT snapshot_date FROM option_quotes "
                "WHERE snapshot_date < current_date GROUP BY snapshot_date) d"
            )
        ).scalar_one()
    if not days or not total:
        return None
    return float(total) / float(days)


def collect_resource_report(engine: Engine) -> ResourceReport:
    """Sample database sizes, row counts, growth, and this process's memory."""
    with engine.connect() as conn:
        database_bytes = {
            row.datname: int(row.size)
            for row in conn.execute(
                text(
                    "SELECT datname, pg_database_size(datname) AS size FROM pg_database "
                    "WHERE datname = ANY(:names)"
                ),
                {"names": list(TRACKED_DATABASES)},
            )
        }
        market_rows = {
            row.relname: int(row.n_live_tup)
            for row in conn.execute(
                text(
                    "SELECT relname, n_live_tup FROM pg_stat_user_tables "
                    "ORDER BY n_live_tup DESC LIMIT 8"
                )
            )
        }

    bytes_per_day = _options_growth(engine)
    market = database_bytes.get("market", 0)
    runway = None
    if bytes_per_day and bytes_per_day > 0:
        runway = max(0.0, (DATABASE_CEILING_BYTES - market) / bytes_per_day)

    return ResourceReport(
        database_bytes=database_bytes,
        market_rows=market_rows,
        bytes_per_day=bytes_per_day,
        runway_days=runway,
        memory_used_bytes=process_rss_bytes(),
        memory_limit_bytes=cgroup_memory_limit_bytes(),
    )


def check_headroom(report: ResourceReport) -> list[Breach]:
    """Threshold breaches worth surfacing, empty when everything has room."""
    breaches: list[Breach] = []

    if report.runway_days is not None and report.runway_days < MIN_RUNWAY_DAYS:
        breaches.append(
            Breach(
                "database_runway",
                f"{report.runway_days:.0f} days of growth left before "
                f"{DATABASE_CEILING_BYTES / 1024**3:.0f} GB (floor {MIN_RUNWAY_DAYS})",
            )
        )

    fraction = report.memory_fraction
    if fraction is not None and fraction > MAX_MEMORY_FRACTION:
        breaches.append(
            Breach(
                "memory_pressure",
                f"process at {fraction:.0%} of its container cap "
                f"(ceiling {MAX_MEMORY_FRACTION:.0%}) — raise the limit in docker-compose.yml",
            )
        )

    return breaches
