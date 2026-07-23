"""Operational CLI: `quantpulse <command>`. Thin wrappers over the library modules."""

import argparse
import datetime as dt
import logging
import math
import sys
from pathlib import Path

from quantpulse.config import get_settings

logger = logging.getLogger("quantpulse")

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _alembic_upgrade() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    command.upgrade(cfg, "head")
    logger.info("Database migrated to head")


def _sync_universe() -> None:
    from quantpulse.data.universe import load_universe, sync_universe
    from quantpulse.db import get_session

    settings = get_settings()
    path = settings.quantpulse_universe_file
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    entries = load_universe(path)
    with get_session() as session:
        counts = sync_universe(session, entries)
    logger.info("Universe synced: %s (%d configured)", counts, len(entries))


def _backfill(
    start: dt.date | None,
    end: dt.date | None,
    exchange: str | None = None,
    batch_size: int = 25,
) -> None:
    from quantpulse.data.calendar import get_exchange, last_trading_day
    from quantpulse.data.ingest import fetch_daily_bars, upsert_prices
    from quantpulse.data.universe import active_tickers
    from quantpulse.db import get_session

    settings = get_settings()
    code = get_exchange(exchange).code if exchange else None
    start = start or dt.date.fromisoformat(settings.quantpulse_history_start)
    # The end date follows the requested market's own calendar.
    end = end or last_trading_day(exchange=code)
    with get_session() as session:
        tickers = active_tickers(session, code)
    if not tickers:
        target = code or "any market"
        logger.error("No active tickers for %s — run `quantpulse sync-universe` first", target)
        sys.exit(1)
    logger.info(
        "Backfilling %d %s tickers from %s to %s", len(tickers), code or "all-market", start, end
    )
    total = 0
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        bars = fetch_daily_bars(batch, start, end)
        with get_session() as session:
            written = upsert_prices(session, bars)
        total += written
        logger.info("Batch %s..%s: wrote %d rows", batch[0], batch[-1], written)
    logger.info("Backfill complete: %d rows", total)


def _features() -> None:
    from quantpulse.db import get_engine, get_session
    from quantpulse.features.engineering import FEATURE_VERSION, compute_features
    from quantpulse.features.store import load_price_bars, store_features

    bars = load_price_bars(get_engine())
    if bars.empty:
        logger.error("No price bars stored — run `quantpulse backfill` first")
        sys.exit(1)
    features = compute_features(bars)
    with get_session() as session:
        written = store_features(session, features, FEATURE_VERSION)
    logger.info("Stored %d feature rows (version %s)", written, FEATURE_VERSION)


def _train() -> None:
    from quantpulse.db import get_engine, get_session
    from quantpulse.ml.pipeline import train_evaluate_promote

    settings = get_settings()
    with get_session() as session:
        summary = train_evaluate_promote(
            get_engine(), session, tracking_uri=settings.mlflow_tracking_uri
        )
    for key, value in summary.items():
        logger.info("%-24s %s", key, value)


def _score(replay: bool, exchange: str | None = None) -> None:
    from quantpulse.data.calendar import EXCHANGES, get_exchange
    from quantpulse.db import get_engine, get_session
    from quantpulse.ml.pipeline import score_latest
    from quantpulse.ml.portfolio import rebuild_portfolio, score_history

    settings = get_settings()
    codes = [get_exchange(exchange).code] if exchange else sorted(EXCHANGES)
    total = 0
    for code in codes:
        if replay:
            with get_session() as session:
                total += score_history(
                    get_engine(), session, tracking_uri=settings.mlflow_tracking_uri, exchange=code
                )
            # Separate transaction: the rebuild reads predictions through its own connection.
            with get_session() as session:
                rebuild_portfolio(get_engine(), session, exchange=code)
        else:
            with get_session() as session:
                total += score_latest(
                    get_engine(), session, tracking_uri=settings.mlflow_tracking_uri, exchange=code
                )
    logger.info("Wrote %d predictions", total)


def _options_snapshot() -> None:
    from quantpulse.data.universe import active_tickers
    from quantpulse.db import get_session
    from quantpulse.options.ingest import snapshot_option_chains

    with get_session() as session:
        tickers = active_tickers(session)
    if not tickers:
        logger.error("Universe is empty — run `quantpulse sync-universe` first")
        sys.exit(1)
    n = snapshot_option_chains(get_session, tickers)
    logger.info("Wrote %d option quotes", n)


