"""Read-only HTTP surface over the platform's data, consumed by the React dashboard.

Four things recur; knowing them makes the rest of the file predictable.

**Two data sources.** Endpoints read either the ORM tables (`prices`, `predictions`,
`option_quotes` — raw facts) or the dbt marts in the `analytics` schema (`fct_*` —
derived, and the only place ratios are computed). Mart queries go through `_mart_rows`,
which returns `None` rather than raising when the schema does not exist yet: a freshly
bootstrapped database has tables but no marts until the first `dbt build`, and the
dashboard should render an empty panel then, not a 500.

**Everything is scoped to one market.** `ExchangeDep` resolves and validates the
`?exchange=` parameter once. An endpoint that forgets it does not fail — it silently serves
one market's data under another's heading. The subtle form is an unscoped aggregate:
`max(Price.date)` over the whole table returns whichever market ingested last, so scope
every `max()` to the rows you are about to read.

**Ratios come from the marts, never from here.** Sharpe, alpha and win rate are nulled at
source below `min_days_for_ratios` (20), because a handful of days annualizes into a
confident-looking number that is pure noise. Computing one in this layer would route
around that guard.

**Nothing here writes.** There are no POST/PUT/DELETE routes by design: the pipeline owns
every mutation, and a serving layer that could edit the evidence would undermine the
audit trail the project rests on.
"""

import datetime as dt
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from quantpulse.api import schemas
from quantpulse.api.deps import engine_dep, session_dep
from quantpulse.data.calendar import DEFAULT_EXCHANGE, EXCHANGES, get_exchange
from quantpulse.db import (
    DriftMetric,
    ModelRun,
    OptionQuote,
    PortfolioSnapshot,
    Prediction,
    Price,
    UniverseMember,
)
from quantpulse.ml.metrics import TRADING_DAYS_PER_YEAR, max_drawdown, sharpe_ratio
from quantpulse.research.brief import compose, gather

router = APIRouter()

# The book the dashboard treats as "the" track record. Other variants exist for
# comparison (quantpulse.ml.portfolio.BOOKS) and are served at /portfolio/books.
LIVE_BOOK = "daily"
# The market shown when the caller does not ask for one — keeps existing URLs working.
LIVE_MARKET = DEFAULT_EXCHANGE
# Overlaid on the equity curve so the cost of daily churn is visible, not just tabulated.
COMPARISON_BOOK = "horizon"

SessionDep = Annotated[Session, Depends(session_dep)]
EngineDep = Annotated[Engine, Depends(engine_dep)]


def exchange_param(
    exchange: Annotated[str, Query(description="Market code, e.g. XNYS or XJSE")] = LIVE_MARKET,
) -> str:
    """Validate + normalise the market code once, rather than in every endpoint."""
    try:
        return get_exchange(exchange).code
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


ExchangeDep = Annotated[str, Depends(exchange_param)]


def _mart_rows(
    session: Session, sql: str, params: dict[str, Any] | None = None
) -> Sequence[Mapping[str, Any]] | None:
    """Query a dbt mart in the analytics schema; None when it doesn't exist yet
    (fresh database before the first dbt build)."""
    try:
        rows = session.execute(text(sql), params or {}).mappings().all()
        return cast("Sequence[Mapping[str, Any]]", rows)
    except ProgrammingError:
        session.rollback()
        return None


@router.get("/health", response_model=schemas.Health)
def health(engine: EngineDep) -> schemas.Health:
    """Whether the API and its database are up, how fresh the prices are, and the memory it uses."""
    from quantpulse.monitoring.resources import cgroup_memory_limit_bytes, process_rss_bytes

    # Self-reported so the container's own footprint is observable without granting anything
    # access to the Docker socket. None off Linux (running the API on a macOS host).
    memory = {
        "memory_rss_bytes": process_rss_bytes(),
        "memory_limit_bytes": cgroup_memory_limit_bytes(),
    }
    try:
        with engine.connect() as conn:
            latest = conn.execute(text("SELECT max(date) FROM prices")).scalar()
        return schemas.Health(status="ok", database=True, latest_price_date=latest, **memory)
    except Exception:
        return schemas.Health(status="degraded", database=False, latest_price_date=None, **memory)


@router.get("/universe", response_model=list[schemas.UniverseMemberOut])
def universe(session: SessionDep) -> list[schemas.UniverseMemberOut]:
    """Every ticker the platform tracks, with its market and whether it is a stock or a fund."""
    members = session.scalars(select(UniverseMember).order_by(UniverseMember.ticker)).all()
    return [
        schemas.UniverseMemberOut(
            ticker=m.ticker, exchange=m.exchange, asset_type=m.asset_type, active=m.active
        )
        for m in members
    ]


@router.get("/prices/{ticker}", response_model=schemas.PriceSeries)
def prices(
    ticker: str,
    session: SessionDep,
    start: Annotated[dt.date | None, Query()] = None,
    end: Annotated[dt.date | None, Query()] = None,
) -> schemas.PriceSeries:
    """One stock's daily prices: open, high, low, close and volume."""
    ticker = ticker.upper()
    stmt = select(Price).where(Price.ticker == ticker).order_by(Price.date)
    if start:
        stmt = stmt.where(Price.date >= start)
    if end:
        stmt = stmt.where(Price.date <= end)
    rows = session.scalars(stmt).all()
    if not rows:
        raise HTTPException(status_code=404, detail=f"No prices stored for {ticker}")
    points = [
        schemas.PricePoint(
            date=r.date, open=r.open, high=r.high, low=r.low, close=r.close, volume=r.volume
        )
        for r in rows
    ]
    return schemas.PriceSeries(ticker=ticker, points=points)


