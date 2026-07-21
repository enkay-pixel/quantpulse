"""Dagster Definitions: the single code location loaded by webserver and daemon."""

import dagster as dg
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
    )
    | dg.AssetSelection.groups("transform"),
)

training_job = dg.define_asset_job("training_job", selection=[qp_assets.champion_model])

# Catch-up bounds: how far back to look for skipped sessions, and how many to request
# per sensor tick (so a long sleep doesn't stampede the queue).
LOOKBACK_DAYS = 30
MAX_CATCHUP_PER_TICK = 3

# All schedules default to RUNNING: `make up` must mean fully automated —
# without this, Dagster ships schedules stopped until toggled in the UI.

# Evenings after the NYSE close: ingest today's bars (non-trading days no-op)...
ingest_schedule = dg.build_schedule_from_partitioned_job(
    ingest_job,
    hour_of_day=18,
    minute_of_hour=30,
    name="daily_ingest_schedule",
    default_status=dg.DefaultScheduleStatus.RUNNING,
)

# ...then run features -> predictions -> portfolio -> drift half an hour later.
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

    today = dt.date.today()
    recent = trading_days(today - dt.timedelta(days=LOOKBACK_DAYS), today)
    missing = missing_trading_days(recent)[:MAX_CATCHUP_PER_TICK]
    if not missing:
        return dg.SensorResult(skip_reason="no missed trading days in the lookback window")
    return dg.SensorResult(
        run_requests=[
            dg.RunRequest(partition_key=str(day), run_key=f"catchup-{day}") for day in missing
        ]
    )


defs = dg.Definitions(
    assets=[
        qp_assets.raw_prices,
        qp_assets.features,
        qp_assets.predictions,
        qp_assets.portfolio_equity,
        qp_assets.drift_report,
        qp_assets.option_chains,
        qp_assets.champion_model,
        transform_dbt_assets,
    ],
    asset_checks=[qp_assets.recent_prices_quality, qp_assets.option_snapshot_quality],
    jobs=[ingest_job, process_job, training_job],
    schedules=[ingest_schedule, process_schedule, training_schedule],
    sensors=[drift_retrain_sensor, pipeline_failure_alert, missed_partition_catchup_sensor],
    resources={"dbt": dbt_resource},
)
