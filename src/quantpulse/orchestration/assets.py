"""Dagster assets wrapping the quantpulse library. Assets stay thin: all logic
lives in importable, unit-tested modules."""

import datetime as dt

import dagster as dg
from quantpulse.config import get_settings
from quantpulse.data.calendar import is_trading_day, last_trading_day, trading_days
from quantpulse.db import get_engine, get_session

daily_partitions = dg.DailyPartitionsDefinition(
    start_date="2023-01-01", timezone="America/New_York", end_offset=1
)

RETRY_POLICY = dg.RetryPolicy(max_retries=2, delay=60)


@dg.asset(
    partitions_def=daily_partitions,
    retry_policy=RETRY_POLICY,
    group_name="market_data",
    kinds={"python", "postgres"},
)
def raw_prices(context: dg.AssetExecutionContext) -> dg.MaterializeResult:
    """Daily OHLCV bars for the active universe (yfinance, Stooq fallback)."""
    from quantpulse.data.ingest import fetch_daily_bars, upsert_prices
    from quantpulse.data.universe import active_tickers

    day = dt.date.fromisoformat(context.partition_key)
    if not is_trading_day(day):
        return dg.MaterializeResult(metadata={"rows": 0, "note": "non-trading day"})
    with get_session() as session:
        tickers = active_tickers(session)
    if not tickers:
        raise ValueError("Universe is empty — run `quantpulse sync-universe`")
    bars = fetch_daily_bars(tickers, day, day)
    with get_session() as session:
        rows = upsert_prices(session, bars)
    return dg.MaterializeResult(
        metadata={"rows": rows, "tickers": len(bars["ticker"].unique()), "date": str(day)}
    )


@dg.asset_check(asset=raw_prices, blocking=False)
def recent_prices_quality() -> dg.AssetCheckResult:
    """Data-quality gate over the trailing 30 trading days of stored bars."""
    import pandas as pd

    from quantpulse.data.quality import failed_checks, run_quality_checks
    from quantpulse.data.universe import active_tickers

    end = last_trading_day()
    days = trading_days(end - dt.timedelta(days=45), end)[-30:]
    with get_session() as session:
        tickers = active_tickers(session)
    bars = pd.read_sql(
        "SELECT ticker, date, open, high, low, close, volume FROM prices WHERE date >= %(start)s",
        get_engine(),
        params={"start": days[0]},
    )
    results = run_quality_checks(bars, days, tickers)
    failed = failed_checks(results)
    return dg.AssetCheckResult(
        passed=not failed,
        metadata={
            r.name: dg.MetadataValue.json({"passed": bool(r.passed), **r.details}) for r in results
        },
    )


@dg.asset(deps=[raw_prices], group_name="features", kinds={"python", "postgres"})
def features() -> dg.MaterializeResult:
    """Engineered feature rows recomputed over the full stored history."""
    from quantpulse.features.engineering import FEATURE_VERSION, compute_features
    from quantpulse.features.store import load_price_bars, store_features

    bars = load_price_bars(get_engine())
    if bars.empty:
        raise ValueError("No price bars stored")
    frame = compute_features(bars)
    with get_session() as session:
        rows = store_features(session, frame, FEATURE_VERSION)
    return dg.MaterializeResult(
        metadata={"rows": rows, "latest_date": str(frame["date"].max()), "version": FEATURE_VERSION}
    )


@dg.asset(deps=[features], group_name="serving", kinds={"python", "mlflow"})
def predictions() -> dg.MaterializeResult:
    """Champion-model scores for the latest feature date."""
    from quantpulse.ml.pipeline import score_latest

    settings = get_settings()
    with get_session() as session:
        rows = score_latest(get_engine(), session, tracking_uri=settings.mlflow_tracking_uri)
    return dg.MaterializeResult(
        metadata={"rows": rows, "note": "0 rows means no champion model yet"}
    )


@dg.asset(deps=[predictions], group_name="serving", kinds={"python", "postgres"})
def portfolio_equity() -> dg.MaterializeResult:
    """Simulated long/short paper book rebuilt from the prediction trail."""
    from quantpulse.ml.portfolio import rebuild_portfolio

    with get_session() as session:
        rows = rebuild_portfolio(get_engine(), session)
    return dg.MaterializeResult(metadata={"snapshots": rows})


@dg.asset(deps=[features], group_name="monitoring", kinds={"python"})
def drift_report() -> dg.MaterializeResult:
    """KS/PSI feature drift vs. reference history; feeds the retraining sensor."""
    from quantpulse.monitoring.drift import run_drift_check

    with get_session() as session:
        report = run_drift_check(get_engine(), session)
    return dg.MaterializeResult(
        metadata={
            "share_drifted": report.share_drifted,
            "drifted": report.drifted,
            "n_features": len(report.features),
        }
    )


