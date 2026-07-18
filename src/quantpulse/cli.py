"""Operational CLI: `quantpulse <command>`. Thin wrappers over the library modules."""

import argparse
import datetime as dt
import logging
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


def _backfill(start: dt.date | None, end: dt.date | None, batch_size: int = 25) -> None:
    from quantpulse.data.calendar import last_trading_day
    from quantpulse.data.ingest import fetch_daily_bars, upsert_prices
    from quantpulse.data.universe import active_tickers
    from quantpulse.db import get_session

    settings = get_settings()
    start = start or dt.date.fromisoformat(settings.quantpulse_history_start)
    end = end or last_trading_day()
    with get_session() as session:
        tickers = active_tickers(session)
    if not tickers:
        logger.error("Universe is empty — run `quantpulse sync-universe` first")
        sys.exit(1)
    logger.info("Backfilling %d tickers from %s to %s", len(tickers), start, end)
    total = 0
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        bars = fetch_daily_bars(batch, start, end)
        with get_session() as session:
            written = upsert_prices(session, bars)
        total += written
        logger.info("Batch %s..%s: wrote %d rows", batch[0], batch[-1], written)
    logger.info("Backfill complete: %d rows", total)


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

    quality = sub.add_parser("quality", help="Run data-quality checks on stored prices")
    quality.add_argument("--start", type=dt.date.fromisoformat, required=True)
    quality.add_argument("--end", type=dt.date.fromisoformat, required=True)

    args = parser.parse_args(argv)
    if args.command == "init-db":
        _alembic_upgrade()
    elif args.command == "sync-universe":
        _sync_universe()
    elif args.command == "backfill":
        _backfill(args.start, args.end)
    elif args.command == "quality":
        _quality(args.start, args.end)


if __name__ == "__main__":
    main()
