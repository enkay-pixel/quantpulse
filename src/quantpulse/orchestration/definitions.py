"""Dagster Definitions: the single code location loaded by webserver and daemon.

Read this file to learn what the platform does on a timer. It wires four things together
and nothing else: **jobs** (which assets run together), **schedules** (when, in whose
timezone), **sensors** (what reacts to state), and the `defs` object at the bottom that
Dagster actually loads. Every sensor's real logic lives in `orchestration/catchup.py`, so
it can be unit tested without a Dagster instance.

**Why sensor bodies import inside themselves.** The daemon re-imports this module on every
reload while evaluating sensors on a 30-second loop; it needs the schedule and sensor
*definitions*, not the database or ML stack. Importing this module already costs ~4.75s,
almost all of it Dagster itself. Same convention as `assets.py` and `cli.py`.
"""

import dagster as dg
from quantpulse.data.calendar import EXCHANGES, get_exchange, is_trading_day, market_today
from quantpulse.orchestration import assets as qp_assets
from quantpulse.orchestration.transform_assets import dbt_resource, transform_dbt_assets

# Partitioning is inferred from the selected asset (raw_prices is daily-partitioned).
ingest_job = dg.define_asset_job("ingest_job", selection=[qp_assets.raw_prices])

process_job = dg.define_asset_job(
    "process_job",
    selection=dg.AssetSelection.assets(
        qp_assets.features,
        qp_assets.predictions,
        qp_assets.portfolio_equity,
        qp_assets.drift_report,
        qp_assets.option_chains,
        qp_assets.resource_report,
    )
    | dg.AssetSelection.groups("transform"),
)

training_job = dg.define_asset_job("training_job", selection=[qp_assets.champion_model])

# Catch-up bounds: how far back to look for skipped sessions, and how many to request
# per sensor tick (so a long sleep doesn't stampede the queue).
LOOKBACK_DAYS = 30
MAX_CATCHUP_PER_TICK = 3
# A snapshot is ~10 minutes of network calls; a feed that is genuinely down should not
# be retried all day, so cap same-day repairs.
MAX_OPTION_REPAIRS_PER_DAY = 3

# All schedules default to RUNNING: `make up` must mean fully automated —
# without this, Dagster ships schedules stopped until toggled in the UI.

# Ingest runs per market, in that market's own timezone, a couple of hours after its
# close. build_schedule_from_partitioned_job cannot express this: one cron cannot serve
# two closes, and the partition key now carries the exchange. The fire time lives in
# catchup.py because the catch-up sensor must know when the schedule has had its turn.


def _ingest_schedule(exchange: str) -> dg.ScheduleDefinition:
    from quantpulse.orchestration.catchup import INGEST_HOUR_AFTER_CLOSE, INGEST_MINUTE

    ex = get_exchange(exchange)
    hour = (ex.close_hour + INGEST_HOUR_AFTER_CLOSE) % 24

    @dg.schedule(
        job=ingest_job,
        cron_schedule=f"{INGEST_MINUTE} {hour} * * 1-5",
        execution_timezone=ex.timezone,
        name=f"daily_ingest_{exchange.lower()}",
        default_status=dg.DefaultScheduleStatus.RUNNING,
    )
    def _schedule(context: dg.ScheduleEvaluationContext) -> dg.RunRequest | dg.SkipReason:
        day = market_today(exchange)
        if not is_trading_day(day, exchange):
            return dg.SkipReason(f"{day} is not a {exchange} session")
        key = dg.MultiPartitionKey({"date": str(day), "exchange": exchange})
        return dg.RunRequest(partition_key=key, run_key=f"ingest-{exchange}-{day}")

    return _schedule


ingest_schedules = [_ingest_schedule(code) for code in sorted(EXCHANGES)]


# Processing is cross-market (features rank within each exchange, books build per market),
# so it runs once, after the latest close of the day — NYSE. The hour comes from catchup
# alongside the ingest constants, so that "when does processing run" and "are features owed
# yet" cannot drift apart; a checker that disagreed with the cron reported a daily stall.
def _process_constants() -> tuple[int, int, str]:
    from quantpulse.orchestration.catchup import PROCESS_HOUR, PROCESS_MINUTE, PROCESS_TIMEZONE

    return PROCESS_HOUR, PROCESS_MINUTE, PROCESS_TIMEZONE


_process = _process_constants()
process_schedule = dg.ScheduleDefinition(
    job=process_job,
    cron_schedule=f"{_process[1]} {_process[0]} * * 1-5",
    execution_timezone=_process[2],
    name="daily_process_schedule",
    default_status=dg.DefaultScheduleStatus.RUNNING,
)

# Weekly retrain, Saturday morning.
training_schedule = dg.ScheduleDefinition(
    job=training_job,
    cron_schedule="0 9 * * 6",
    execution_timezone="America/New_York",
    name="weekly_training_schedule",
    default_status=dg.DefaultScheduleStatus.RUNNING,
)


