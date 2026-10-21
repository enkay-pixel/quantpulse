"""Hooks attached to every job: they run in each step's own process as the step finishes.

The one here records the step's peak memory. The daemon container's cap is shared by the daemon,
its code server, each run's worker and every step process, and only a step's own process knows
how large it grew, so the record has to be made there, before the process exits.
"""

import dagster as dg


def _record(context: dg.HookContext) -> None:
    import datetime as dt
    import os

    from quantpulse.db import get_engine
    from quantpulse.monitoring.resources import (
        StepPeak,
        process_peak_rss_bytes,
        process_started_at,
        record_step_peak,
    )

    peak, started = process_peak_rss_bytes(), process_started_at()
    if peak is None or started is None:
        return  # not on Linux, so there is no /proc to read
    try:
        record_step_peak(
            get_engine(),
            StepPeak(
                run_id=context.run_id,
                job_name=context.job_name,
                step_key=context.step_key,
                pid=os.getpid(),
                started_at=started,
                finished_at=dt.datetime.now(dt.UTC),
                peak_rss_bytes=peak,
            ),
        )
    except Exception:
        # A measurement must never fail the work it measures.
        context.log.warning("Could not record this step's peak memory", exc_info=True)


@dg.success_hook(name="record_step_memory")
def record_step_memory(context: dg.HookContext) -> None:
    _record(context)


@dg.failure_hook(name="record_failed_step_memory")
def record_failed_step_memory(context: dg.HookContext) -> None:
    """A step that fails for want of memory is the one most worth recording."""
    _record(context)


STEP_HOOKS = frozenset({record_step_memory, record_failed_step_memory})
