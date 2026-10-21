"""Headroom checks must fire early enough to act on and stay quiet otherwise — a monitor
that cries wolf gets ignored, which is worse than not having it.

Memory is judged on the daemon's container. Its cgroup counts page cache against the cap, so the
cap is reached in ordinary operation (4,949 times in a quiet day, with 0.45 s of stalls and no
kills): only kills, real stalls and the heaviest run's own processes are worth an alarm.
"""

import datetime as dt
from pathlib import Path

import pytest

from quantpulse.monitoring.resources import (
    DATABASE_CEILING_BYTES,
    MAX_MEMORY_STALL_FRACTION,
    MIN_RUNWAY_DAYS,
    Breach,
    ContainerMemory,
    ResourceReport,
    RunFootprint,
    StepPeak,
    check_headroom,
    container_memory,
    full_stall_seconds,
    heaviest_run,
    parse_keyed,
    process_peak_rss_bytes,
    process_started_at,
    resident_peak_bytes,
)

GB = 1024**3
MB = 1024**2
T0 = dt.datetime(2026, 10, 21, 23, 0, tzinfo=dt.UTC)


def report(**overrides: object) -> ResourceReport:
    base: dict[str, object] = {
        "database_bytes": {"market": 180 * MB, "dagster": 12 * MB},
        "market_rows": {"features": 104250},
        "bytes_per_day": 8.0 * MB,
        "runway_days": 2500.0,
        "container": ContainerMemory(
            limit_bytes=1536 * MB, oom_kills=0, limit_hits=4949, stall_fraction=0.000004
        ),
        "heaviest_run": RunFootprint("r1", "process_job", 900 * MB, 3),
        "largest_step": None,
    }
    return ResourceReport(**{**base, **overrides})  # type: ignore[arg-type]


def test_healthy_stack_reports_nothing() -> None:
    """Reaching the cap through cache is the normal state, not a breach."""
    assert check_headroom(report()) == []


def test_short_runway_is_flagged_with_the_number_in_it() -> None:
    breaches = check_headroom(report(runway_days=30.0))
    assert [b.name for b in breaches] == ["database_runway"]
    assert "30 days" in breaches[0].detail


def test_runway_floor_is_inclusive_of_headroom() -> None:
    """Exactly at the floor is still fine; one day under is not."""
    assert check_headroom(report(runway_days=float(MIN_RUNWAY_DAYS))) == []
    assert check_headroom(report(runway_days=MIN_RUNWAY_DAYS - 1.0))


def test_a_killed_process_is_a_breach_however_little_else_looks_wrong() -> None:
    container = ContainerMemory(1536 * MB, oom_kills=1, limit_hits=0, stall_fraction=0.0)
    breaches = check_headroom(report(container=container))
    assert [b.name for b in breaches] == ["memory_oom"]
    assert "docker-compose.yml" in breaches[0].detail


def test_stalling_on_memory_is_a_breach_and_cache_reclaim_is_not() -> None:
    quiet = ContainerMemory(1536 * MB, 0, 4949, MAX_MEMORY_STALL_FRACTION)
    assert check_headroom(report(container=quiet)) == []
    thrashing = ContainerMemory(1536 * MB, 0, 4949, 0.02)
    assert [b.name for b in check_headroom(report(container=thrashing))] == ["memory_stall"]


def test_a_heavy_run_names_its_job_and_the_remedy() -> None:
    breaches = check_headroom(report(heaviest_run=RunFootprint("r", "process_job", 1400 * MB, 3)))
    assert [b.name for b in breaches] == ["memory_pressure"]
    assert "process_job" in breaches[0].detail and "3 steps at once" in breaches[0].detail


def test_unknown_memory_is_not_treated_as_pressure() -> None:
    """Off Linux there is no cgroup to read; absence must not look like a breach."""
    unknown = ContainerMemory(None, None, None, None)
    assert check_headroom(report(container=unknown, heaviest_run=None)) == []


def test_breaches_accumulate_rather_than_short_circuit() -> None:
    container = ContainerMemory(1536 * MB, 2, 0, 0.05)
    breaches = check_headroom(report(runway_days=5.0, container=container))
    assert {b.name for b in breaches} == {"database_runway", "memory_oom", "memory_stall"}


def test_memory_fraction_is_the_heaviest_run_against_the_cap() -> None:
    assert report().memory_fraction == 900 / 1536
    assert report(heaviest_run=None).memory_fraction is None
    assert report(container=ContainerMemory(None, 0, 0, 0.0)).memory_fraction is None


def test_ceiling_is_generous_enough_to_be_a_denominator_not_a_wall() -> None:
    """Guards the intent: the ceiling exists to convert growth into runway. If someone
    lowers it near current usage, the check becomes a permanent alarm."""
    assert DATABASE_CEILING_BYTES >= 10 * GB


def test_breach_is_hashable_and_comparable() -> None:
    assert Breach("a", "b") == Breach("a", "b")


# --- the heaviest run, from the steps' peaks ------------------------------------------------


def step(key: str, pid: int, start_s: int, end_s: int, mb: int, run: str = "r1") -> StepPeak:
    return StepPeak(
        run_id=run,
        job_name="process_job",
        step_key=key,
        pid=pid,
        started_at=T0 + dt.timedelta(seconds=start_s),
        finished_at=T0 + dt.timedelta(seconds=end_s),
        peak_rss_bytes=mb * MB,
    )