@dg.sensor(
    job=training_job,
    minimum_interval_seconds=3600,
    default_status=dg.DefaultSensorStatus.RUNNING,
)
def drift_retrain_sensor(context: dg.SensorEvaluationContext) -> dg.SensorResult:
    """Fire an off-cycle retrain when a market's latest drift check crosses the threshold.

    Evaluated per market: a pooled reading dilutes one market's drift with the other's
    calm, and firing on it retrains both on evidence about neither. The cursor carries each
    market's last-fired date so one drifting market cannot lock out the other's trigger.
    """
    import json

    from sqlalchemy import select

    from quantpulse.db import DriftMetric, get_session

    fired: dict[str, str] = json.loads(context.cursor) if context.cursor else {}
    requests, skipped = [], []
    with get_session() as session:
        for exchange in sorted(EXCHANGES):
            latest = session.execute(
                select(DriftMetric.date, DriftMetric.value, DriftMetric.drifted)
                .where(
                    DriftMetric.metric_name == "share_drifted",
                    DriftMetric.exchange == exchange,
                )
                .order_by(DriftMetric.date.desc(), DriftMetric.id.desc())
                .limit(1)
            ).first()
            if latest is None or not latest.drifted:
                skipped.append(exchange)
                continue
            day = str(latest.date)
            if fired.get(exchange) == day:
                skipped.append(f"{exchange} (already retrained for {day})")
                continue
            requests.append(
                dg.RunRequest(
                    run_key=f"drift-retrain-{exchange}-{day}",
                    tags={
                        "trigger": "drift",
                        "exchange": exchange,
                        "drift_share": str(latest.value),
                    },
                )
            )
            fired[exchange] = day

    if not requests:
        return dg.SensorResult(skip_reason=f"no drift beyond threshold: {', '.join(skipped)}")
    return dg.SensorResult(run_requests=requests, cursor=json.dumps(fired))


@dg.run_failure_sensor(
    default_status=dg.DefaultSensorStatus.RUNNING,
    monitor_all_code_locations=True,
)
def pipeline_failure_alert(context: dg.RunFailureSensorContext) -> None:
    """Make failures visible. A local-first platform whose whole premise is accumulating
    irreplaceable daily history cannot fail silently — without this, a broken 7pm run is
    only noticed days later via stale dates on the dashboard."""
    from quantpulse.monitoring.alerts import record_failure

    record_failure(
        job_name=context.dagster_run.job_name,
        run_id=context.dagster_run.run_id,
        error=str(context.failure_event.message or "unknown error"),
    )
    context.log.error("ALERT: %s failed — see alerts log", context.dagster_run.job_name)


@dg.sensor(
    job=ingest_job,
    minimum_interval_seconds=1800,
    default_status=dg.DefaultSensorStatus.RUNNING,
)
def missed_partition_catchup_sensor(context: dg.SensorEvaluationContext) -> dg.SensorResult:
    """Backfill trading days the schedule slept through.

    Schedules only fire while the stack is up, and this runs on a laptop that sleeps.
    Rather than silently skipping those days, request the missing daily partitions
    (bounded per tick) whenever the stack comes back.

    Two rules, matching the option sensor:
    - Today only counts as *missed* once its scheduled ingest is overdue — the exchange
      date flips at midnight, hours before the session trades, and a rescue fired then
      runs against a session that does not exist yet.
    - The retry budget comes from Dagster's run history for the partition, and every
      run_key is fresh: a run_key is deduplicated forever, so a fixed one strands the
      day after a single premature or failed attempt.
    """
    import datetime as dt

    from quantpulse.data.calendar import trading_days
    from quantpulse.orchestration.catchup import (
        benchmark_missing_days,
        exchange_day_start_utc,
        ingest_overdue,
        missing_trading_days,
        next_ingest_attempt,
    )

    requests: list[dg.RunRequest] = []
    exhausted: list[str] = []
    for exchange in sorted(EXCHANGES):
        # Each market keeps its own budget: a long JSE gap must not crowd out NYSE.
        today = market_today(exchange)
        end = today if ingest_overdue(exchange=exchange) else today - dt.timedelta(days=1)
        recent = trading_days(today - dt.timedelta(days=LOOKBACK_DAYS), end, exchange)
        day_start = exchange_day_start_utc(today, exchange)
        # Two reasons to re-ingest a session, deduplicated into one queue so a day that is
        # both thin AND missing its benchmark is requested once and spends one attempt.
        # Coverage first: it is the older, broader signal, and a session it flags is
        # missing the benchmark's bar too.
        due = missing_trading_days(recent, exchange)
        due += [day for day in benchmark_missing_days(recent, exchange) if day not in set(due)]
        for day in sorted(due)[:MAX_CATCHUP_PER_TICK]:
            key = dg.MultiPartitionKey({"date": str(day), "exchange": exchange})
            # Scheduled runs carry the same partition tag, so a failing 18:30 ingest
            # also consumes this budget rather than being retried on top of.
            partition = dg.RunsFilter(
                job_name=ingest_job.name, tags={"dagster/partition": str(key)}
            )
            history = context.instance.get_run_records(filters=partition)
            todays = context.instance.get_run_records(
                filters=dg.RunsFilter(
                    job_name=ingest_job.name,
                    tags={"dagster/partition": str(key)},
                    created_after=day_start,
                )
            )
            attempt = next_ingest_attempt(
                [(r.dagster_run.status.value, r.start_time) for r in history],
                [(r.dagster_run.status.value, r.start_time) for r in todays],
            )
            if attempt is None:
                exhausted.append(f"{exchange} {day}")
                continue
            requests.append(
                dg.RunRequest(partition_key=key, run_key=f"catchup-{exchange}-{day}-{attempt}")
            )
    if not requests:
        # Distinguish the two silences. "Nothing missing" and "missing, but I have given
        # up on it today" look identical from outside and mean opposite things — the
        # second is the one worth a human's attention, and reporting it as the first is
        # how a 24-hour outage left two sessions stranded with the sensor claiming health.
        if exhausted:
            return dg.SensorResult(
                skip_reason=(
                    f"{len(exhausted)} session(s) still missing but out of attempts for "
                    f"today, retrying tomorrow: {', '.join(exhausted[:4])}"
                )
            )
        return dg.SensorResult(skip_reason="no missed trading days in the lookback window")
    return dg.SensorResult(run_requests=requests)


