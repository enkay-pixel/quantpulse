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