@router.get("/options/{ticker}/summary", response_model=schemas.OptionSummary)
def option_summary(ticker: str, session: SessionDep) -> schemas.OptionSummary:
    """ATM IV + put/call ratio for the latest snapshot (empty before the first run)."""
    ticker = ticker.upper()
    rows = _mart_rows(
        session,
        "SELECT ticker, snapshot_date, atm_iv, atm_days, put_call_ratio, call_oi, put_oi, "
        "n_contracts FROM analytics.fct_option_summary WHERE ticker = :ticker "
        "ORDER BY snapshot_date DESC LIMIT 1",
        {"ticker": ticker},
    )
    latest = dict(rows[0]) if rows else {}
    expiries = _mart_rows(
        session,
        "SELECT DISTINCT expiry FROM analytics.stg_option_quotes WHERE ticker = :ticker "
        "AND snapshot_date = (SELECT max(snapshot_date) FROM analytics.stg_option_quotes "
        "WHERE ticker = :ticker) ORDER BY expiry",
        {"ticker": ticker},
    )
    spot = session.scalar(
        select(OptionQuote.underlying_close)
        .where(OptionQuote.ticker == ticker)
        .order_by(OptionQuote.snapshot_date.desc())
        .limit(1)
    )
    return schemas.OptionSummary(
        ticker=ticker,
        snapshot_date=latest.get("snapshot_date"),
        underlying_close=spot,
        atm_iv=latest.get("atm_iv"),
        atm_days=latest.get("atm_days"),
        put_call_ratio=latest.get("put_call_ratio"),
        call_oi=latest.get("call_oi"),
        put_oi=latest.get("put_oi"),
        n_contracts=latest.get("n_contracts"),
        expiries=[r["expiry"] for r in expiries or []],
    )


@router.get("/options/{ticker}/surface", response_model=schemas.IvSurfaceOut)
def iv_surface(ticker: str, session: SessionDep) -> schemas.IvSurfaceOut:
    """The two readings the chain endpoint cannot give: IV across maturities, and over time.

    `/chain` returns one expiry of the latest snapshot, which is the smile. Reading across
    expiries is the term structure, and reading across snapshots is what the forward-only
    capture has been accruing since 2026-07-20 — neither was surfaced anywhere.

    Buckets 4 and 5 straddle at-the-money (mean moneyness -0.025 and +0.024), so both are
    taken rather than one: a single bucket is a strike offset, not the money. Contracts with
    under a week to run are excluded, matching fct_option_summary — the feed's IV for those is
    unreliable, and an opening junk point invites reading a slope that is not there.
    """
    ticker = ticker.upper()
    snapshot = session.scalar(
        select(func.max(OptionQuote.snapshot_date)).where(OptionQuote.ticker == ticker)
    )
    if snapshot is None:
        return schemas.IvSurfaceOut(
            ticker=ticker, snapshot_date=None, term_structure=[], history=[]
        )
    term = _mart_rows(
        session,
        "SELECT days_to_expiry, expiry, avg(avg_iv) AS avg_iv, "
        "sum(n_contracts)::int AS n_contracts FROM analytics.fct_iv_surface "
        "WHERE ticker = :t AND snapshot_date = :d AND moneyness_bucket IN (4, 5) "
        # Same ">= 7 days" rule fct_option_summary uses. The feed reports unreliable IV for
        # contracts expiring within the week, and a term structure that opens on a junk point
        # invites reading a slope that is not there. Consistency with the existing ATM
        # convention matters more than a complete front end.
        "AND days_to_expiry >= 7 "
        "GROUP BY days_to_expiry, expiry ORDER BY days_to_expiry",
        {"t": ticker, "d": snapshot},
    )
    # Nearest to 30 days per snapshot, matching the ATM convention fct_option_summary uses,
    # so the history line and the headline ATM IV describe the same contract.
    history = _mart_rows(
        session,
        "SELECT DISTINCT ON (snapshot_date) snapshot_date, avg_iv FROM ("
        "  SELECT snapshot_date, days_to_expiry, avg(avg_iv) AS avg_iv "
        "  FROM analytics.fct_iv_surface WHERE ticker = :t AND moneyness_bucket IN (4, 5) "
        "    AND days_to_expiry >= 7 GROUP BY snapshot_date, days_to_expiry) s "
        "ORDER BY snapshot_date, abs(days_to_expiry - 30)",
        {"t": ticker},
    )
    return schemas.IvSurfaceOut(
        ticker=ticker,
        snapshot_date=snapshot,
        term_structure=[schemas.IvTermPoint(**dict(r)) for r in term or []],
        history=[schemas.IvHistoryPoint(**dict(r)) for r in history or []],
    )


@router.get("/options/{ticker}/chain", response_model=schemas.OptionChainOut)
def option_chain(
    ticker: str,
    session: SessionDep,
    expiry: Annotated[dt.date | None, Query()] = None,
) -> schemas.OptionChainOut:
    """Latest snapshot's chain with Greeks; defaults to the nearest expiry."""
    ticker = ticker.upper()
    snapshot = session.scalar(
        select(func.max(OptionQuote.snapshot_date)).where(OptionQuote.ticker == ticker)
    )
    if snapshot is None:
        return schemas.OptionChainOut(
            ticker=ticker, snapshot_date=None, expiry=None, underlying_close=None, contracts=[]
        )
    if expiry is None:
        expiry = session.scalar(
            select(func.min(OptionQuote.expiry)).where(
                OptionQuote.ticker == ticker, OptionQuote.snapshot_date == snapshot
            )
        )
    rows = session.scalars(
        select(OptionQuote)
        .where(
            OptionQuote.ticker == ticker,
            OptionQuote.snapshot_date == snapshot,
            OptionQuote.expiry == expiry,
        )
        .order_by(OptionQuote.strike, OptionQuote.option_type)
    ).all()
    return schemas.OptionChainOut(
        ticker=ticker,
        snapshot_date=snapshot,
        expiry=expiry,
        underlying_close=rows[0].underlying_close if rows else None,
        contracts=[
            schemas.OptionContract(
                expiry=r.expiry,
                strike=r.strike,
                option_type=r.option_type,
                bid=r.bid,
                ask=r.ask,
                last_price=r.last_price,
                volume=r.volume,
                open_interest=r.open_interest,
                implied_volatility=r.implied_volatility,
                in_the_money=r.in_the_money,
                theo_value=r.theo_value,
                delta=r.delta,
                gamma=r.gamma,
                theta=r.theta,
                vega=r.vega,
            )
            for r in rows
        ],
    )


