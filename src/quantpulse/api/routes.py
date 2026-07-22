import datetime as dt
from collections.abc import Mapping, Sequence
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from quantpulse.api import schemas
from quantpulse.api.deps import engine_dep, session_dep
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

router = APIRouter()

# The book the dashboard treats as "the" track record. Other variants exist for
# comparison (quantpulse.ml.portfolio.BOOKS) and are served at /portfolio/books.
LIVE_BOOK = "daily"

SessionDep = Annotated[Session, Depends(session_dep)]
EngineDep = Annotated[Engine, Depends(engine_dep)]


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
    try:
        with engine.connect() as conn:
            latest = conn.execute(text("SELECT max(date) FROM prices")).scalar()
        return schemas.Health(status="ok", database=True, latest_price_date=latest)
    except Exception:
        return schemas.Health(status="degraded", database=False, latest_price_date=None)


@router.get("/universe", response_model=list[schemas.UniverseMemberOut])
def universe(session: SessionDep) -> list[schemas.UniverseMemberOut]:
    members = session.scalars(select(UniverseMember).order_by(UniverseMember.ticker)).all()
    return [
        schemas.UniverseMemberOut(ticker=m.ticker, asset_type=m.asset_type, active=m.active)
        for m in members
    ]


@router.get("/prices/{ticker}", response_model=schemas.PriceSeries)
def prices(
    ticker: str,
    session: SessionDep,
    start: Annotated[dt.date | None, Query()] = None,
    end: Annotated[dt.date | None, Query()] = None,
) -> schemas.PriceSeries:
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

    latest_pred_date = session.scalar(select(func.max(Prediction.date)))
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
def latest_predictions(session: SessionDep) -> schemas.PredictionsOut:
    latest_date = session.scalar(select(func.max(Prediction.date)))
    if latest_date is None:
        return schemas.PredictionsOut(date=None, model_version=None, rows=[])
    latest_version = session.scalar(
        select(func.max(Prediction.model_version)).where(Prediction.date == latest_date)
    )
    rows = session.scalars(
        select(Prediction)
        .where(Prediction.date == latest_date, Prediction.model_version == latest_version)
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
def equity_curve(session: SessionDep) -> schemas.EquityCurve:
    rows = session.scalars(
        select(PortfolioSnapshot)
        .where(PortfolioSnapshot.variant == LIVE_BOOK)
        .order_by(PortfolioSnapshot.date)
    ).all()
    if not rows:
        return schemas.EquityCurve(points=[], total_return=None, max_drawdown=None, sharpe=None)
    import pandas as pd

    # Enrich with phase + SPY benchmark from the dbt mart when it exists.
    mart = _mart_rows(
        session,
        "SELECT date, phase, benchmark_equity "
        "FROM analytics.fct_portfolio_vs_benchmark ORDER BY date",
    )
    enrich = {m["date"]: m for m in mart or []}

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
            )
            for r in rows
        ],
        total_return=rows[-1].equity - 1.0,
        max_drawdown=max_drawdown(returns),
        sharpe=sharpe_ratio(returns, TRADING_DAYS_PER_YEAR) if len(returns) > 2 else None,
    )


@router.get("/portfolio/books", response_model=schemas.BookComparison)
def portfolio_books(session: SessionDep) -> schemas.BookComparison:
    """Compare the paper books that run over the same predictions.

    They differ only in rebalance frequency, so the spread between them is a clean
    read on how fast the signal decays and what the extra churn costs.
    """
    import pandas as pd

    from quantpulse.ml.metrics import annualized_return
    from quantpulse.ml.portfolio import BOOKS

    rebalance = {b.variant: b for b in BOOKS}
    rows = session.scalars(
        select(PortfolioSnapshot).order_by(PortfolioSnapshot.variant, PortfolioSnapshot.date)
    ).all()

    books = []
    for variant in sorted({r.variant for r in rows}):
        series = [r for r in rows if r.variant == variant]
        returns = pd.Series([r.daily_return for r in series])
        turnover = pd.Series([r.turnover for r in series])
        cfg = rebalance.get(variant)
        books.append(
            schemas.BookStats(
                variant=variant,
                rebalance_days=cfg.rebalance_days if cfg else 0,
                n_days=len(series),
                total_return=series[-1].equity - 1.0,
                annualized_return=annualized_return(returns, TRADING_DAYS_PER_YEAR),
                sharpe=sharpe_ratio(returns, TRADING_DAYS_PER_YEAR) if len(returns) > 2 else None,
                max_drawdown=max_drawdown(returns),
                mean_turnover=float(turnover.mean()),
                annualized_cost_drag=float(turnover.mean())
                * (cfg.cost_per_turnover if cfg else 0.0)
                * TRADING_DAYS_PER_YEAR,
            )
        )
    return schemas.BookComparison(books=books)