def _sensitivity() -> None:
    """Report how the backtest holds up across trading-cost and borrow assumptions."""
    import pandas as pd

    from quantpulse.db import get_engine
    from quantpulse.ml.sensitivity import breakeven_cost, cost_sensitivity

    panel = pd.read_sql(
        "SELECT p.date, p.ticker, p.score AS pred, f.fwd_ret FROM predictions p JOIN ("
        "  SELECT ticker, date, lead(close, 21) OVER (PARTITION BY ticker ORDER BY date)"
        "   / close - 1 AS fwd_ret FROM prices"
        ") f ON f.ticker = p.ticker AND f.date = p.date WHERE f.fwd_ret IS NOT NULL",
        get_engine(),
    )
    if panel.empty:
        logger.error("No scored panel available — run `quantpulse score --replay` first")
        sys.exit(1)

    rows = cost_sensitivity(panel)
    logger.info(
        "%-12s %-10s %-12s %-8s %-10s", "round-trip", "borrow", "annual ret", "sharpe", "max dd"
    )
    for r in rows:
        logger.info(
            "%-12.2f%% %-9.1f%% %-11.2f%% %-8.2f %-9.2f%%",
            r.round_trip_cost * 100,
            r.borrow_rate * 100,
            r.annual_return * 100,
            r.sharpe,
            r.max_drawdown * 100,
        )
    be = breakeven_cost(rows)
    ceiling = max(r.round_trip_cost for r in rows)
    if be is None:
        summary = "never profitable — no edge to erode"
    elif math.isinf(be):
        summary = f"above {ceiling * 100:.2f}% — still profitable at the harshest cost tested"
    else:
        summary = f"{be * 100:.2f}%"
    logger.info("Breakeven round-trip cost (no borrow): %s", summary)


def _quality(start: dt.date, end: dt.date) -> None:
    import pandas as pd

    from quantpulse.data.calendar import trading_days
    from quantpulse.data.quality import failed_checks, run_quality_checks
    from quantpulse.data.universe import active_tickers
    from quantpulse.db import get_engine, get_session

    with get_session() as session:
        tickers = active_tickers(session)
    bars = pd.read_sql(
        "SELECT ticker, date, open, high, low, close, volume FROM prices "
        "WHERE date BETWEEN %(start)s AND %(end)s",
        get_engine(),
        params={"start": start, "end": end},
    )
    results = run_quality_checks(bars, trading_days(start, end), tickers)
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        logger.info("%-18s %s %s", r.name, status, r.details or "")
    if failed_checks(results):
        sys.exit(1)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(prog="quantpulse")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="Run Alembic migrations to head")
    sub.add_parser("sync-universe", help="Sync configs/universe.yaml into the database")

    backfill = sub.add_parser("backfill", help="Fetch and upsert daily bars for the universe")
    backfill.add_argument("--start", type=dt.date.fromisoformat, default=None)
    backfill.add_argument("--end", type=dt.date.fromisoformat, default=None)
    backfill.add_argument("--exchange", default=None, help="Limit to one market, e.g. XJSE")

    quality = sub.add_parser("quality", help="Run data-quality checks on stored prices")
    quality.add_argument("--start", type=dt.date.fromisoformat, required=True)
    quality.add_argument("--end", type=dt.date.fromisoformat, required=True)

    sub.add_parser("features", help="Compute and store features from ingested bars")
    sub.add_parser("options-snapshot", help="Snapshot live option chains for the universe")
    sub.add_parser("sensitivity", help="Backtest sensitivity to trading cost and borrow rate")
    sub.add_parser("train", help="Train, evaluate, and maybe promote a model")
    score = sub.add_parser("score", help="Score features with the champion model")
    score.add_argument(
        "--replay",
        action="store_true",
        help="Score the full feature history (pre-champion dates are an in-sample replay)",
    )
    score.add_argument("--exchange", default=None, help="Limit to one market, e.g. XJSE")

    args = parser.parse_args(argv)
    if args.command == "init-db":
        _alembic_upgrade()
    elif args.command == "sync-universe":
        _sync_universe()
    elif args.command == "backfill":
        _backfill(args.start, args.end, args.exchange)
    elif args.command == "quality":
        _quality(args.start, args.end)
    elif args.command == "features":
        _features()
    elif args.command == "options-snapshot":
        _options_snapshot()
    elif args.command == "sensitivity":
        _sensitivity()
    elif args.command == "train":
        _train()
    elif args.command == "score":
        _score(args.replay, args.exchange)


if __name__ == "__main__":
    main()
