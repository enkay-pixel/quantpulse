"""Resource headroom: how much room is left, and how long it lasts.

Bytes are a poor alarm — 180 MB means nothing without knowing the rate. This reports
**runway in days**, computed from the observed growth of the only table that meaningfully
grows, so the signal is "you have years" or "you have a fortnight" rather than a number
that has to be interpreted every time.

Memory is judged on the container, not on one process. A container's cgroup counts page cache
against its cap, so reaching the cap is normal and says nothing by itself; what matters is whether
anything was killed, whether processes stalled waiting for memory, and how much memory the
container could not give back during its heaviest run. All three come from the cgroup, the third
read as each step finishes (`record_step_memory`), which also records the step's own peak.

Processes cannot simply be summed: Dagster forks its step processes, and the pages they share are
counted in every process's resident size but charged to the container once. Summed, the first
night's peaks came to 143% of the cap on a night the container never reached it.

Deliberately dependency-free: no Prometheus, no cAdvisor, no Docker socket. A stack whose
defining constraint is a ≤2.5 GB footprint should not spend a gigabyte watching itself.
"""

import datetime as dt
import logging
import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine, text

logger = logging.getLogger(__name__)

# A ceiling for the market database. Nothing enforces it; it is the denominator that
# turns growth into runway. Generous on a 512 GB disk with ~277 GB free.
DATABASE_CEILING_BYTES = 20 * 1024**3

# Warn while there is still time to act, not once the disk is full.
MIN_RUNWAY_DAYS = 90
# Memory the container cannot reclaim (anon + kernel) during its heaviest run, against the cap.
MAX_MEMORY_FRACTION = 0.85
# Share of the container's life its processes spent stalled waiting for memory (pressure stall
# information, "full"). Reclaiming cache costs almost nothing, so this stays near zero until
# processes genuinely compete for memory; thrashing shows up in whole percents.
MAX_MEMORY_STALL_FRACTION = 0.001
# How far back the step records are read for the heaviest run.
STEP_WINDOW = dt.timedelta(days=1)
CGROUP = Path("/sys/fs/cgroup")

TRACKED_DATABASES = ("market", "dagster", "mlflow")


@dataclass(frozen=True)
class StepPeak:
    """One finished step: its own process at its largest, and the container as it finished."""

    run_id: str
    job_name: str
    step_key: str
    pid: int
    started_at: dt.datetime
    finished_at: dt.datetime
    peak_rss_bytes: int
    # The container's unreclaimable memory (anon + kernel) as the step finished, shared pages once.
    container_bytes: int | None = None


@dataclass(frozen=True)
class RunFootprint:
    """The most unreclaimable memory the container held during one run, read as its steps
    finished, and the most of its steps that overlapped."""

    run_id: str
    job_name: str
    bytes: int
    concurrent_steps: int


@dataclass(frozen=True)
class ContainerMemory:
    """The container's own counters, all since it started."""

    limit_bytes: int | None
    oom_kills: int | None
    limit_hits: int | None
    stall_fraction: float | None


@dataclass(frozen=True)
class ResourceReport:
    database_bytes: dict[str, int]
    market_rows: dict[str, int]
    bytes_per_day: float | None  # observed growth of option_quotes, the only real grower
    runway_days: float | None  # until DATABASE_CEILING_BYTES at that rate
    container: ContainerMemory
    heaviest_run: RunFootprint | None
    largest_step: StepPeak | None

    @property
    def memory_fraction(self) -> float | None:
        """The heaviest recent run's footprint against the container cap."""
        if self.heaviest_run is None or not self.container.limit_bytes:
            return None
        return self.heaviest_run.bytes / self.container.limit_bytes


@dataclass(frozen=True)
class Breach:
    name: str
    detail: str


