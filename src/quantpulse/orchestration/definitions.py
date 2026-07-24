"""Dagster Definitions: the single code location loaded by webserver and daemon."""

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
# two closes, and the partition key now carries the exchange.
INGEST_HOUR_AFTER_CLOSE = 2


def _ingest_schedule(exchange: str) -> dg.ScheduleDefinition:
    ex = get_exchange(exchange)
    hour = (ex.close_hour + INGEST_HOUR_AFTER_CLOSE) % 24

    @dg.schedule(
        job=ingest_job,
        cron_schedule=f"30 {hour} * * 1-5",
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
# so it runs once, after the latest close of the day — NYSE.
process_schedule = dg.ScheduleDefinition(
    job=process_job,
    cron_schedule="0 19 * * 1-5",
    execution_timezone="America/New_York",
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
    """Fire an off-cycle retrain when the latest drift check crosses the threshold."""
    from sqlalchemy import select

    from quantpulse.db import DriftMetric, get_session

    with get_session() as session:
        latest = session.execute(
            select(DriftMetric.date, DriftMetric.value, DriftMetric.drifted)
            .where(DriftMetric.metric_name == "share_drifted")
            .order_by(DriftMetric.date.desc(), DriftMetric.id.desc())
            .limit(1)
        ).first()

    if latest is None or not latest.drifted:
        return dg.SensorResult(skip_reason="no drift beyond threshold")
    cursor_key = str(latest.date)
    if context.cursor == cursor_key:
        return dg.SensorResult(skip_reason=f"already retrained for drift on {cursor_key}")
    return dg.SensorResult(
        run_requests=[
            dg.RunRequest(
                run_key=f"drift-retrain-{cursor_key}",
                tags={"trigger": "drift", "drift_share": str(latest.value)},
            )
        ],
        cursor=cursor_key,
    )


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
    """
    import datetime as dt

    from quantpulse.data.calendar import trading_days
    from quantpulse.orchestration.catchup import missing_trading_days

    requests: list[dg.RunRequest] = []
    for exchange in sorted(EXCHANGES):
        # Each market keeps its own budget: a long JSE gap must not crowd out NYSE.
        today = market_today(exchange)
        recent = trading_days(today - dt.timedelta(days=LOOKBACK_DAYS), today, exchange)
        for day in missing_trading_days(recent, exchange)[:MAX_CATCHUP_PER_TICK]:
            key = dg.MultiPartitionKey({"date": str(day), "exchange": exchange})
            requests.append(dg.RunRequest(partition_key=key, run_key=f"catchup-{exchange}-{day}"))
    if not requests:
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

    This is what makes the options history survive stack up/down. The 19:00 schedule fires
    once; if the machine is off at that minute, that snapshot would be lost forever, because
    chains are live-only. So this sensor captures **today's** snapshot whenever it is
    missing *or* thin and the market has closed — including immediately after `make up`.
    Only *today* is salvageable: re-running tomorrow snapshots tomorrow's chains, not
    yesterday's. The one unrecoverable case left is being powered off for the entire
    post-close evening of a trading day.

    A snapshot is ~500 network calls over ~10 minutes and commits per ticker (idempotent
    upsert), so a partial run is safe to re-run. Bounded by a per-day cursor so a genuinely
    unavailable feed cannot spin the run queue all evening.

    Gated to post-close: capturing pre-market fills tickers with stale IV (≈2.1% against
    ≈33% post-close), which would leave one snapshot_date holding two incompatible
    qualities of data — worse than the clean partial it started as.
    """
    import datetime as dt

    from quantpulse.data.calendar import get_exchange, market_today
    from quantpulse.orchestration.catchup import (
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
    day_start = dt.datetime.combine(today, dt.time.min, tzinfo=get_exchange().tz)
    records = context.instance.get_run_records(
        filters=dg.RunsFilter(job_name=OPTION_CAPTURE_JOB, created_after=day_start)
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
        qp_assets.option_snapshot_quality,
        qp_assets.predictions_are_current,
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
