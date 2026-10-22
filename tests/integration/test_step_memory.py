"""Step memory records: written by the hook in each step's process, read by the resource report.

The table is the only place a step's peak survives the step, so a write that silently drops a
record, or a retry that leaves two, would put a wrong number under the daemon's headroom check.
"""

import datetime as dt

import pytest
from sqlalchemy import Engine

from quantpulse.monitoring.resources import (
    StepPeak,
    collect_resource_report,
    recent_step_peaks,
    record_step_peak,
)

pytestmark = pytest.mark.integration

T0 = dt.datetime(2026, 10, 21, 23, 0, tzinfo=dt.UTC)
MB = 1024**2


def _peak(step_key: str, mb: int, finished: dt.datetime, pid: int = 10) -> StepPeak:
    return StepPeak("run-1", "process_job", step_key, pid, T0, finished, mb * MB, (mb + 50) * MB)


def test_a_retried_step_replaces_its_record_and_old_records_age_out(db_engine: Engine) -> None:
    record_step_peak(db_engine, _peak("features", 400, T0 + dt.timedelta(seconds=20)))
    record_step_peak(db_engine, _peak("features", 420, T0 + dt.timedelta(seconds=90), pid=11))
    record_step_peak(db_engine, _peak("predictions", 350, T0 - dt.timedelta(days=2)))
    recent = recent_step_peaks(db_engine, T0 - dt.timedelta(days=1))
    assert [(p.step_key, p.peak_rss_bytes, p.pid, p.container_bytes) for p in recent] == [
        ("features", 420 * MB, 11, 470 * MB)
    ]


def test_the_report_reads_the_records_without_a_container_to_measure(db_engine: Engine) -> None:
    """Run on a host without /proc, the container figures are unknown rather than zero, and the
    step records still name the largest step."""
    record_step_peak(db_engine, _peak("features", 400, T0))
    report = collect_resource_report(db_engine, now=T0 + dt.timedelta(hours=1))
    assert report.largest_step is not None and report.largest_step.step_key == "features"