@dg.asset(deps=[raw_prices], group_name="options", kinds={"python", "postgres"})
def option_chains() -> dg.MaterializeResult:
    """Snapshot live option chains + Greeks. No free history exists, so each run
    grows our own options dataset going forward."""
    from quantpulse.data.universe import active_tickers
    from quantpulse.options.ingest import snapshot_option_chains

    with get_session() as session:
        tickers = active_tickers(session)
    rows = snapshot_option_chains(get_session, tickers)  # commits per ticker
    return dg.MaterializeResult(metadata={"quotes": rows, "tickers": len(tickers)})


@dg.asset_check(asset=option_chains, blocking=False)
def option_snapshot_quality() -> dg.AssetCheckResult:
    """Guard the options dataset: coverage, plausible IV (catches stale/pre-market
    snapshots), traded contracts present, and no missing Greeks."""
    import pandas as pd

    from quantpulse.data.quality import failed_checks
    from quantpulse.data.universe import active_tickers
    from quantpulse.options.quality import run_option_quality_checks

    with get_session() as session:
        n_tickers = len(active_tickers(session))
    quotes = pd.read_sql(
        "SELECT ticker, implied_volatility, open_interest, delta, gamma, theta, vega, "
        "theo_value FROM option_quotes WHERE snapshot_date = "
        "(SELECT max(snapshot_date) FROM option_quotes)",
        get_engine(),
    )
    results = run_option_quality_checks(quotes, n_tickers)
    return dg.AssetCheckResult(
        passed=not failed_checks(results),
        metadata={
            r.name: dg.MetadataValue.json({"passed": bool(r.passed), **r.details}) for r in results
        },
    )


@dg.asset(group_name="monitoring", kinds={"python", "postgres"})
def resource_report() -> dg.MaterializeResult:
    """Database growth and memory headroom, expressed as runway rather than raw bytes.

    Materialization metadata is the storage: Dagster charts numeric metadata over time, so
    the trend is visible without a new table, a new container, or a metrics stack.

    The memory figure is the **run process's** RSS against the container cap, not the
    daemon's idle footprint — runs execute in-process under the launcher. That is the more
    useful of the two: it measures the process that could actually exhaust the cap, which
    on a Saturday is the Optuna/LightGBM retrain.
    """
    from quantpulse.monitoring.resources import check_headroom, collect_resource_report

    report = collect_resource_report(get_engine())
    breaches = check_headroom(report)
    gb = 1024**3
    metadata: dict[str, float | int | str] = {
        f"db_{name}_mb": round(size / 1024**2, 1) for name, size in report.database_bytes.items()
    }
    metadata["total_gb"] = round(sum(report.database_bytes.values()) / gb, 3)
    if report.bytes_per_day:
        metadata["growth_mb_per_day"] = round(report.bytes_per_day / 1024**2, 2)
    if report.runway_days is not None:
        metadata["runway_days"] = round(report.runway_days)
        metadata["runway_years"] = round(report.runway_days / 365, 1)
    if report.memory_fraction is not None:
        metadata["memory_pct_of_cap"] = round(report.memory_fraction * 100, 1)
    metadata["breaches"] = len(breaches)
    for breach in breaches:
        metadata[f"breach_{breach.name}"] = breach.detail
    return dg.MaterializeResult(metadata=metadata)


@dg.asset_check(asset=resource_report, blocking=False)
def resource_headroom() -> dg.AssetCheckResult:
    """Fail when runway or memory headroom drops below its floor.

    Non-blocking on purpose: running low on disk is a reason to be told, not a reason to
    stop collecting the options history that is using the disk.
    """
    from quantpulse.monitoring.resources import check_headroom, collect_resource_report

    breaches = check_headroom(collect_resource_report(get_engine()))
    return dg.AssetCheckResult(
        passed=not breaches,
        metadata={b.name: b.detail for b in breaches} or {"status": "all within limits"},
    )


@dg.asset(group_name="training", kinds={"python", "mlflow"}, op_tags={"compute": "heavy"})
def champion_model() -> dg.MaterializeResult:
    """Train a challenger, evaluate on holdout backtest, promote if it beats the champion."""
    from quantpulse.ml.pipeline import train_evaluate_promote

    settings = get_settings()
    with get_session() as session:
        summary = train_evaluate_promote(
            get_engine(), session, tracking_uri=settings.mlflow_tracking_uri
        )
    return dg.MaterializeResult(
        metadata={k: dg.MetadataValue.text(str(v)) for k, v in summary.items()}
    )
