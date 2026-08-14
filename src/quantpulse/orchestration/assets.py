"""Dagster assets wrapping the quantpulse library. Assets stay thin: all logic
lives in importable, unit-tested modules.

An asset body should read as "fetch the inputs, call the library, report metadata".
Anything more cannot be tested without standing up Dagster, which a unit test should never
need.

**Why the imports sit inside the asset bodies.** Dagster imports this module to build the
asset graph — on every daemon reload, in the webserver, and in each run process — but the
graph needs only the decorators, not lightgbm or mlflow. Importing `definitions` already
costs ~4.75s; hoisting the ML stack to module scope would add ~4s to work that happens
constantly and mostly does not execute an asset at all. Same convention, same reason, in
`definitions.py` and `cli.py`.
"""

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

#: Trailing sessions the benchmark freshness check judges. Long enough that a late-arriving
#: bar (JSE bars can land 2+ days after the session) still gets reported while it is
#: recoverable, short enough that one historical hole does not alarm forever.
BENCHMARK_LOOKBACK_SESSIONS = 30

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


@dg.asset_check(asset=raw_prices, blocking=False)
def benchmark_freshness() -> dg.AssetCheckResult:
    """Every session a market ingested must also have a bar for that market's benchmark.

    Separate from `recent_prices_quality` because a benchmark hole is invisible there: the
    catch-up sensor's coverage floor is a *share* of the universe, so 28 of 29 JSE names
    clears 0.8 comfortably and never retries, and the per-ticker completeness ratio gives a
    single absent day 0.967 against a 0.95 threshold. Both correctly ignore one missing
    ticker. But when that ticker is the benchmark, the inner joins in `fct_alpha_beta` and
    `fct_portfolio_vs_benchmark` drop the entire day from the CAPM decomposition, so the
    gap only shows up as two marts quietly disagreeing about the live day count.

    Non-blocking on purpose: a stale benchmark makes the alpha numbers thinner, not wrong,
    and must not stop the ingest.
    """
    from sqlalchemy import text

    from quantpulse.data.calendar import get_exchange
    from quantpulse.data.quality import benchmark_gaps

    metadata: dict[str, dg.MetadataValue] = {}
    any_failed = False
    with get_engine().connect() as conn:
        for exchange in sorted(EXCHANGES):
            benchmark = get_exchange(exchange).benchmark
            end = last_trading_day(exchange=exchange)
            window_start = end - dt.timedelta(days=45)
            # Sessions this market actually has data for — not the calendar. A day nobody
            # ingested is an outage the catch-up sensor owns; flagging it here as well
            # would fire two alarms for one cause.
            sessions = [
                row.date
                for row in conn.execute(
                    text(
                        "SELECT p.date FROM prices p "
                        "JOIN universe u ON u.ticker = p.ticker AND u.exchange = :ex "
                        "WHERE p.date >= :start GROUP BY p.date ORDER BY p.date"
                    ),
                    {"start": window_start, "ex": exchange},
                ).all()
            ][-BENCHMARK_LOOKBACK_SESSIONS:]
            if not sessions:
                continue  # market not ingesting yet; nothing to judge
            bars = conn.execute(
                text("SELECT date FROM prices WHERE ticker = :t AND date >= :start"),
                {"t": benchmark, "start": window_start},
            ).all()
            in_universe = (
                conn.execute(
                    text("SELECT count(*) FROM universe WHERE ticker = :t AND active"),
                    {"t": benchmark},
                ).scalar_one()
                > 0
            )
            result = benchmark_gaps(benchmark, sessions, [r.date for r in bars], in_universe)
            any_failed = any_failed or not result.passed
            metadata[exchange] = dg.MetadataValue.json(
                {"passed": bool(result.passed), **result.details}
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
    """Catch a market whose predictions have quietly stopped updating, or skipped a day.

    A market can have data, features and a universe yet no champion — the registry name
    changed, or a candidate failed the promotion gate. Scoring then writes nothing while
    the dashboard keeps serving yesterday's predictions as if they were today's. That is
    the worst kind of failure here: nothing errors, the numbers just stop moving.

    Lag alone is not enough. Comparing only the two *maxima* is blind to a hole in the
    middle: when a session goes unscored, the next night's run pushes both maxima forward
    and the check passes while the live track record is quietly a day short. So gaps are
    counted too — any feature date inside the scoring window with
    no predictions at all.
    """
    import pandas as pd

    from quantpulse.data.universe import active_tickers
    from quantpulse.ml.pipeline import SCORING_LOOKBACK_DAYS

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
        gaps = _unscored_dates(exchange, row["latest_feature"], SCORING_LOOKBACK_DAYS)
        metadata[f"{exchange}/unscored_days"] = dg.MetadataValue.int(len(gaps))
        if gaps:
            stale.append(f"{exchange}: {len(gaps)} feature date(s) never scored: {gaps[:5]}")
    return dg.AssetCheckResult(
        passed=not stale,
        metadata={**metadata, **({"stale": dg.MetadataValue.json(stale)} if stale else {})},
    )


def _unscored_dates(exchange: str, latest_feature: dt.date, lookback: int) -> list[str]:
    """Feature dates in the scoring window that have no predictions at all."""
    from sqlalchemy import text

    from quantpulse.ml.pipeline import dates_with_predictions

    window_start = latest_feature - dt.timedelta(days=lookback)
    with get_engine().connect() as conn:
        feature_dates = {
            r.date
            for r in conn.execute(
                text(
                    "SELECT DISTINCT f.date FROM features f "
                    "JOIN universe u ON u.ticker = f.ticker AND u.exchange = :ex "
                    "WHERE f.date >= :since"
                ),
                {"ex": exchange, "since": window_start},
            ).all()
        }
    scored = dates_with_predictions(get_engine(), exchange, window_start)
    return [str(d) for d in sorted(feature_dates - scored)]


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
    """KS/PSI feature drift vs. reference history, per market; feeds the retraining sensor.

    Per market rather than pooled: a mixture of two markets' feature distributions is a
    description of neither, and it halved the measured signal (see `monitoring.drift`).
    """
    from quantpulse.data.universe import active_tickers
    from quantpulse.monitoring.drift import run_drift_check

    metadata: dict[str, dg.MetadataValue] = {}
    for exchange in sorted(EXCHANGES):
        with get_session() as session:
            if not active_tickers(session, exchange):
                continue  # market not configured yet
            report = run_drift_check(get_engine(), session, exchange=exchange)
        metadata[f"{exchange}/share_drifted"] = dg.MetadataValue.float(report.share_drifted)
        metadata[f"{exchange}/drifted"] = dg.MetadataValue.bool(report.drifted)
        metadata[f"{exchange}/n_features"] = dg.MetadataValue.int(len(report.features))
    if not metadata:
        raise ValueError("No configured market has tickers — run `quantpulse sync-universe`")
    return dg.MaterializeResult(metadata=metadata)


@dg.asset(deps=[raw_prices], group_name="options", kinds={"python", "postgres"})
def option_chains() -> dg.MaterializeResult:
    """Snapshot live option chains + Greeks. No free history exists, so each run
    grows our own options dataset going forward.

    Only markets with `has_options` are snapshotted: no free JSE chain data exists from
    any vendor we can use, so this stays a US-only layer by necessity.
    """
    from quantpulse.data.universe import options_tickers
    from quantpulse.options.ingest import snapshot_option_chains

    with get_session() as session:
        tickers = options_tickers(session)
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
    from quantpulse.data.universe import options_tickers
    from quantpulse.options.quality import run_option_quality_checks

    with get_session() as session:
        # Must match what the asset snapshots, or coverage is scored against the wrong
        # denominator.
        n_tickers = len(options_tickers(session))
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
def champion_model(context: dg.AssetExecutionContext) -> dg.MaterializeResult:
    """Train a challenger per market, evaluate on holdout backtest, promote if it wins.

    One champion per exchange: different sessions, currencies and dynamics, and pooling
    them would muddle attribution for no gain in data we are short of.

    Scoped by the run's `exchange` tag when one is set. The drift sensor measures and fires
    per market, so without this a drift reading on one market would retrain the other too —
    retraining on evidence about neither. An untagged run, such as the weekly schedule,
    still covers every market.
    """
    from quantpulse.data.universe import active_tickers
    from quantpulse.ml.pipeline import train_evaluate_promote

    settings = get_settings()
    metadata: dict[str, dg.MetadataValue] = {}
    targeted = context.run.tags.get("exchange")
    if targeted and targeted not in EXCHANGES:
        # Fail rather than silently widening to every market: a typo'd or renamed code
        # would otherwise read as a routine full retrain and cost two Optuna budgets.
        raise ValueError(f"run tagged for unknown exchange {targeted!r}")
    selected = [targeted] if targeted else sorted(EXCHANGES)
    context.log.info("Retraining %s", selected)
    for exchange in selected:
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


@dg.asset_check(asset=champion_model, blocking=False)
def champion_registry_agrees() -> dg.AssetCheckResult:
    """MLflow's `@champion` alias must name the same version the audit trail does.

    Two systems record which model is champion, and they are updated separately. MLflow's
    alias decides what `load_champion` deserializes and therefore what actually scores;
    `model_runs` decides what the dashboard reports and what `fct_portfolio_daily` uses to
    date the `backfilled` boundary. Nothing spans both writes: `train_evaluate_promote`
    sets the alias first and commits the audit row after, so a failure between them leaves
    MLflow promoted and Postgres silent — the dashboard would keep naming the old champion
    while the new one wrote every prediction, and every number on screen would be attributed
    to a model that did not produce it.

    Reports, never repairs. Choosing which of two disagreeing records is right means
    knowing whether the promotion was intended, and that is not a decision to automate on a
    registry the scoring pipeline deserializes.
    """
    from quantpulse.data.universe import active_tickers
    from quantpulse.ml import registry
    from quantpulse.ml.promotion import audit_champion

    settings = get_settings()
    registry.configure(settings.mlflow_tracking_uri)

    metadata: dict[str, dg.MetadataValue] = {}
    disagreements = []
    for exchange in sorted(EXCHANGES):
        with get_session() as session:
            if not active_tickers(session, exchange):
                continue  # market not configured yet
            audited = audit_champion(session, exchange)
            # Read inside the session: the ORM expires attributes on commit, so touching
            # this after the block raises DetachedInstanceError.
            audit_version = audited.model_version if audited else None
        try:
            live = registry.get_champion(exchange=exchange)
            alias_version = live.version if live else None
        except Exception as exc:  # registry unreachable is itself worth reporting
            metadata[exchange] = dg.MetadataValue.json({"error": f"{type(exc).__name__}: {exc}"})
            disagreements.append(f"{exchange}: registry unreachable")
            continue
        agrees = str(audit_version) == str(alias_version)
        metadata[exchange] = dg.MetadataValue.json(
            {"audit_trail": audit_version, "mlflow_alias": alias_version, "agrees": agrees}
        )
        if not agrees:
            disagreements.append(
                f"{exchange}: audit says v{audit_version}, MLflow @champion is v{alias_version}"
            )
    if disagreements:
        metadata["disagreements"] = dg.MetadataValue.text("; ".join(disagreements))
    return dg.AssetCheckResult(passed=not disagreements, metadata=metadata)