def process_rss_bytes() -> int | None:
    """Resident memory of the current process now, or None off Linux (e.g. a macOS host).

    Right for a container that runs one process, such as the API. Not for the daemon's, where
    runs and their steps are separate processes: see `container_memory` and `heaviest_run`.
    """
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def process_peak_rss_bytes(pid: int | str = "self", proc: Path = Path("/proc")) -> int | None:
    """A process's peak resident memory (VmHWM), or None off Linux (e.g. a macOS host)."""
    try:
        for line in (proc / str(pid) / "status").read_text().splitlines():
            if line.startswith("VmHWM:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def process_started_at(pid: int | str = "self", proc: Path = Path("/proc")) -> dt.datetime | None:
    """When a process started: its start in clock ticks after boot, plus the boot time."""
    try:
        # The command name in field 2 may hold spaces, so count fields from after its ')'.
        after_name = (proc / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()
        ticks = int(after_name[19])  # field 22, starttime
        btime = next(
            int(line.split()[1])
            for line in (proc / "stat").read_text().splitlines()
            if line.startswith("btime ")
        )
    except (OSError, ValueError, IndexError, StopIteration):
        return None
    return dt.datetime.fromtimestamp(btime + ticks / os.sysconf("SC_CLK_TCK"), tz=dt.UTC)


def container_unreclaimable_bytes(cgroup: Path = CGROUP) -> int | None:
    """Memory the container cannot reclaim right now: anonymous plus kernel, from memory.stat.

    Page cache is left out because the kernel drops it under pressure; anonymous memory and kernel
    allocations are what an out-of-memory kill is about. Shared pages are counted once.
    """
    try:
        stat = parse_keyed((cgroup / "memory.stat").read_text())
    except OSError:
        return None
    if "anon" not in stat:
        return None
    return stat["anon"] + stat.get("kernel", 0)


def parse_keyed(text_: str) -> dict[str, int]:
    """`key value` lines, as cgroup files such as memory.events hold them."""
    out: dict[str, int] = {}
    for line in text_.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].isdigit():
            out[parts[0]] = int(parts[1])
    return out


def full_stall_seconds(pressure: str) -> float | None:
    """Total time every non-idle process stalled on memory, from a cgroup's memory.pressure."""
    for line in pressure.splitlines():
        if line.startswith("full "):
            fields = dict(f.split("=", 1) for f in line.split()[1:] if "=" in f)
            try:
                return int(fields["total"]) / 1e6
            except (KeyError, ValueError):
                return None
    return None


def container_memory(
    cgroup: Path = CGROUP, proc: Path = Path("/proc"), now: dt.datetime | None = None
) -> ContainerMemory:
    """The container's kills, cap hits and memory stalls, each counted since it started."""

    def read(name: str) -> str | None:
        try:
            return (cgroup / name).read_text()
        except OSError:
            return None

    events = parse_keyed(read("memory.events") or "")
    pressure = read("memory.pressure")
    stalled = full_stall_seconds(pressure) if pressure else None
    started = process_started_at(1, proc)
    now = now or dt.datetime.now(dt.UTC)
    age = (now - started).total_seconds() if started else None
    return ContainerMemory(
        limit_bytes=cgroup_memory_limit_bytes(),
        oom_kills=events.get("oom_kill"),
        limit_hits=events.get("max"),
        stall_fraction=stalled / age if stalled is not None and age else None,
    )


def heaviest_run(steps: Iterable[StepPeak]) -> RunFootprint | None:
    """The run during which the container held the most memory it could not reclaim.

    Read from each step's record of the container as it finished, so it is a sample at step
    boundaries rather than a continuous peak; a long step's high point between boundaries can be
    missed. Runs whose steps carry no container reading are left out. The overlap count treats
    steps that shared a process (an in-process executor) as one.
    """
    by_run: dict[str, list[StepPeak]] = {}
    for step in steps:
        if step.container_bytes is not None:
            by_run.setdefault(step.run_id, []).append(step)
    heaviest: RunFootprint | None = None
    for run_id, run_steps in by_run.items():
        processes: dict[int, tuple[dt.datetime, dt.datetime]] = {}
        for st in run_steps:
            start, end = processes.get(st.pid, (st.started_at, st.finished_at))
            processes[st.pid] = (min(start, st.started_at), max(end, st.finished_at))
        # A process ending at the instant another starts did not overlap it: ends sort first.
        events = sorted(
            [(a, 1) for a, _ in processes.values()] + [(b, -1) for _, b in processes.values()]
        )
        alive = most_alive = 0
        for _, change in events:
            alive += change
            most_alive = max(most_alive, alive)
        held = max(st.container_bytes or 0 for st in run_steps)
        footprint = RunFootprint(run_id, run_steps[0].job_name, held, most_alive)
        if heaviest is None or footprint.bytes > heaviest.bytes:
            heaviest = footprint
    return heaviest


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
        total: int = conn.execute(
            text("SELECT pg_total_relation_size('option_quotes')")
        ).scalar_one()
        days: int = conn.execute(
            text(
                "SELECT count(*) FROM (SELECT snapshot_date FROM option_quotes "
                "WHERE snapshot_date < current_date GROUP BY snapshot_date) d"
            )
        ).scalar_one()
    if not days or not total:
        return None
    return float(total) / float(days)


def record_step_peak(engine: Engine, peak: StepPeak) -> None:
    """Store one finished step's peak memory; a retried step replaces its earlier record."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO step_memory (run_id, step_key, job_name, pid, started_at, "
                "finished_at, peak_rss_bytes, container_bytes) VALUES (:run_id, :step_key, "
                ":job_name, :pid, :started_at, :finished_at, :peak_rss_bytes, :container_bytes) "
                "ON CONFLICT (run_id, step_key) DO UPDATE SET pid = excluded.pid, "
                "started_at = excluded.started_at, finished_at = excluded.finished_at, "
                "peak_rss_bytes = excluded.peak_rss_bytes, "
                "container_bytes = excluded.container_bytes"
            ),
            {
                "run_id": peak.run_id,
                "step_key": peak.step_key,
                "job_name": peak.job_name,
                "pid": peak.pid,
                "started_at": peak.started_at,
                "finished_at": peak.finished_at,
                "peak_rss_bytes": peak.peak_rss_bytes,
                "container_bytes": peak.container_bytes,
            },
        )


def recent_step_peaks(engine: Engine, since: dt.datetime) -> list[StepPeak]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT run_id, job_name, step_key, pid, started_at, finished_at, peak_rss_bytes, "
                "container_bytes FROM step_memory WHERE finished_at >= :since"
            ),
            {"since": since},
        ).all()
    return [
        StepPeak(
            run_id=r.run_id,
            job_name=r.job_name,
            step_key=r.step_key,
            pid=int(r.pid),
            started_at=r.started_at,
            finished_at=r.finished_at,
            peak_rss_bytes=int(r.peak_rss_bytes),
            container_bytes=None if r.container_bytes is None else int(r.container_bytes),
        )
        for r in rows
    ]


def collect_resource_report(engine: Engine, now: dt.datetime | None = None) -> ResourceReport:
    """Sample database sizes, row counts, growth, the container's memory counters, and the
    heaviest recent run."""
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

    now = now or dt.datetime.now(dt.UTC)
    steps = recent_step_peaks(engine, now - STEP_WINDOW)
    return ResourceReport(
        database_bytes=database_bytes,
        market_rows=market_rows,
        bytes_per_day=bytes_per_day,
        runway_days=runway,
        container=container_memory(now=now),
        heaviest_run=heaviest_run(steps),
        largest_step=max(steps, key=lambda st: st.peak_rss_bytes, default=None),
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

    container = report.container
    if container.oom_kills:
        breaches.append(
            Breach(
                "memory_oom",
                f"{container.oom_kills} process(es) killed for memory since the container started "
                "— raise the limit in docker-compose.yml",
            )
        )
    if (
        container.stall_fraction is not None
        and container.stall_fraction > MAX_MEMORY_STALL_FRACTION
    ):
        breaches.append(
            Breach(
                "memory_stall",
                f"processes stalled on memory {container.stall_fraction:.2%} of the time since "
                f"the container started (ceiling {MAX_MEMORY_STALL_FRACTION:.1%})",
            )
        )
    fraction = report.memory_fraction
    if fraction is not None and fraction > MAX_MEMORY_FRACTION and report.heaviest_run:
        run = report.heaviest_run
        breaches.append(
            Breach(
                "memory_pressure",
                f"during {run.job_name} the container held {fraction:.0%} of its cap in memory it "
                f"cannot reclaim (ceiling {MAX_MEMORY_FRACTION:.0%}, {run.concurrent_steps} steps "
                "at once) "
                "— raise the limit in docker-compose.yml or run fewer steps at once",
            )
        )

    return breaches