def test_overlapping_steps_add_up_and_the_worker_counts_once() -> None:
    """The 2026-10-21 process run: option chains for 175 s, with features and the report beside
    it, then the rest one after another."""
    steps = [
        step("option_chains", 1, 0, 175, 300),
        step("features", 2, 0, 20, 400),
        step("resource_report", 3, 0, 1, 250),
        step("predictions", 4, 22, 27, 350),
        step("transform_dbt_assets", 5, 177, 189, 280),
    ]
    run = heaviest_run(steps, resident_bytes=444 * MB)
    assert run is not None
    # 444 resident + 250 worker (the lightest step) + 300 + 400 + 250 at the opening moment.
    assert run.bytes == (444 + 250 + 300 + 400 + 250) * MB
    assert run.concurrent_steps == 3


def test_a_step_ending_as_another_starts_did_not_overlap_it() -> None:
    run = heaviest_run([step("a", 1, 0, 10, 300), step("b", 2, 10, 20, 300)], 0)
    assert run is not None and run.concurrent_steps == 1


def test_steps_sharing_a_process_count_once_at_their_largest() -> None:
    """Run in-process, every step reports the same process's peak; summing them would count
    one process once per step."""
    shared = [step("a", 7, 0, 30, 500), step("b", 7, 0, 60, 650), step("c", 7, 0, 90, 650)]
    run = heaviest_run(shared, resident_bytes=0)
    assert run is not None and run.bytes == 650 * MB  # one process, which is also the worker


def test_the_heaviest_of_several_runs_is_the_one_reported() -> None:
    steps = [step("a", 1, 0, 10, 300, run="light"), step("b", 2, 0, 10, 900, run="heavy")]
    run = heaviest_run(steps, 0)
    assert run is not None and run.run_id == "heavy"
    assert heaviest_run([], 0) is None


# --- reading /proc and the cgroup -------------------------------------------------------------


def test_cgroup_counters_and_pressure_parse_as_the_kernel_writes_them() -> None:
    events = parse_keyed("low 0\nhigh 0\nmax 4949\noom 0\noom_kill 0\nsock_throttled 35071\n")
    assert events["max"] == 4949 and events["oom_kill"] == 0
    pressure = (
        "some avg10=0.00 avg60=0.00 avg300=0.00 total=446267\n"
        "full avg10=0.00 avg60=0.00 avg300=0.00 total=434882\n"
    )
    assert full_stall_seconds(pressure) == pytest.approx(0.434882)
    assert full_stall_seconds("") is None


def _fake_proc(root: Path, pid: int, command: str, hwm_kib: int, start_ticks: int) -> None:
    (root / str(pid)).mkdir(parents=True)
    (root / str(pid) / "cmdline").write_bytes(command.replace(" ", "\0").encode())
    (root / str(pid) / "status").write_text(f"Name:\tpython3\nVmHWM:\t{hwm_kib} kB\nVmRSS:\t1 kB\n")
    # Field 2 holds spaces, as a real command name can; the start time is field 22.
    fields = ["S"] + ["0"] * 18 + [str(start_ticks)] + ["0"] * 10
    (root / str(pid) / "stat").write_text(f"{pid} (python3 -m x) " + " ".join(fields))


def test_process_peaks_start_times_and_the_resident_pair(tmp_path: Path) -> None:
    import os

    (tmp_path / "stat").write_text("cpu 1 2 3\nbtime 1792000000\n")
    hz = os.sysconf("SC_CLK_TCK")
    _fake_proc(
        tmp_path, 1, "/usr/local/bin/python3 /usr/local/bin/dagster-daemon run", 160 * 1024, 0
    )
    _fake_proc(tmp_path, 40, "python3 -m dagster api grpc --lazy-load-user-code", 284 * 1024, hz)
    _fake_proc(tmp_path, 41, "python3 -m dagster api execute_run x", 250 * 1024, 2 * hz)
    assert process_peak_rss_bytes(40, tmp_path) == 284 * MB
    assert process_started_at(40, tmp_path) == dt.datetime.fromtimestamp(1792000001, tz=dt.UTC)
    # The run worker comes and goes with each run; only the daemon and code server are resident.
    assert resident_peak_bytes(tmp_path) == (160 + 284) * MB


def test_container_memory_turns_stall_time_into_a_share_of_its_life(tmp_path: Path) -> None:
    proc, cgroup = tmp_path / "proc", tmp_path / "cgroup"
    proc.mkdir()
    cgroup.mkdir()
    (proc / "stat").write_text("btime 1792000000\n")
    _fake_proc(proc, 1, "dagster-daemon run", 160 * 1024, 0)
    (cgroup / "memory.events").write_text("max 12\noom_kill 0\n")
    (cgroup / "memory.pressure").write_text("full avg10=0.00 total=36000000\n")  # 36 s stalled
    now = dt.datetime.fromtimestamp(1792000000 + 3600, tz=dt.UTC)  # an hour after it started
    memory = container_memory(cgroup, proc, now)
    assert memory.limit_hits == 12 and memory.oom_kills == 0
    assert memory.stall_fraction == pytest.approx(0.01)


def test_a_container_without_cgroup_files_reports_nothing_rather_than_zero(tmp_path: Path) -> None:
    memory = container_memory(tmp_path / "none", tmp_path / "none", T0)
    assert (memory.oom_kills, memory.limit_hits, memory.stall_fraction) == (None, None, None)