@router.get("/options/{ticker}/idea", response_model=schemas.OptionIdeaOut)
def option_idea(ticker: str, session: SessionDep) -> schemas.OptionIdeaOut:
    """Tier 2: a HYPOTHETICAL structure expressing the model's signal. Not advice."""
    from quantpulse.options.strategy import ChainRow, build_idea

    ticker = ticker.upper()
    empty = schemas.OptionIdeaOut(
        ticker=ticker,
        available=False,
        signal=None,
        direction=None,
        structure=None,
        rationale=None,
        expiry=None,
        legs=[],
        net_debit=None,
        max_profit=None,
        max_loss=None,
        breakeven=None,
    )

    # Per ticker, not global: this endpoint takes no exchange, so a global max() would be
    # the other market's date whenever it ingests first, and every idea would report
    # itself unavailable until NYSE caught up — on a US holiday, all day.
    latest_pred_date = session.scalar(
        select(func.max(Prediction.date)).where(Prediction.ticker == ticker)
    )
    score = session.scalar(
        select(Prediction.score)
        .where(Prediction.ticker == ticker, Prediction.date == latest_pred_date)
        .order_by(Prediction.model_version.desc())
        .limit(1)
    )
    snapshot = session.scalar(
        select(func.max(OptionQuote.snapshot_date)).where(OptionQuote.ticker == ticker)
    )
    if score is None or snapshot is None:
        return empty

    # Prefer the nearest expiry ~2 weeks out so the 21d view has time to play out;
    # if the snapshot only holds short-dated weeklies, fall back to the longest one.
    expiry = session.scalar(
        select(func.min(OptionQuote.expiry)).where(
            OptionQuote.ticker == ticker,
            OptionQuote.snapshot_date == snapshot,
            OptionQuote.expiry >= snapshot + dt.timedelta(days=14),
        )
    ) or session.scalar(
        select(func.max(OptionQuote.expiry)).where(
            OptionQuote.ticker == ticker, OptionQuote.snapshot_date == snapshot
        )
    )
    if expiry is None:
        return empty

    quotes = session.scalars(
        select(OptionQuote).where(
            OptionQuote.ticker == ticker,
            OptionQuote.snapshot_date == snapshot,
            OptionQuote.expiry == expiry,
        )
    ).all()
    if not quotes:
        return empty

    spot = quotes[0].underlying_close
    chain_rows = [
        ChainRow(
            strike=q.strike,
            option_type=q.option_type,
            # mid when quotable, else the model's theoretical value
            price=((q.bid + q.ask) / 2 if q.bid and q.ask else q.theo_value),
        )
        for q in quotes
    ]
    idea = build_idea(float(score), spot, chain_rows)
    if idea is None:
        return schemas.OptionIdeaOut(**{**empty.model_dump(), "signal": float(score)})

    return schemas.OptionIdeaOut(
        ticker=ticker,
        available=True,
        signal=float(score),
        direction=idea.direction,
        structure=idea.structure,
        rationale=idea.rationale,
        expiry=expiry,
        legs=[
            schemas.OptionLegOut(
                action=leg.action, option_type=leg.option_type, strike=leg.strike, price=leg.price
            )
            for leg in idea.legs
        ],
        net_debit=idea.net_debit,
        max_profit=idea.max_profit,
        max_loss=idea.max_loss,
        breakeven=idea.breakeven,
    )


# Explicit /history/ segment so this never shadows static /signals/* routes.
@router.get("/signals/history/{ticker}", response_model=schemas.SignalSeries)
def signal_history(ticker: str, session: SessionDep) -> schemas.SignalSeries:
    """The model's score trail for one ticker (newest model version per date)."""
    ticker = ticker.upper()
    rows = session.execute(
        text(
            "SELECT DISTINCT ON (date) date, score, model_version FROM predictions "
            "WHERE ticker = :ticker ORDER BY date, model_version DESC"
        ),
        {"ticker": ticker},
    ).all()
    return schemas.SignalSeries(
        ticker=ticker,
        points=[
            schemas.SignalPoint(date=r.date, score=r.score, model_version=r.model_version)
            for r in rows
        ],
    )


@router.get("/predictions/latest", response_model=schemas.PredictionsOut)
def latest_predictions(session: SessionDep, exchange: ExchangeDep) -> schemas.PredictionsOut:
    """The model's newest forecasts for one market: each stock's predicted return over the next
    21 trading days (about a month), ranked strongest first. Research output, not advice."""
    members = select(UniverseMember.ticker).where(UniverseMember.exchange == exchange)
    latest_date = session.scalar(
        select(func.max(Prediction.date)).where(Prediction.ticker.in_(members))
    )
    if latest_date is None:
        return schemas.PredictionsOut(date=None, model_version=None, rows=[])
    latest_version = session.scalar(
        select(func.max(Prediction.model_version)).where(
            Prediction.date == latest_date, Prediction.ticker.in_(members)
        )
    )
    rows = session.scalars(
        select(Prediction)
        .where(
            Prediction.date == latest_date,
            Prediction.model_version == latest_version,
            Prediction.ticker.in_(members),
        )
        .order_by(Prediction.score.desc())
    ).all()
    return schemas.PredictionsOut(
        date=latest_date,
        model_version=latest_version,
        rows=[
            schemas.PredictionRow(ticker=r.ticker, score=r.score, rank=i + 1)
            for i, r in enumerate(rows)
        ],
    )


@router.get("/portfolio/equity-curve", response_model=schemas.EquityCurve)
def equity_curve(session: SessionDep, exchange: ExchangeDep) -> schemas.EquityCurve:
    """How the paper book's value has moved day by day, beside the market's index fund and the
    monthly-rebalanced book, with each day marked replay or live."""
    rows = session.scalars(
        select(PortfolioSnapshot)
        .where(
            PortfolioSnapshot.variant == LIVE_BOOK,
            PortfolioSnapshot.exchange == exchange,
        )
        .order_by(PortfolioSnapshot.date)
    ).all()
    if not rows:
        return schemas.EquityCurve(points=[], total_return=None, max_drawdown=None, sharpe=None)
    import pandas as pd

    # Enrich with phase + SPY benchmark from the dbt mart when it exists.
    mart = _mart_rows(
        session,
        "SELECT date, phase, benchmark_equity "
        "FROM analytics.fct_portfolio_vs_benchmark WHERE exchange = :ex ORDER BY date",
        {"ex": exchange},
    )
    enrich = {m["date"]: m for m in mart or []}

    # The horizon book runs over the same predictions and the same days, so it overlays
    # directly — no re-indexing needed. Both start at equity 1.0 on the same date.
    horizon: dict[dt.date, float] = {
        row.date: row.equity
        for row in session.execute(
            select(PortfolioSnapshot.date, PortfolioSnapshot.equity).where(
                PortfolioSnapshot.variant == COMPARISON_BOOK,
                PortfolioSnapshot.exchange == exchange,
            )
        )
    }

    returns = pd.Series([r.daily_return for r in rows])
    return schemas.EquityCurve(
        points=[
            schemas.EquityPoint(
                date=r.date,
                equity=r.equity,
                daily_return=r.daily_return,
                turnover=r.turnover,
                phase=enrich.get(r.date, {}).get("phase"),
                benchmark_equity=enrich.get(r.date, {}).get("benchmark_equity"),
                horizon_equity=horizon.get(r.date),
            )
            for r in rows
        ],
        total_return=rows[-1].equity - 1.0,
        max_drawdown=max_drawdown(returns),
        sharpe=sharpe_ratio(returns, TRADING_DAYS_PER_YEAR) if len(returns) > 2 else None,
    )


