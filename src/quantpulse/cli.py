"""Operational CLI: `quantpulse <command>`. Thin wrappers over the library modules.

Every command is a `_verb()` function doing argument plumbing only; the work lives in
`quantpulse.data`, `.features`, `.ml` and `.options`, where it is importable and unit
tested. If a command grows logic worth testing, that logic belongs in a module and the
command keeps calling it.

**Why the imports sit inside the functions.** Importing lightgbm, mlflow and pandas costs
several seconds. Keeping those imports inside the commands that need them means
`quantpulse --help` and the commands that never touch the ML stack stay fast. The same
convention appears in `orchestration/assets.py` and `orchestration/definitions.py`, where
Dagster re-imports the code location on every daemon reload.
"""

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


def _train(exchange: str | None = None) -> None:
    """Retrain every market, or one when named.

    `train_evaluate_promote` handles a single market, so a caller that omits the exchange
    silently gets the default one and a summary that reads like a full retrain. The
    scheduled path loops markets itself; this one has to as well, or the two disagree about
    what "train" means.
    """
    from quantpulse.data.calendar import EXCHANGES, get_exchange
    from quantpulse.data.universe import active_tickers
    from quantpulse.db import get_engine, get_session
    from quantpulse.ml.pipeline import train_evaluate_promote

    settings = get_settings()
    codes = [get_exchange(exchange).code] if exchange else sorted(EXCHANGES)
    for code in codes:
        with get_session() as session:
            if not active_tickers(session, code):
                logger.info("%s: no active tickers — skipping", code)
                continue
            summary = train_evaluate_promote(
                get_engine(),
                session,
                tracking_uri=settings.mlflow_tracking_uri,
                exchange=code,
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


def _options_snapshot(force: bool = False) -> None:
    from quantpulse.data.universe import active_tickers, options_tickers
    from quantpulse.db import get_session
    from quantpulse.options.ingest import OffHoursSnapshotError, snapshot_option_chains

    with get_session() as session:
        # Options-bearing markets only — same narrowing the Dagster asset applies, so the
        # two paths snapshot the same set instead of the CLI also walking the JSE names.
        tickers = options_tickers(session)
        if not tickers:
            # "Nothing synced yet" and "synced, but no market here has options" need
            # different fixes, so don't send both to sync-universe.
            reason = (
                "run `quantpulse sync-universe` first"
                if not active_tickers(session)
                else "no options-bearing market has active members"
            )
            logger.error("No tickers to snapshot — %s", reason)
            sys.exit(1)
    try:
        n = snapshot_option_chains(get_session, tickers, force=force)
    except OffHoursSnapshotError as exc:
        # A refusal is an expected outcome of running this by hand, not a crash — report
        # it like the other CLI guards rather than dumping a traceback.
        logger.error("%s", exc)
        sys.exit(1)
    logger.info("Wrote %d option quotes", n)


def _demote(exchange: str, reason: str, version: str | None, dry_run: bool) -> None:
    """Withdraw a promotion and fall back to whatever stands behind it.

    Deliberately manual. Choosing to undo a promotion needs a human judgement about why,
    which is why `--reason` is required and lands in the audit row: a demotion with no
    recorded cause is the kind of history that makes later investigation harder.
    """
    from quantpulse.config import get_settings
    from quantpulse.db import get_session
    from quantpulse.ml import registry
    from quantpulse.ml.promotion import demote_champion

    registry.configure(get_settings().mlflow_tracking_uri)
    try:
        with get_session() as session:
            result = demote_champion(session, exchange, reason, version, dry_run)
    except ValueError as exc:
        logger.error("%s", exc)
        sys.exit(1)

    verb = "would demote" if dry_run else "demoted"
    logger.info(
        "%s %s v%s (%s); champion is now %s",
        result.exchange,
        verb,
        result.demoted_version,
        result.reason,
        f"v{result.fell_back_to}" if result.fell_back_to else "none — market stands down",
    )


def _prune(exchange: str | None) -> None:
    """Select a feature set from evidence and measure it against the full one."""
    from quantpulse.data.calendar import EXCHANGES
    from quantpulse.db import get_engine
    from quantpulse.features.engineering import FEATURE_COLUMNS
    from quantpulse.ml.ablation import RESOLVES_AT_T, forward_select

    engine = get_engine()
    for code in [exchange] if exchange else sorted(EXCHANGES):
        try:
            sel = forward_select(engine, code)
        except ValueError as exc:
            logger.error("%s: %s", code, exc)
            continue
        logger.info(
            "%s selected %d of %d: %s",
            sel.exchange,
            len(sel.chosen),
            len(FEATURE_COLUMNS),
            ", ".join(sel.chosen) or "(nothing beat an empty model)",
        )
        logger.info(
            "  holdout IC — pruned %.4f | full %.4f | momentum %.4f (paired over %d seeds)",
            sel.pruned_ic,
            sel.full_ic,
            sel.baseline_ic,
            sel.seeds,
        )
        if sel.delta_t != sel.delta_t:
            verdict = "no set selected — nothing to compare"
        elif sel.delta_t >= RESOLVES_AT_T:
            verdict = (
                f"pruning helps: {sel.delta:+.4f} +/- {sel.delta_se:.4f} (t {sel.delta_t:+.2f})"
            )
        elif sel.delta_t <= -RESOLVES_AT_T:
            verdict = (
                f"pruning hurts: {sel.delta:+.4f} +/- {sel.delta_se:.4f} "
                f"(t {sel.delta_t:+.2f}) — keep the full set"
            )
        else:
            verdict = (
                f"pruning changes nothing that repeats: {sel.delta:+.4f} "
                f"+/- {sel.delta_se:.4f} (t {sel.delta_t:+.2f})"
            )
        logger.info("  %s", verdict)


def _ablation(exchange: str | None) -> None:
    """Report which features earn their place, per market."""
    from quantpulse.data.calendar import EXCHANGES
    from quantpulse.db import get_engine
    from quantpulse.ml.ablation import ablation_report

    engine = get_engine()
    for code in [exchange] if exchange else sorted(EXCHANGES):
        try:
            table = ablation_report(engine, code)
        except ValueError as exc:
            logger.error("%s: %s", code, exc)
            continue
        logger.info(
            "%s full model IC %.4f | deltas paired across %d seeds, |t| >= 2 to count",
            code,
            table.attrs["full_ic"],
            table.attrs["seeds"],
        )
        logger.info(
            "%-22s %-10s %-10s %-7s %-9s %s",
            "feature",
            "delta",
            "std err",
            "t",
            "alone IC",
            "verdict",
        )
        for row in table.to_dict("records"):
            logger.info(
                "%-22s %+-10.4f %-10.4f %+-7.2f %-9.4f %s",
                row["feature"],
                row["delta"],
                row["delta_se"],
                row["delta_t"],
                row["alone_ic"],
                row["verdict"],
            )


def _staleness(exchange: str | None) -> None:
    """Report how fast a frozen model loses skill, per market."""
    from quantpulse.data.calendar import EXCHANGES
    from quantpulse.db import get_engine
    from quantpulse.ml.staleness import staleness_curve

    engine = get_engine()
    for code in [exchange] if exchange else sorted(EXCHANGES):
        try:
            table = staleness_curve(engine, code)
        except ValueError as exc:
            logger.error("%s: %s", code, exc)
            continue
        if table.empty:
            logger.warning("%s: no age bucket had enough dates to score", code)
            continue
        logger.info(
            "%s staleness: %d freeze points x %d seeds",
            code,
            table.attrs["origins"],
            table.attrs["seeds"],
        )
        logger.info("%-14s %-10s %-10s %s", "age (days)", "IC", "std err", "window-fits")
        for row in table.to_dict("records"):
            logger.info(
                "%-14s %+-10.4f %-10.4f %d",
                f"{row['age_start']}-{row['age_end']}",
                row["ic"],
                row["ic_std_error"],
                row["n_windows"],
            )
        first, last = table.iloc[0], table.iloc[-1]
        change = last["ic"] - first["ic"]
        pooled = (first["ic_std_error"] ** 2 + last["ic_std_error"] ** 2) ** 0.5
        resolved = pooled > 0 and abs(change) >= 2 * pooled
        if not resolved:
            logger.info(
                "  no change this window can resolve (%+.4f against %.4f) — measured "
                "staleness does not justify any particular cadence",
                change,
                2 * pooled,
            )
            continue
        if change < 0:
            # The last age at which the model is still better than nothing is the cadence
            # bound: past it the book is running on a model that hurts.
            useful = [r for r in table.to_dict("records") if r["ic"] - 2 * r["ic_std_error"] > 0]
            bound = f"{useful[-1]['age_end']} days" if useful else "less than the first bucket"
            logger.info(
                "  IC falls %+.4f from age %d to age %d (%.1f sd); still positive out to %s, "
                "so retrain before a model is older than that",
                change,
                first["age_start"],
                last["age_end"],
                abs(change) / pooled,
                bound,
            )
        else:
            logger.info(
                "  IC *rises* %+.4f with age (%.1f sd), which is not staleness — a model that "
                "predicts worst when freshest points at the training window, not the cadence",
                change,
                abs(change) / pooled,
            )


def _retrain_value(exchange: str | None) -> None:
    """Report whether a freshly fitted model beats an older one on the same window."""
    from quantpulse.data.calendar import EXCHANGES
    from quantpulse.db import get_engine
    from quantpulse.ml.retrain_value import retrain_value

    engine = get_engine()
    for code in [exchange] if exchange else sorted(EXCHANGES):
        try:
            table = retrain_value(engine, code)
        except ValueError as exc:
            logger.error("%s: %s", code, exc)
            continue
        if table.empty:
            logger.warning("%s: no lag had enough shared windows to compare", code)
            continue
        logger.info(
            "%s retrain value: %d origins x %d seeds",
            code,
            table.attrs["origins"],
            table.attrs["seeds"],
        )
        logger.info(
            "%-12s %-11s %-10s %-7s %s", "lag (days)", "fresh-stale", "std err", "t", "favour fresh"
        )
        for row in table.to_dict("records"):
            se = row["std_error"]
            logger.info(
                "%-12d %+-11.4f %-10.4f %-+7.2f %d/%d",
                row["lag_days"],
                row["mean_delta"],
                se,
                row["mean_delta"] / se if se else float("nan"),
                row["n_favour_fresh"],
                row["n_windows"],
            )
        worst = min(table.to_dict("records"), key=lambda r: r["mean_delta"])
        if worst["mean_delta"] + 2 * worst["std_error"] < 0:
            logger.info(
                "  retraining costs %+.4f IC at a lag of %d days and the window resolves it — "
                "a fresher model is not automatically a better one, so the cadence rests on "
                "the promotion gate rather than on freshness",
                worst["mean_delta"],
                worst["lag_days"],
            )
        else:
            logger.info(
                "  no lag shows a difference this window can resolve — retraining is not "
                "measurably better than leaving the model alone"
            )


def _baseline(exchange: str | None) -> None:
    """Compare the champion against simpler models on one shared holdout.

    The question the ML Test Score audit found unanswered: does the LightGBM layer beat a
    momentum rule? Reports every competitor on the same exam so the answer is comparable
    rather than anecdotal.
    """
    from quantpulse.config import get_settings
    from quantpulse.data.calendar import EXCHANGES
    from quantpulse.db import get_engine
    from quantpulse.ml.baselines import compare_baselines

    engine = get_engine()
    for code in [exchange] if exchange else sorted(EXCHANGES):
        try:
            table = compare_baselines(engine, code, tracking_uri=get_settings().mlflow_tracking_uri)
        except ValueError as exc:
            logger.error("%s: %s", code, exc)
            continue
        logger.info(
            "%s holdout %s -> %s (%s sessions)",
            code,
            table.attrs["holdout_start"],
            table.attrs["holdout_end"],
            table.attrs["holdout_days"],
        )
        logger.info("%-22s %-9s %-9s %-9s %-9s", "model", "IC", "sharpe", "ann.ret", "max dd")
        for row in table.to_dict("records"):
            logger.info(
                "%-22s %-9.4f %-9.2f %-8.2f%% %-8.2f%%",
                row["model"],
                row["holdout_ic"],
                row["holdout_sharpe"],
                row["holdout_annual_return"] * 100,
                row["holdout_max_drawdown"] * 100,
            )


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
    options_snapshot = sub.add_parser(
        "options-snapshot", help="Snapshot live option chains for the universe"
    )
    options_snapshot.add_argument(
        "--force",
        action="store_true",
        help=(
            "Snapshot even before the close. Testing only: off-hours IV is stale and "
            "overwrites good post-close rows for the same snapshot_date."
        ),
    )
    sub.add_parser("sensitivity", help="Backtest sensitivity to trading cost and borrow rate")
    base = sub.add_parser("baseline", help="Compare the champion against simpler models")
    stale = sub.add_parser("staleness", help="Report how fast a frozen model loses skill")
    stale.add_argument("--exchange", default=None, help="Limit to one market, e.g. XJSE")
    retr = sub.add_parser(
        "retrain-value", help="Report whether retraining beats leaving a model alone"
    )
    retr.add_argument("--exchange", default=None, help="Limit to one market, e.g. XJSE")
    abl = sub.add_parser("ablation", help="Report which features earn their place")
    prn = sub.add_parser("prune", help="Select a feature set from evidence and measure it")
    prn.add_argument("--exchange", default=None, help="Limit to one market, e.g. XJSE")
    abl.add_argument("--exchange", default=None, help="Limit to one market, e.g. XJSE")
    dem = sub.add_parser("demote", help="Withdraw a promotion and fall back")
    dem.add_argument("--exchange", required=True, help="Market code, e.g. XJSE")
    dem.add_argument("--reason", required=True, help="Why — recorded in the audit row")
    dem.add_argument("--version", default=None, help="Version to demote (default: champion)")
    dem.add_argument("--dry-run", action="store_true", help="Report the plan, change nothing")
    base.add_argument("--exchange", default=None, help="Limit to one market, e.g. XJSE")
    trn = sub.add_parser("train", help="Train, evaluate, and maybe promote a model")
    trn.add_argument("--exchange", default=None, help="Limit to one market, e.g. XJSE")
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
        _options_snapshot(args.force)
    elif args.command == "sensitivity":
        _sensitivity()
    elif args.command == "baseline":
        _baseline(args.exchange)
    elif args.command == "ablation":
        _ablation(args.exchange)
    elif args.command == "prune":
        _prune(args.exchange)
    elif args.command == "staleness":
        _staleness(args.exchange)
    elif args.command == "retrain-value":
        _retrain_value(args.exchange)
    elif args.command == "demote":
        _demote(args.exchange, args.reason, args.version, args.dry_run)
    elif args.command == "train":
        _train(args.exchange)
    elif args.command == "score":
        _score(args.replay, args.exchange)


if __name__ == "__main__":
    main()
