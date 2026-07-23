"""Dagster assets wrapping the quantpulse library. Assets stay thin: all logic
lives in importable, unit-tested modules."""

import datetime as dt

import dagster as dg
from quantpulse.config import get_settings
from quantpulse.data.calendar import (
    EXCHANGES,
    is_trading_day,
    last_trading_day,
    trading_days,
)
from quantpulse.db import get_engine, get_session

daily_partitions = dg.DailyPartitionsDefinition(
    # The date dimension stays on NY time for continuity with existing keys. It only
    # decides when a calendar date becomes current, and every supported market closes
    # before NY midnight, so each exchange's session is available within its own date.
    start_date="2023-01-01",
    timezone="America/New_York",
    end_offset=1,
)
exchange_partitions = dg.StaticPartitionsDefinition(sorted(EXCHANGES))

#: (date, exchange) — a JSE holiday is not an NYSE holiday, and each market needs its own
#: post-close schedule, so exchange has to be a partition dimension rather than a loop.
market_partitions = dg.MultiPartitionsDefinition(
    {"date": daily_partitions, "exchange": exchange_partitions}
)

RETRY_POLICY = dg.RetryPolicy(max_retries=2, delay=60)

# Features are recomputed daily; predictions should follow within a session or two. A
# larger gap means scoring is silently writing nothing.
MAX_PREDICTION_LAG_DAYS = 4


def partition_date_and_exchange(context: dg.AssetExecutionContext) -> tuple[dt.date, str]:
    """Unpack a (date, exchange) partition key."""
    keys = context.partition_key.keys_by_dimension
    return dt.date.fromisoformat(keys["date"]), keys["exchange"]


@dg.asset(
    partitions_def=market_partitions,
    retry_policy=RETRY_POLICY,
    group_name="market_data",
    kinds={"python", "postgres"},
)
def raw_prices(context: dg.AssetExecutionContext) -> dg.MaterializeResult:
    """Daily OHLCV bars for one market's active universe (yfinance, Stooq fallback)."""
    from quantpulse.data.ingest import fetch_daily_bars, upsert_prices
    from quantpulse.data.universe import active_tickers

    day, exchange = partition_date_and_exchange(context)
    if not is_trading_day(day, exchange):
        return dg.MaterializeResult(
            metadata={"rows": 0, "note": f"not a {exchange} trading day", "exchange": exchange}
        )
    with get_session() as session:
        tickers = active_tickers(session, exchange)
    if not tickers:
        # Another market being configured is not an error for this one.
        return dg.MaterializeResult(
            metadata={"rows": 0, "note": f"no active {exchange} tickers", "exchange": exchange}
        )
    bars = fetch_daily_bars(tickers, day, day)
    with get_session() as session:
        rows = upsert_prices(session, bars)
    return dg.MaterializeResult(
        metadata={
            "rows": rows,
            "tickers": len(bars["ticker"].unique()) if not bars.empty else 0,
            "date": str(day),
            "exchange": exchange,
        }
    )


@dg.asset_check(asset=raw_prices, blocking=False)
def recent_prices_quality() -> dg.AssetCheckResult:
    """Data-quality gate over the trailing 30 trading days of stored bars."""
    import pandas as pd

    from quantpulse.data.quality import failed_checks, run_quality_checks
    from quantpulse.data.universe import active_tickers

    metadata: dict[str, dg.MetadataValue] = {}
    any_failed = False
    for exchange in sorted(EXCHANGES):
        with get_session() as session:
            tickers = active_tickers(session, exchange)
        if not tickers:
            continue  # market not configured yet; nothing to judge
        end = last_trading_day(exchange=exchange)
        days = trading_days(end - dt.timedelta(days=45), end, exchange)[-30:]
        bars = pd.read_sql(
            "SELECT p.ticker, p.date, p.open, p.high, p.low, p.close, p.volume FROM prices p "
            "JOIN universe u ON u.ticker = p.ticker AND u.exchange = %(ex)s "
            "WHERE p.date >= %(start)s",
            get_engine(),
            params={"start": days[0].isoformat(), "ex": exchange},
        )
        results = run_quality_checks(bars, days, tickers)
        any_failed = any_failed or bool(failed_checks(results))
        for r in results:
            metadata[f"{exchange}/{r.name}"] = dg.MetadataValue.json(
                {"passed": bool(r.passed), **r.details}
            )
    return dg.AssetCheckResult(passed=not any_failed, metadata=metadata)


@dg.asset(deps=[raw_prices], group_name="features", kinds={"python", "postgres"})
def features() -> dg.MaterializeResult:
    """Engineered feature rows recomputed over the full stored history."""
    from quantpulse.features.engineering import FEATURE_VERSION, compute_features
    from quantpulse.features.store import load_price_bars, store_features

    # load_price_bars carries `exchange`, and compute_features ranks cross-sectionally
    # within it — one call covers every market without mixing their cross-sections.
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
    """Champion-model scores for the latest feature date, per market."""
    from quantpulse.ml.pipeline import score_latest

    settings = get_settings()
    per_exchange = {}
    for exchange in sorted(EXCHANGES):
        with get_session() as session:
            per_exchange[exchange] = score_latest(
                get_engine(),
                session,
                tracking_uri=settings.mlflow_tracking_uri,
                exchange=exchange,
            )
    return dg.MaterializeResult(
        metadata={
            "rows": sum(per_exchange.values()),
            **{f"rows_{k}": v for k, v in per_exchange.items()},
            "note": "0 rows means that market has no champion model yet",
        }
    )