@router.get("/exchanges", response_model=list[schemas.ExchangeOut])
def exchanges(session: SessionDep) -> list[schemas.ExchangeOut]:
    """Markets the dashboard can switch between.

    `configured` distinguishes a market that is defined in the registry from one that has
    tickers loaded — the UI should not offer a switch to an empty market.
    """
    from quantpulse.data.universe import active_exchanges

    live = set(active_exchanges(session))
    return [
        schemas.ExchangeOut(
            code=ex.code,
            timezone=ex.timezone,
            currency=ex.currency,
            benchmark=ex.benchmark,
            has_options=ex.has_options,
            display_symbol=ex.display_symbol,
            display_divisor=ex.display_divisor,
            configured=ex.code in live,
        )
        for ex in sorted(EXCHANGES.values(), key=lambda e: e.code)
    ]


@router.get("/portfolio/books", response_model=schemas.BookComparison)
def portfolio_books(session: SessionDep, exchange: ExchangeDep) -> schemas.BookComparison:
    """Compare the paper books that run over the same predictions.

    They differ only in rebalance frequency, so the spread between them is a clean
    read on how fast the signal decays and what the extra churn costs.
    """
    import pandas as pd

    from quantpulse.ml.metrics import annualized_return
    from quantpulse.ml.portfolio import BOOKS

    rebalance = {b.variant: b for b in BOOKS}
    rows = session.scalars(
        select(PortfolioSnapshot)
        .where(PortfolioSnapshot.exchange == exchange)
        .order_by(PortfolioSnapshot.variant, PortfolioSnapshot.date)
    ).all()

    books = []
    for variant in sorted({r.variant for r in rows}):
        series = [r for r in rows if r.variant == variant]
        returns = pd.Series([r.daily_return for r in series])
        turnover = pd.Series([r.turnover for r in series])
        cfg = rebalance.get(variant)
        # Add the charged frictions back to recover the pre-cost return.
        gross = returns.copy()
        if cfg:
            gross = (
                returns
                + cfg.cost_per_turnover * turnover
                + cfg.borrow_rate * cfg.side_weight / TRADING_DAYS_PER_YEAR
            )
        books.append(
            schemas.BookStats(
                variant=variant,
                rebalance_days=cfg.rebalance_days if cfg else 0,
                n_days=len(series),
                total_return=series[-1].equity - 1.0,
                annualized_return=annualized_return(returns, TRADING_DAYS_PER_YEAR),
                annualized_gross_return=annualized_return(gross, TRADING_DAYS_PER_YEAR),
                sharpe=sharpe_ratio(returns, TRADING_DAYS_PER_YEAR) if len(returns) > 2 else None,
                max_drawdown=max_drawdown(returns),
                mean_turnover=float(turnover.mean()),
                annualized_cost_drag=float(turnover.mean())
                * (cfg.cost_per_turnover if cfg else 0.0)
                * TRADING_DAYS_PER_YEAR,
            )
        )
    return schemas.BookComparison(books=books)


@router.get("/portfolio/champions", response_model=schemas.ChampionRecordOut)
def champion_records(session: SessionDep, exchange: ExchangeDep) -> schemas.ChampionRecordOut:
    """Live record per deployed model — what each champion earned, not what the market did."""
    rows = _mart_rows(
        session,
        "SELECT model_version, n_days, start_date, end_date, total_return, "
        "avg_daily_return, max_drawdown, sharpe, win_rate, is_current "
        "FROM analytics.fct_champion_record WHERE exchange = :ex ORDER BY start_date",
        {"ex": exchange},
    )
    return schemas.ChampionRecordOut(
        champions=[schemas.ChampionRecord(**dict(r)) for r in rows or []]
    )


@router.get("/track-record", response_model=schemas.TrackRecord)
def track_record(session: SessionDep, exchange: ExchangeDep) -> schemas.TrackRecord:
    """The paper book's results, split into the replay from before the model went live and the
    live record since. Judge only the live part."""
    live_since = session.scalar(
        select(func.min(ModelRun.created_at)).where(
            ModelRun.decision == "promoted", ModelRun.exchange == exchange
        )
    )
    rows = _mart_rows(
        session,
        "SELECT phase, n_days, start_date, end_date, total_return, annualized_volatility, "
        "sharpe, max_drawdown, win_rate FROM analytics.fct_track_record "
        "WHERE exchange = :ex ORDER BY phase",
        {"ex": exchange},
    )
    return schemas.TrackRecord(
        live_since=live_since.date() if live_since else None,
        phases=[schemas.PhaseStats(**dict(r)) for r in rows or []],
    )


@router.get("/alerts", response_model=schemas.AlertsOut)
def alerts(limit: Annotated[int, Query(ge=1, le=50)] = 10) -> schemas.AlertsOut:
    """Recent pipeline failures, newest last. Empty when nothing has failed."""
    from quantpulse.monitoring.alerts import read_alerts

    return schemas.AlertsOut(
        alerts=[schemas.AlertEntry(**entry) for entry in read_alerts(limit=limit)]
    )


@router.get("/portfolio/alpha-beta", response_model=schemas.AlphaBetaOut)
def alpha_beta(session: SessionDep, exchange: ExchangeDep) -> schemas.AlphaBetaOut:
    """Market exposure vs market-independent return — the fair read on a long/short book."""
    rows = _mart_rows(
        session,
        "SELECT phase, n_days, beta, alpha_daily, alpha_annualized, "
        "alpha_std_error_annualized, alpha_t_stat, r_squared, "
        "correlation, tracking_error, information_ratio "
        "FROM analytics.fct_alpha_beta WHERE exchange = :ex ORDER BY phase",
        {"ex": exchange},
    )
    return schemas.AlphaBetaOut(phases=[schemas.AlphaBetaStats(**dict(r)) for r in rows or []])


