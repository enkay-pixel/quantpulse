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
        "champion_model",
    }
    dbt_models = {
        "stg_prices",
        "stg_predictions",
        "fct_daily_returns",
        "fct_signal_performance",
        "fct_portfolio_daily",
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
    assert {"daily_ingest_schedule", "daily_process_schedule", "weekly_training_schedule"} <= (
        schedule_names
    )
    sensor_names = {s.name for s in defs.sensors or []}
    assert "drift_retrain_sensor" in sensor_names


def test_raw_prices_is_daily_partitioned() -> None:
    job = defs.resolve_job_def("ingest_job")
    assert isinstance(job.partitions_def, dg.DailyPartitionsDefinition)
    assert job.partitions_def.timezone == "America/New_York"