@router.get("/track-record", response_model=schemas.TrackRecord)
def track_record(session: SessionDep) -> schemas.TrackRecord:
    live_since = session.scalar(
        select(func.min(ModelRun.created_at)).where(ModelRun.decision == "promoted")
    )
    rows = _mart_rows(
        session,
        "SELECT phase, n_days, start_date, end_date, total_return, annualized_volatility, "
        "sharpe, max_drawdown, win_rate FROM analytics.fct_track_record ORDER BY phase",
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
def alpha_beta(session: SessionDep) -> schemas.AlphaBetaOut:
    """Market exposure vs market-independent return — the fair read on a long/short book."""
    rows = _mart_rows(
        session,
        "SELECT phase, n_days, beta, alpha_daily, alpha_annualized, r_squared, "
        "correlation, tracking_error, information_ratio "
        "FROM analytics.fct_alpha_beta ORDER BY phase",
    )
    return schemas.AlphaBetaOut(phases=[schemas.AlphaBetaStats(**dict(r)) for r in rows or []])


@router.get("/signals/quintiles", response_model=schemas.QuintilesOut)
def signal_quintiles(session: SessionDep) -> schemas.QuintilesOut:
    overall = _mart_rows(
        session,
        "SELECT signal_quintile, count(*) AS n_days, avg(avg_next_day_return) AS "
        "avg_next_day_return FROM analytics.fct_signal_performance "
        "GROUP BY signal_quintile ORDER BY signal_quintile",
    )
    # Trailing 45 calendar days ~= 30 trading days.
    recent = _mart_rows(
        session,
        "SELECT signal_quintile, count(*) AS n_days, avg(avg_next_day_return) AS "
        "avg_next_day_return FROM analytics.fct_signal_performance "
        "WHERE date >= (SELECT max(date) FROM analytics.fct_signal_performance) - 45 "
        "GROUP BY signal_quintile ORDER BY signal_quintile",
    )
    return schemas.QuintilesOut(
        overall=[schemas.QuintileStat(**dict(r)) for r in overall or []],
        recent=[schemas.QuintileStat(**dict(r)) for r in recent or []],
    )


@router.get("/portfolio/risk", response_model=schemas.RiskOut)
def portfolio_risk(session: SessionDep) -> schemas.RiskOut:
    rows = _mart_rows(
        session,
        "SELECT date, drawdown, rolling_sharpe_63d "
        "FROM analytics.fct_portfolio_daily ORDER BY date",
    )
    return schemas.RiskOut(points=[schemas.RiskPoint(**dict(r)) for r in rows or []])


@router.get("/portfolio/positions", response_model=schemas.PositionsOut)
def portfolio_positions(session: SessionDep) -> schemas.PositionsOut:
    snapshot = session.scalars(
        select(PortfolioSnapshot)
        .where(PortfolioSnapshot.variant == LIVE_BOOK)
        .order_by(PortfolioSnapshot.date.desc())
    ).first()
    if snapshot is None or not snapshot.positions:
        return schemas.PositionsOut(date=None, model_version=None, rows=[])
    tickers = list(snapshot.positions.keys())

    latest_price_date = session.scalar(select(func.max(Price.date)))
    closes = {
        p.ticker: p.close
        for p in session.scalars(
            select(Price).where(Price.date == latest_price_date, Price.ticker.in_(tickers))
        )
    }
    latest_pred_date = session.scalar(select(func.max(Prediction.date)))
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
def model_history(session: SessionDep) -> list[schemas.ModelRunOut]:
    runs = session.scalars(select(ModelRun).order_by(ModelRun.id.desc())).all()
    return [
        schemas.ModelRunOut(
            id=r.id,
            run_type=r.run_type,
            model_version=r.model_version,
            decision=r.decision,
            metrics={k: float(v) for k, v in r.metrics.items()},
            mlflow_run_id=r.mlflow_run_id,
            created_at=r.created_at,
        )
        for r in runs
    ]


@router.get("/models/current", response_model=schemas.ModelInfo)
def current_model(session: SessionDep) -> schemas.ModelInfo:
    run = session.scalars(
        select(ModelRun).where(ModelRun.decision == "promoted").order_by(ModelRun.id.desc())
    ).first()
    if run is None:
        return schemas.ModelInfo(
            model_version=None, decision=None, trained_at=None, metrics={}, mlflow_run_id=None
        )
    return schemas.ModelInfo(
        model_version=run.model_version,
        decision=run.decision,
        trained_at=run.created_at,
        metrics={k: float(v) for k, v in run.metrics.items()},
        mlflow_run_id=run.mlflow_run_id,
    )


@router.get("/drift/latest", response_model=schemas.DriftStatus)
def latest_drift(session: SessionDep) -> schemas.DriftStatus:
    latest_date = session.scalar(select(func.max(DriftMetric.date)))
    if latest_date is None:
        return schemas.DriftStatus(date=None, share_drifted=None, drifted=None, features=[])
    rows = session.scalars(select(DriftMetric).where(DriftMetric.date == latest_date)).all()
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
    )


@router.get("/freshness", response_model=schemas.FreshnessOut)
def freshness(session: SessionDep) -> schemas.FreshnessOut:
    from quantpulse.db import Feature

    return schemas.FreshnessOut(
        latest_price_date=session.scalar(select(func.max(Price.date))),
        latest_feature_date=session.scalar(select(func.max(Feature.date))),
        latest_prediction_date=session.scalar(select(func.max(Prediction.date))),
        latest_snapshot_date=session.scalar(
            select(func.max(PortfolioSnapshot.date)).where(PortfolioSnapshot.variant == LIVE_BOOK)
        ),
    )