@router.get("/decisions", response_model=schemas.DecisionsOut)
def decisions(engine: EngineDep) -> schemas.DecisionsOut:
    """The standing decisions, and whether anything has reopened one.

    Judged on the stored record by the same code the weekday decisions job runs, so the
    dashboard and the notification cannot disagree about a condition.
    """
    from quantpulse.config import get_settings
    from quantpulse.monitoring.decisions import collect, evaluate, load

    settings = get_settings()
    if not settings.quantpulse_decisions_file.exists():
        return schemas.DecisionsOut(decisions=[])
    standing = load(settings.quantpulse_decisions_file)
    try:
        outcomes = evaluate(standing, collect(engine, settings.quantpulse_shadow_verdict_dir))
    except ProgrammingError:  # the marts have not been built yet
        return schemas.DecisionsOut(decisions=[])
    out = []
    for d in standing:
        mine = [o for o in outcomes if o.decision.id == d.id]
        states = {o.state for o in mine}
        if "fired" in states:
            state = "reopened"
        elif "unknown" in states:
            state = "unknown"
        elif states == {"manual"}:
            state = "manual"
        else:
            state = "standing"
        out.append(
            schemas.DecisionOut(
                id=d.id,
                title=d.title,
                decided=d.decided,
                note=d.note,
                state=state,
                conditions=[
                    schemas.DecisionConditionOut(
                        type=o.condition.type, state=o.state, detail=o.detail
                    )
                    for o in mine
                ],
            )
        )
    return schemas.DecisionsOut(decisions=out)


@router.get("/findings", response_model=schemas.FindingsOut)
def findings() -> schemas.FindingsOut:
    """Every investigation's question and outcome, read from the findings index itself."""
    from quantpulse.config import get_settings
    from quantpulse.monitoring.findings import load

    settings = get_settings()
    rows = load(settings.quantpulse_findings_index, settings.quantpulse_findings_url)
    return schemas.FindingsOut(
        findings=[
            schemas.FindingOut(title=f.title, url=f.url, question=f.question, outcome=f.outcome)
            for f in rows
        ]
    )


@router.get("/options/forward-vrp", response_model=schemas.ForwardVrpOut)
def forward_vrp(session: SessionDep, exchange: ExchangeDep) -> schemas.ForwardVrpOut:
    """Implied volatility against the volatility that then arrived, per snapshot day.

    Only days whose 21-session realization window has closed have a row, so the newest month of
    snapshots is absent by construction.
    """
    rows = _mart_rows(
        session,
        "SELECT snapshot_date, count(*) AS tickers, avg(atm_iv) AS implied, "
        "avg(forward_realized_vol_21d) AS realized, avg(forward_premium) AS premium "
        "FROM analytics.fct_iv_vs_forward_realized WHERE exchange = :ex "
        "GROUP BY snapshot_date ORDER BY snapshot_date",
        {"ex": exchange},
    )
    return schemas.ForwardVrpOut(
        exchange=exchange, days=[schemas.ForwardVrpDay(**dict(r)) for r in rows or []]
    )


_POSITIONING_COLUMNS = (
    "ticker, asset_type, followed_by, spot, call_oi, put_oi, call_gamma_usd_1pct, "
    "put_gamma_usd_1pct, "
    "call_gamma_near_share, adv_usd_20d, call_gamma_share_of_adv, put_gamma_share_of_adv"
)


@router.get("/research/positioning", response_model=schemas.PositioningOut)
def positioning(session: SessionDep, exchange: ExchangeDep) -> schemas.PositioningOut:
    """Option hedging exposure and short interest per ticker, on the market's latest snapshot.

    The two sides run on different clocks: chains are captured each evening, short interest is
    published monthly and arrives a week or two late. So this pairs the latest snapshot with the
    latest short interest known now, each carrying its own date. The mart keeps the history with
    short interest joined as of each day instead, so a past day never shows a later figure.
    """
    rows = _mart_rows(
        session,
        f"SELECT snapshot_date, {_POSITIONING_COLUMNS} FROM analytics.fct_positioning "
        "WHERE exchange = :ex AND snapshot_date = (SELECT max(snapshot_date) "
        "FROM analytics.fct_positioning WHERE exchange = :ex) ORDER BY ticker",
        {"ex": exchange},
    )
    if not rows:
        return schemas.PositioningOut(exchange=exchange, snapshot_date=None, rows=[])
    short = _mart_rows(
        session,
        "SELECT DISTINCT ON (ticker) ticker, settlement_date, known_from, shares_short, "
        "short_pct_float, days_to_cover, "
        "shares_short::float / nullif(shares_short_prior, 0) - 1 AS short_change "
        "FROM analytics.stg_short_interest WHERE ticker = ANY(:tickers) "
        "ORDER BY ticker, settlement_date DESC",
        {"tickers": [r["ticker"] for r in rows]},
    )
    latest_short = {s["ticker"]: s for s in short or []}
    out = []
    for row in rows:
        s = latest_short.get(row["ticker"], {})
        out.append(
            schemas.PositioningRow(
                **{k: v for k, v in row.items() if k != "snapshot_date"},
                short_settlement_date=s.get("settlement_date"),
                short_known_from=s.get("known_from"),
                shares_short=s.get("shares_short"),
                short_pct_float=s.get("short_pct_float"),
                days_to_cover=s.get("days_to_cover"),
                short_change=s.get("short_change"),
            )
        )
    return schemas.PositioningOut(
        exchange=exchange, snapshot_date=rows[0]["snapshot_date"], rows=out
    )


@router.get("/research/positioning/{ticker}/profile", response_model=schemas.GammaProfileOut)
def gamma_profile(ticker: str, session: SessionDep) -> schemas.GammaProfileOut:
    """Call and put dollar gamma by strike on the ticker's latest snapshot — where the hedging
    exposure sits relative to the price."""
    ticker = ticker.upper()
    rows = _mart_rows(
        session,
        "SELECT snapshot_date, spot, strike, call_oi, put_oi, call_gamma_usd_1pct, "
        "put_gamma_usd_1pct FROM analytics.fct_gamma_by_strike WHERE ticker = :t "
        "AND snapshot_date = (SELECT max(snapshot_date) FROM analytics.fct_gamma_by_strike "
        "WHERE ticker = :t) ORDER BY strike",
        {"t": ticker},
    )
    if not rows:
        return schemas.GammaProfileOut(ticker=ticker, snapshot_date=None, spot=None, strikes=[])
    return schemas.GammaProfileOut(
        ticker=ticker,
        snapshot_date=rows[0]["snapshot_date"],
        spot=rows[0]["spot"],
        strikes=[
            schemas.GammaStrike(
                **{k: v for k, v in r.items() if k not in ("snapshot_date", "spot")}
            )
            for r in rows
        ],
    )