OPTION_CAPTURE_JOB = "option_resnapshot_job"


@dg.sensor(
    job=dg.define_asset_job(OPTION_CAPTURE_JOB, selection=[qp_assets.option_chains]),
    minimum_interval_seconds=1800,
    default_status=dg.DefaultSensorStatus.RUNNING,
)
def option_snapshot_repair_sensor(context: dg.SensorEvaluationContext) -> dg.SensorResult:
    """Ensure today's option snapshot exists, whenever the stack is up post-close.

    Option chains are live-only, so a snapshot missed at its scheduled minute is lost for
    good. This captures today's snapshot whenever it is missing or thin and the market has
    closed, including right after the stack comes up. Only today is recoverable: re-running
    tomorrow captures tomorrow's chains.

    A snapshot is several hundred network calls and commits per ticker, so a partial run is
    safe to re-run. A per-day budget stops an unavailable feed filling the run queue.

    Gated to post-close because pre-market implied volatility is stale, and one
    snapshot_date holding both qualities of data is worse than a clean partial. The capture
    enforces that gate itself; skipping here as well keeps pre-market ticks from queueing
    runs that would fail on arrival and spend the retry budget.
    """
    from quantpulse.data.calendar import market_today
    from quantpulse.orchestration.catchup import (
        exchange_day_start_utc,
        is_post_close,
        option_snapshot_incomplete,
        summarize_capture_runs,
    )

    if not is_post_close():
        return dg.SensorResult(
            skip_reason="before the close — option IV is not yet meaningful to snapshot"
        )

    # Must be the same clock the ingest stamps rows with, or it looks at a day that does
    # not exist yet and re-snapshots forever.
    today = market_today()
    coverage = option_snapshot_incomplete(today)
    if coverage is None:
        return dg.SensorResult(skip_reason="today's option snapshot is already complete")

    # The budget is derived from Dagster's own run history rather than a cursor the sensor
    # increments hopefully: a run cancelled before it ever left the queue never reached the
    # vendor, so it must not count. (A cursor counted requests, which is how three
    # cancelled pre-market runs locked the sensor out for a whole evening.)
    records = context.instance.get_run_records(
        filters=dg.RunsFilter(
            job_name=OPTION_CAPTURE_JOB, created_after=exchange_day_start_utc(today)
        )
    )
    in_flight, reached_feed = summarize_capture_runs(
        [(r.dagster_run.status.value, r.start_time) for r in records]
    )
    if in_flight:
        return dg.SensorResult(skip_reason="a capture for today is already in flight")
    if reached_feed >= MAX_OPTION_REPAIRS_PER_DAY:
        return dg.SensorResult(
            skip_reason=(
                f"today's snapshot already reached the feed {reached_feed}x "
                f"at {coverage:.0%} coverage"
            )
        )
    # Suffix by total runs (cancelled included) so each emission gets a fresh run_key —
    # reusing one Dagster has already seen would be silently deduplicated.
    return dg.SensorResult(
        run_requests=[dg.RunRequest(run_key=f"option-snapshot-{today}-{len(records) + 1}")]
    )


defs = dg.Definitions(
    assets=[
        qp_assets.raw_prices,
        qp_assets.features,
        qp_assets.predictions,
        qp_assets.portfolio_equity,
        qp_assets.drift_report,
        qp_assets.option_chains,
        qp_assets.resource_report,
        qp_assets.champion_model,
        transform_dbt_assets,
    ],
    asset_checks=[
        qp_assets.recent_prices_quality,
        qp_assets.benchmark_freshness,
        qp_assets.option_snapshot_quality,
        qp_assets.predictions_are_current,
        qp_assets.champion_registry_agrees,
        qp_assets.resource_headroom,
    ],
    jobs=[ingest_job, process_job, training_job],
    schedules=[*ingest_schedules, process_schedule, training_schedule],
    sensors=[
        drift_retrain_sensor,
        pipeline_failure_alert,
        missed_partition_catchup_sensor,
        option_snapshot_repair_sensor,
    ],
    resources={"dbt": dbt_resource},
)
