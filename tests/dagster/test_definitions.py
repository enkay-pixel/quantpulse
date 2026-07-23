"""The Definitions module must always load — this is what the webserver/daemon import."""

import dagster as dg
from quantpulse.orchestration.definitions import defs


def test_definitions_load_and_resolve() -> None:
    # Resolving the job/asset graph raises on any wiring error.
    assert defs.resolve_all_job_defs()


def test_expected_assets_present() -> None:
    keys = {spec.key.to_user_string() for spec in defs.resolve_all_asset_specs()}
    core = {
        "raw_prices",
        "features",
        "predictions",
        "portfolio_equity",
        "drift_report",
        "option_chains",
        "champion_model",
    }
    dbt_models = {
        "stg_prices",
        "stg_predictions",
        "stg_option_quotes",
        "fct_daily_returns",
        "fct_signal_performance",
        "fct_portfolio_daily",
        "fct_option_summary",
        "fct_iv_surface",
        "dim_universe",
    }
    assert core <= keys
    assert dbt_models <= keys


def test_dbt_assets_grouped_as_transform() -> None:
    groups = {spec.key.to_user_string(): spec.group_name for spec in defs.resolve_all_asset_specs()}
    assert groups["fct_signal_performance"] == "transform"
    assert groups["stg_prices"] == "transform"


def test_schedules_default_to_running() -> None:
    # `make up` must mean fully automated — schedules may never ship stopped.
    for schedule in defs.schedules or []:
        assert schedule.default_status == dg.DefaultScheduleStatus.RUNNING, schedule.name


def test_schedules_and_sensors_registered() -> None:
    schedule_names = {s.name for s in defs.schedules or []}
    # One ingest schedule per market, each in its own timezone.
    assert {"daily_ingest_xnys", "daily_ingest_xjse"} <= schedule_names
    assert {"daily_process_schedule", "weekly_training_schedule"} <= schedule_names
    sensor_names = {s.name for s in defs.sensors or []}
    assert {
        "drift_retrain_sensor",
        "pipeline_failure_alert",
        "missed_partition_catchup_sensor",
        "option_snapshot_repair_sensor",
    } <= sensor_names


def test_sensors_ship_running() -> None:
    """Same reasoning as the schedules: a sensor that ships stopped is a sensor that
    silently never fires."""
    for sensor in defs.sensors or []:
        assert sensor.default_status == dg.DefaultSensorStatus.RUNNING, sensor.name


def test_raw_prices_is_partitioned_by_date_and_exchange() -> None:
    """Exchange is a partition dimension, not a loop inside the asset: a JSE holiday is
    not an NYSE holiday, and each market needs its own post-close schedule."""
    job = defs.resolve_job_def("ingest_job")
    partitions = job.partitions_def
    assert isinstance(partitions, dg.MultiPartitionsDefinition)
    dims = {d.name: d.partitions_def for d in partitions.partitions_defs}
    assert set(dims) == {"date", "exchange"}
    assert isinstance(dims["date"], dg.DailyPartitionsDefinition)
    assert dims["date"].timezone == "America/New_York"
    assert set(dims["exchange"].get_partition_keys()) == {"XNYS", "XJSE"}


def test_each_market_ingests_in_its_own_timezone() -> None:
    """A single cron cannot serve two closes; the JSE closes five hours before NYSE."""
    by_name = {s.name: s for s in defs.schedules or []}
    assert by_name["daily_ingest_xnys"].execution_timezone == "America/New_York"
    assert by_name["daily_ingest_xjse"].execution_timezone == "Africa/Johannesburg"
    assert by_name["daily_ingest_xnys"].cron_schedule != by_name["daily_ingest_xjse"].cron_schedule