@router.get("/research/watchlist", response_model=schemas.WatchlistOut)
def watchlist(session: SessionDep) -> schemas.WatchlistOut:
    """The names the research branch follows beyond the model's universe, and why each is followed.

    They appear on the Positioning tab beside the universe's names, marked as watchlist names.
    None is ever a model input.
    """
    rows = _mart_rows(
        session,
        "SELECT ticker, exchange, asset_type, why, wikipedia FROM analytics.stg_watchlist "
        "ORDER BY exchange, ticker",
        {},
    )
    return schemas.WatchlistOut(names=[schemas.WatchlistName(**dict(r)) for r in rows or []])


@router.get("/research/ownership", response_model=schemas.OwnershipOut)
def ownership(session: SessionDep, exchange: ExchangeDep) -> schemas.OwnershipOut:
    """Insider buying and selling over the past 90 days, and holders over 5%, per US stock.

    From SEC EDGAR filings: Form 4 for insiders' trades, Schedules 13D and 13G for large stakes.
    A JSE company files with no US regulator, so that market's list is empty.
    """
    rows = _mart_rows(
        session,
        "SELECT ticker, followed_by, as_of, bought_usd_90d, sold_usd_90d, buyers_90d, sellers_90d, "
        "planned_sold_share_90d, last_trade_date, holders_over_5pct, activist_holder, top_holder, "
        "top_holder_percent, top_holder_class FROM analytics.fct_ownership "
        "WHERE exchange = :ex ORDER BY ticker",
        {"ex": exchange},
    )
    if not rows:
        return schemas.OwnershipOut(exchange=exchange, as_of=None, rows=[])
    return schemas.OwnershipOut(
        exchange=exchange,
        as_of=rows[0]["as_of"],
        rows=[schemas.OwnershipRow(**{k: v for k, v in r.items() if k != "as_of"}) for r in rows],
    )


@router.get("/research/ownership/{ticker}", response_model=schemas.OwnershipDetailOut)
def ownership_detail(ticker: str, session: SessionDep) -> schemas.OwnershipDetailOut:
    """One stock's open-market insider trades over the past year, newest first, and the holders
    whose latest 13D or 13G still reports 5% or more, largest first."""
    ticker = ticker.upper()
    trades = _mart_rows(
        session,
        "SELECT transaction_date, filed, owner, role, trade, shares_traded, trade_price, "
        "value_usd, planned FROM analytics.fct_insider_trades WHERE ticker = :t AND "
        "transaction_date > "
        "(SELECT max(filed) FROM analytics.fct_insider_trades) - 365 "
        "ORDER BY transaction_date DESC, accession, seq LIMIT 50",
        {"t": ticker},
    )
    holders = _mart_rows(
        session,
        "SELECT filer, form, filed, shares_held, percent, share_class "
        "FROM analytics.fct_large_holders "
        "WHERE ticker = :t ORDER BY percent DESC",
        {"t": ticker},
    )
    return schemas.OwnershipDetailOut(
        ticker=ticker,
        trades=[schemas.InsiderTrade(**dict(r)) for r in trades or []],
        holders=[schemas.HolderStake(**dict(r)) for r in holders or []],
    )


_FUNDAMENTALS_COLUMNS = ", ".join(schemas.FundamentalsRow.model_fields)


@router.get("/research/fundamentals", response_model=schemas.FundamentalsOut)
def fundamentals(session: SessionDep, exchange: ExchangeDep) -> schemas.FundamentalsOut:
    """Each US company's revenue, profit, cash flow and balance sheet over the last twelve months,
    from its SEC filings, with price ratios where they can be trusted. JSE companies file with no
    US regulator, so that market's list is empty."""
    rows = _mart_rows(
        session,
        f"SELECT {_FUNDAMENTALS_COLUMNS} FROM analytics.fct_fundamentals "
        "WHERE exchange = :ex ORDER BY ticker",
        {"ex": exchange},
    )
    return schemas.FundamentalsOut(
        exchange=exchange, rows=[schemas.FundamentalsRow(**dict(r)) for r in rows or []]
    )


@router.get("/research/briefs", response_model=schemas.BriefIndexOut)
def brief_index(session: SessionDep, exchange: ExchangeDep) -> schemas.BriefIndexOut:
    """The stocks one market has a brief for: the model's universe, then the research watchlist."""
    rows = _mart_rows(
        session,
        "SELECT r.ticker, u.name, r.followed_by FROM analytics.stg_research_names r "
        "LEFT JOIN universe u ON u.ticker = r.ticker WHERE r.exchange = :ex "
        "ORDER BY r.followed_by, r.ticker",
        {"ex": exchange},
    )
    return schemas.BriefIndexOut(
        exchange=exchange, names=[schemas.BriefName(**dict(r)) for r in rows or []]
    )


@router.get("/research/brief/{ticker}", response_model=schemas.BriefOut)
def advisor_brief(ticker: str, session: SessionDep) -> schemas.BriefOut:
    """One page per stock to take to a licensed advisor: the evidence, the points that lean each
    way, the risks, questions to ask and what the page cannot know. Assesses; never advises."""
    evidence = gather(session, ticker)
    if evidence is None:
        raise HTTPException(
            status_code=404,
            detail=f"{ticker.upper()} is neither in the model's universe nor on the watchlist",
        )
    return schemas.BriefOut(**asdict(compose(evidence)))


@router.get("/research/attention", response_model=schemas.AttentionOut)
def attention(session: SessionDep, exchange: ExchangeDep) -> schemas.AttentionOut:
    """Each stock's public attention on its newest day, for one market — the research branch's
    measure that covers the JSE as well as the NYSE."""
    rows = _mart_rows(
        session,
        "SELECT DISTINCT ON (ticker) ticker, coalesce(followed_by, 'model') AS followed_by, "
        "article, date, views_7d, baseline_90d, attention_ratio FROM analytics.fct_attention "
        "WHERE exchange = :ex "
        "ORDER BY ticker, date DESC",
        {"ex": exchange},
    )
    out = [schemas.AttentionRow(**dict(r)) for r in rows or []]
    as_of = max((r.date for r in out), default=None)
    return schemas.AttentionOut(exchange=exchange, as_of=as_of, rows=out)