@dg.asset_check(asset=predictions, blocking=False)
def predictions_are_current() -> dg.AssetCheckResult:
    """Catch a market whose predictions have quietly stopped updating.

    A market can have data, features and a universe yet no champion — the registry name
    changed, or a candidate failed the promotion gate. Scoring then writes nothing while
    the dashboard keeps serving yesterday's predictions as if they were today's. That is
    the worst kind of failure here: nothing errors, the numbers just stop moving.
    """
    import pandas as pd

    from quantpulse.data.universe import active_tickers

    rows = pd.read_sql(
        "SELECT u.exchange, max(p.date) AS latest_prediction, "
        "(SELECT max(f.date) FROM features f JOIN universe fu ON fu.ticker = f.ticker "
        " AND fu.exchange = u.exchange) AS latest_feature "
        "FROM predictions p JOIN universe u ON u.ticker = p.ticker GROUP BY u.exchange",
        get_engine(),
    )
    metadata: dict[str, dg.MetadataValue] = {}
    stale = []
    with get_session() as session:
        configured = {e for e in sorted(EXCHANGES) if active_tickers(session, e)}
    seen = set(rows["exchange"]) if not rows.empty else set()
    for exchange in sorted(configured):
        if exchange not in seen:
            stale.append(f"{exchange}: no predictions at all")
            continue
        row = rows[rows["exchange"] == exchange].iloc[0]
        lag = (row["latest_feature"] - row["latest_prediction"]).days
        metadata[f"{exchange}/lag_days"] = dg.MetadataValue.int(int(lag))
        if lag > MAX_PREDICTION_LAG_DAYS:
            stale.append(
                f"{exchange}: predictions {lag}d behind features "
                f"({row['latest_prediction']} vs {row['latest_feature']}) — likely no champion"
            )
    return dg.AssetCheckResult(
        passed=not stale,
        metadata={**metadata, **({"stale": dg.MetadataValue.json(stale)} if stale else {})},
    )


@dg.asset(deps=[predictions], group_name="serving", kinds={"python", "postgres"})
def portfolio_equity() -> dg.MaterializeResult:
    """Simulated paper books rebuilt from the prediction trail, per market."""
    from quantpulse.ml.portfolio import rebuild_portfolio

    per_exchange = {}
    for exchange in sorted(EXCHANGES):
        with get_session() as session:
            per_exchange[exchange] = rebuild_portfolio(get_engine(), session, exchange=exchange)
    return dg.MaterializeResult(
        metadata={
            "snapshots": sum(per_exchange.values()),
            **{f"snapshots_{k}": v for k, v in per_exchange.items()},
        }
    )


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
    grows our own options dataset going forward.

    Only markets with `has_options` are snapshotted: no free JSE chain data exists from
    any vendor we can use, so this stays a US-only layer by necessity.
    """
    from quantpulse.data.universe import active_tickers
    from quantpulse.options.ingest import snapshot_option_chains

    tickers: list[str] = []
    with get_session() as session:
        for code, ex in sorted(EXCHANGES.items()):
            if ex.has_options:
                tickers.extend(active_tickers(session, code))
    if not tickers:
        return dg.MaterializeResult(metadata={"quotes": 0, "note": "no options-bearing market"})
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
        n_tickers = sum(
            len(active_tickers(session, code)) for code, ex in EXCHANGES.items() if ex.has_options
        )
    if not n_tickers:
        return dg.AssetCheckResult(passed=True, metadata={"note": "no options-bearing market"})
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
    """Train a challenger per market, evaluate on holdout backtest, promote if it wins.

    One champion per exchange: different sessions, currencies and dynamics, and pooling
    them would muddle attribution for no gain in data we are short of.
    """
    from quantpulse.data.universe import active_tickers
    from quantpulse.ml.pipeline import train_evaluate_promote

    settings = get_settings()
    metadata: dict[str, dg.MetadataValue] = {}
    for exchange in sorted(EXCHANGES):
        with get_session() as session:
            if not active_tickers(session, exchange):
                continue  # market not configured yet
            summary = train_evaluate_promote(
                get_engine(),
                session,
                tracking_uri=settings.mlflow_tracking_uri,
                exchange=exchange,
            )
        for key, value in summary.items():
            metadata[f"{exchange}/{key}"] = dg.MetadataValue.text(str(value))
    if not metadata:
        raise ValueError("No configured market has tickers — run `quantpulse sync-universe`")
    return dg.MaterializeResult(metadata=metadata)