@router.get("/research/attention/{ticker}/history", response_model=schemas.AttentionHistoryOut)
def attention_history(ticker: str, session: SessionDep) -> schemas.AttentionHistoryOut:
    """A year of one stock's daily views, its weekly mean and its usual level."""
    ticker = ticker.upper()
    rows = _mart_rows(
        session,
        "SELECT date, article, views, views_7d, baseline_90d FROM analytics.fct_attention "
        "WHERE ticker = :t AND date > (SELECT max(date) FROM analytics.fct_attention "
        "WHERE ticker = :t) - 365 ORDER BY date",
        {"t": ticker},
    )
    if not rows:
        return schemas.AttentionHistoryOut(ticker=ticker, article=None, days=[])
    return schemas.AttentionHistoryOut(
        ticker=ticker,
        article=rows[-1]["article"],
        days=[schemas.AttentionDay(**{k: v for k, v in r.items() if k != "article"}) for r in rows],
    )


@router.get("/options/book", response_model=schemas.OptionBookOut)
def option_book(session: SessionDep, exchange: ExchangeDep) -> schemas.OptionBookOut:
    """The paper options book: the model's forecasts held through limited-risk option spreads
    instead of shares, priced every evening at the pessimistic side of each quote, beside the
    21-day share book holding the same names over the same windows. Paper only, not advice."""
    import bisect

    from quantpulse.db import OptionBookDay, OptionBookPosition
    from quantpulse.options import book as ob

    positions = [
        {c.name: getattr(p, c.name) for c in OptionBookPosition.__table__.columns}
        for p in session.scalars(
            select(OptionBookPosition)
            .where(OptionBookPosition.book == ob.BOOK, OptionBookPosition.exchange == exchange)
            .order_by(OptionBookPosition.opened, OptionBookPosition.ticker)
        )
    ]
    days = session.scalars(
        select(OptionBookDay)
        .where(OptionBookDay.book == ob.BOOK, OptionBookDay.exchange == exchange)
        .order_by(OptionBookDay.date)
    ).all()
    shares = session.execute(
        select(PortfolioSnapshot.date, PortfolioSnapshot.equity)
        .where(PortfolioSnapshot.exchange == exchange, PortfolioSnapshot.variant == ob.SHARE_BOOK)
        .order_by(PortfolioSnapshot.date)
    ).all()
    dates = [row.date for row in shares]
    equities = [row.equity for row in shares]

    def share_value(day: dt.date | None) -> float | None:
        # A share-book row already includes the next session's return, so the value at a day's
        # close is the row before that day; with no day, the newest value there is.
        if day is None:
            return equities[-1] if equities else None
        i = bisect.bisect_left(dates, day)
        return equities[i - 1] if i else None

    def share_return(opened: dt.date, closes: dt.date | None) -> float | None:
        start, end = share_value(opened), share_value(closes)
        return end / start - 1 if start and end else None

    base = share_value(days[0].date) if days else None
    newest = positions[-1]["opened"] if positions else None
    return schemas.OptionBookOut(
        exchange=exchange,
        live_since=ob.LIVE_SINCE,
        risk_budget=ob.RISK_BUDGET,
        days=[
            schemas.OptionBookDayOut(
                date=d.date,
                equity=d.equity,
                phase=d.phase,
                share_equity=(v / base if base and (v := share_value(d.date)) else None),
            )
            for d in days
        ],
        cohorts=[
            schemas.OptionBookCohortOut(**c) for c in ob.summarize_cohorts(positions, share_return)
        ],
        positions=[
            schemas.OptionBookPositionOut(
                **{k: p[k] for k in schemas.OptionBookPositionOut.model_fields if k in p},
                return_on_premium=(
                    ob.return_on_premium(p["entry_debit"], p["mark_value"])
                    if p["status"] != "skipped"
                    else None
                ),
            )
            for p in positions
            if p["opened"] == newest
        ],
    )


@router.get("/signals/quintiles", response_model=schemas.QuintilesOut)
def signal_quintiles(session: SessionDep, exchange: ExchangeDep) -> schemas.QuintilesOut:
    """Whether the ranking works: the average next-day return of each fifth of the stocks, sorted
    by forecast, over all days and over recent days."""
    overall = _mart_rows(
        session,
        "SELECT signal_quintile, count(*) AS n_days, avg(avg_next_day_return) AS "
        "avg_next_day_return FROM analytics.fct_signal_performance "
        "WHERE exchange = :ex GROUP BY signal_quintile ORDER BY signal_quintile",
        {"ex": exchange},
    )
    # Trailing 45 calendar days ~= 30 trading days.
    recent = _mart_rows(
        session,
        "SELECT signal_quintile, count(*) AS n_days, avg(avg_next_day_return) AS "
        "avg_next_day_return FROM analytics.fct_signal_performance "
        "WHERE exchange = :ex AND date >= (SELECT max(date) FROM "
        "analytics.fct_signal_performance WHERE exchange = :ex) - 45 "
        "GROUP BY signal_quintile ORDER BY signal_quintile",
        {"ex": exchange},
    )
    return schemas.QuintilesOut(
        overall=[schemas.QuintileStat(**dict(r)) for r in overall or []],
        recent=[schemas.QuintileStat(**dict(r)) for r in recent or []],
    )


@router.get("/portfolio/risk", response_model=schemas.RiskOut)
def portfolio_risk(session: SessionDep, exchange: ExchangeDep) -> schemas.RiskOut:
    """How far the book has fallen from its highs each day, and its return per unit of risk over
    rolling three-month windows."""
    rows = _mart_rows(
        session,
        "SELECT date, drawdown, rolling_sharpe_63d "
        "FROM analytics.fct_portfolio_daily WHERE exchange = :ex ORDER BY date",
        {"ex": exchange},
    )
    return schemas.RiskOut(points=[schemas.RiskPoint(**dict(r)) for r in rows or []])


@router.get("/portfolio/positions", response_model=schemas.PositionsOut)
def portfolio_positions(session: SessionDep, exchange: ExchangeDep) -> schemas.PositionsOut:
    """What the paper book holds on its newest day: each position's side, share of the book and
    the forecast behind it."""
    snapshot = session.scalars(
        select(PortfolioSnapshot)
        .where(PortfolioSnapshot.variant == LIVE_BOOK, PortfolioSnapshot.exchange == exchange)
        .order_by(PortfolioSnapshot.date.desc())
    ).first()
    if snapshot is None or not snapshot.positions:
        return schemas.PositionsOut(date=None, model_version=None, rows=[])
    tickers = list(snapshot.positions.keys())

    # Scoped to the names in this book, not the database. A global max() returns whichever
    # market last ingested — with NYSE a session ahead of the JSE, every JSE row looked up
    # its close on a date the JSE never traded and came back empty, so the positions table
    # rendered twenty blank price and score columns while NYSE looked perfect.
    latest_price_date = session.scalar(
        select(func.max(Price.date)).where(Price.ticker.in_(tickers))
    )
    closes = {
        p.ticker: p.close
        for p in session.scalars(
            select(Price).where(Price.date == latest_price_date, Price.ticker.in_(tickers))
        )
    }
    latest_pred_date = session.scalar(
        select(func.max(Prediction.date)).where(Prediction.ticker.in_(tickers))
    )
    scores = {
        p.ticker: p.score
        for p in session.scalars(
            select(Prediction).where(
                Prediction.date == latest_pred_date, Prediction.ticker.in_(tickers)
            )
        )
    }
    rows = [
        schemas.PositionRow(
            ticker=ticker,
            weight=weight,
            side="long" if weight >= 0 else "short",
            latest_close=closes.get(ticker),
            latest_score=scores.get(ticker),
        )
        for ticker, weight in sorted(snapshot.positions.items(), key=lambda kv: kv[1], reverse=True)
    ]
    return schemas.PositionsOut(date=snapshot.date, model_version=snapshot.model_version, rows=rows)


@router.get("/models/history", response_model=list[schemas.ModelRunOut])
def model_history(session: SessionDep, exchange: ExchangeDep) -> list[schemas.ModelRunOut]:
    """Every model trained for one market, promoted or not, with the scores the promotion gate
    judged it on."""
    # Production's history only. A shadow is a configuration fitted beside the candidate for
    # comparison, never a model that ran or could have run, and listing it beside promotions and
    # rejections would read as a decision that was never made.
    runs = session.scalars(
        select(ModelRun)
        .where(ModelRun.exchange == exchange, ModelRun.run_type != "shadow")
        .order_by(ModelRun.id.desc())
    ).all()
    return [
        schemas.ModelRunOut(
            id=r.id,
            run_type=r.run_type,
            model_version=r.model_version,
            decision=r.decision,
            # metrics also carries audit strings (holdout window, demotion reasons)
            metrics={k: float(v) for k, v in r.metrics.items() if isinstance(v, (int, float))},
            mlflow_run_id=r.mlflow_run_id,
            created_at=r.created_at,
        )
        for r in runs
    ]


@router.get("/models/current", response_model=schemas.ModelInfo)
def current_model(session: SessionDep, exchange: ExchangeDep) -> schemas.ModelInfo:
    """The market's most recent promotion.

    Scoped: showing one market's champion while another market's data is on screen is the
    kind of mix-up nobody notices until a decision rests on it. A market whose candidate
    was rejected correctly reports no champion.
    """
    # Demotion-aware, and shared with the `champion_registry_agrees` asset check so the two
    # cannot drift into agreeing with each other while disagreeing with MLflow.
    from quantpulse.ml.promotion import audit_champion

    run = audit_champion(session, exchange)
    if run is None:
        return schemas.ModelInfo(
            model_version=None, decision=None, trained_at=None, metrics={}, mlflow_run_id=None
        )
    return schemas.ModelInfo(
        model_version=run.model_version,
        decision=run.decision,
        trained_at=run.created_at,
        # metrics also carries audit strings (holdout window); the API contract is numbers
        metrics={k: float(v) for k, v in run.metrics.items() if isinstance(v, (int, float))},
        mlflow_run_id=run.mlflow_run_id,
    )


@router.get("/drift/latest", response_model=schemas.DriftStatus)
def latest_drift(session: SessionDep, exchange: ExchangeDep) -> schemas.DriftStatus:
    """Whether the market has moved away from what the model learned: each input's shift from
    training, against the alarm levels."""
    # Scoped like every other endpoint. Legacy rows stamped POOLED are invisible here:
    # they measured both markets mixed together and belong to neither.
    latest_date = session.scalar(
        select(func.max(DriftMetric.date)).where(DriftMetric.exchange == exchange)
    )
    from quantpulse.monitoring.drift import PSI_DRIFT_THRESHOLD, SHARE_DRIFT_THRESHOLD

    limits = {"psi_threshold": PSI_DRIFT_THRESHOLD, "share_threshold": SHARE_DRIFT_THRESHOLD}
    if latest_date is None:
        return schemas.DriftStatus(
            date=None, share_drifted=None, drifted=None, features=[], **limits
        )
    rows = session.scalars(
        select(DriftMetric).where(DriftMetric.date == latest_date, DriftMetric.exchange == exchange)
    ).all()
    share = next((r for r in rows if r.metric_name == "share_drifted"), None)
    features = [
        schemas.DriftFeatureOut(
            feature=r.metric_name.removeprefix("psi:"), psi=r.value, drifted=r.drifted
        )
        for r in rows
        if r.metric_name.startswith("psi:")
    ]
    return schemas.DriftStatus(
        date=latest_date,
        share_drifted=share.value if share else None,
        drifted=share.drifted if share else None,
        features=sorted(features, key=lambda f: f.psi, reverse=True),
        **limits,
    )


@router.get("/freshness", response_model=schemas.FreshnessOut)
def freshness(session: SessionDep, exchange: ExchangeDep) -> schemas.FreshnessOut:
    """How up to date each stage of the pipeline is for one market: prices, model inputs,
    forecasts and the paper book."""
    from quantpulse.db import Feature

    # Each stage is scoped: an unscoped max() would show NYSE's dates while a JSE view is
    # on screen, which reads as "this market is up to date" when it may not be.
    members = select(UniverseMember.ticker).where(UniverseMember.exchange == exchange)
    return schemas.FreshnessOut(
        latest_price_date=session.scalar(
            select(func.max(Price.date)).where(Price.ticker.in_(members))
        ),
        latest_feature_date=session.scalar(
            select(func.max(Feature.date)).where(Feature.ticker.in_(members))
        ),
        latest_prediction_date=session.scalar(
            select(func.max(Prediction.date)).where(Prediction.ticker.in_(members))
        ),
        latest_snapshot_date=session.scalar(
            select(func.max(PortfolioSnapshot.date)).where(
                PortfolioSnapshot.variant == LIVE_BOOK,
                PortfolioSnapshot.exchange == exchange,
            )
        ),
    )
