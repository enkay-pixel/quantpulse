"""ORM models for the `market` database. Grain and purpose per docs/data-dictionary.md."""

import datetime as dt
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from quantpulse.db.base import Base


class UniverseMember(Base):
    __tablename__ = "universe"

    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(128))
    asset_type: Mapped[str] = mapped_column(String(8))  # 'stock' | 'etf'
    # Source of truth for which market a ticker belongs to; see data.calendar.EXCHANGES.
    exchange: Mapped[str] = mapped_column(String(8), default="XNYS", index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    added_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (CheckConstraint("asset_type IN ('stock', 'etf')", name="asset_type_valid"),)


class Price(Base):
    __tablename__ = "prices"

    ticker: Mapped[str] = mapped_column(
        ForeignKey("universe.ticker", ondelete="RESTRICT"), primary_key=True
    )
    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(BigInteger)
    source: Mapped[str] = mapped_column(String(16))  # data provider, constrained below
    ingested_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("close > 0 AND open > 0 AND high > 0 AND low > 0", name="prices_positive"),
        CheckConstraint("high >= low", name="high_gte_low"),
        CheckConstraint("source IN ('yfinance', 'stooq')", name="source_valid"),
        Index("ix_prices_date", "date"),
    )


class Feature(Base):
    __tablename__ = "features"

    ticker: Mapped[str] = mapped_column(
        String(16), ForeignKey("universe.ticker", ondelete="RESTRICT"), primary_key=True
    )
    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    feature_version: Mapped[str] = mapped_column(String(32), primary_key=True)
    values: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (Index("ix_features_date", "date"),)


class Prediction(Base):
    __tablename__ = "predictions"

    ticker: Mapped[str] = mapped_column(
        String(16), ForeignKey("universe.ticker", ondelete="RESTRICT"), primary_key=True
    )
    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    model_version: Mapped[str] = mapped_column(String(64), primary_key=True)
    score: Mapped[float] = mapped_column(Float)  # predicted forward return
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (Index("ix_predictions_date", "date"),)


class ModelRun(Base):
    __tablename__ = "model_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 'train' | 'promotion' | 'demotion' | 'shadow'. A shadow is a configuration fitted beside
    # the weekly candidate for comparison only: it is never registered, never gated, and never
    # becomes champion, and the check constraint below makes the last of those a property of the
    # table rather than of the code that writes it.
    run_type: Mapped[str] = mapped_column(String(16))
    exchange: Mapped[str] = mapped_column(String(8), default="XNYS")  # whose champion
    mlflow_run_id: Mapped[str | None] = mapped_column(String(64))
    model_version: Mapped[str | None] = mapped_column(String(64))  # MLflow version, a string
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # 'promoted' | 'rejected'; NULL while a run is in flight
    decision: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "run_type IN ('train', 'promotion', 'demotion', 'shadow')", name="run_type_valid"
        ),
        CheckConstraint(
            "decision IN ('promoted', 'rejected') OR decision IS NULL", name="decision_valid"
        ),
        # Several readers identify champions by `decision = 'promoted'` alone, without looking
        # at run_type: the live record's start date and the backfilled boundary both do. A
        # shadow carrying a decision would be read as a promotion by every one of them, so the
        # table refuses it outright.
        CheckConstraint("run_type <> 'shadow' OR decision IS NULL", name="shadow_never_decides"),
    )


class DriftMetric(Base):
    """Feature-distribution drift, measured **per market**.

    Pooling the markets roughly halves the measured signal and hides how large the worst
    feature's drift is. They also drift on different features, so one pooled number
    describes neither.
    """

    __tablename__ = "drift_metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, index=True)
    exchange: Mapped[str] = mapped_column(String(8), default="XNYS", index=True)
    feature_version: Mapped[str] = mapped_column(String(32))
    metric_name: Mapped[str] = mapped_column(String(64))
    value: Mapped[float] = mapped_column(Float)
    drifted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    # A book is per-market and has no ticker to join through, so exchange is carried here.
    exchange: Mapped[str] = mapped_column(String(8), primary_key=True, default="XNYS")
    # Which book this row belongs to — see quantpulse.ml.portfolio.BOOKS. Several
    # constructions run over the same predictions so they can be compared.
    variant: Mapped[str] = mapped_column(String(16), primary_key=True, default="daily")
    equity: Mapped[float] = mapped_column(Float)
    daily_return: Mapped[float] = mapped_column(Float)
    gross_exposure: Mapped[float] = mapped_column(Float)
    net_exposure: Mapped[float] = mapped_column(Float)
    turnover: Mapped[float] = mapped_column(Float)
    positions: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    model_version: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class OptionQuote(Base):
    __tablename__ = "option_quotes"

    snapshot_date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    ticker: Mapped[str] = mapped_column(
        String(16), ForeignKey("universe.ticker", ondelete="RESTRICT"), primary_key=True
    )
    expiry: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    strike: Mapped[float] = mapped_column(Float, primary_key=True)
    option_type: Mapped[str] = mapped_column(String(4), primary_key=True)  # 'call' | 'put'

    underlying_close: Mapped[float] = mapped_column(Float)
    bid: Mapped[float | None] = mapped_column(Float)
    ask: Mapped[float | None] = mapped_column(Float)
    last_price: Mapped[float | None] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(BigInteger, default=0)
    open_interest: Mapped[int] = mapped_column(BigInteger, default=0)
    implied_volatility: Mapped[float] = mapped_column(Float)
    in_the_money: Mapped[bool] = mapped_column(Boolean)

    # Black-Scholes from market IV, computed at ingest time (quantpulse.options.pricing)
    theo_value: Mapped[float] = mapped_column(Float)
    delta: Mapped[float] = mapped_column(Float)
    gamma: Mapped[float] = mapped_column(Float)
    theta: Mapped[float] = mapped_column(Float)
    vega: Mapped[float] = mapped_column(Float)

    ingested_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("option_type IN ('call', 'put')", name="option_type_valid"),
        Index("ix_option_quotes_ticker_date", "ticker", "snapshot_date"),
    )


class ShortInterest(Base):
    """Shares sold short per ticker and settlement date — the research branch's first table.

    Insert-only: a settlement date already stored is never rewritten, so `ingested_at` is the
    date the figure was first seen. Short interest reaches the vendor a week or two after its
    settlement date, and readers key history by `ingested_at` for that reason — keyed by
    settlement, a past day would show a figure that was not yet public.

    No foreign key to `universe`, by design (ADR 0007): research tickers must be addable without
    entering the model's training universe.
    """

    __tablename__ = "short_interest"

    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
    settlement_date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    shares_short: Mapped[int] = mapped_column(BigInteger)
    shares_short_prior: Mapped[int | None] = mapped_column(BigInteger)
    prior_settlement_date: Mapped[dt.date | None] = mapped_column(Date)
    short_pct_float: Mapped[float | None] = mapped_column(Float)
    days_to_cover: Mapped[float | None] = mapped_column(Float)
    float_shares: Mapped[int | None] = mapped_column(BigInteger)
    shares_outstanding: Mapped[int | None] = mapped_column(BigInteger)
    source: Mapped[str] = mapped_column(String(16), default="yfinance")
    ingested_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("shares_short >= 0", name="shares_short_nonnegative"),
        CheckConstraint("source IN ('yfinance')", name="short_interest_source_valid"),
    )


class PageView(Base):
    """Daily Wikipedia page views of each stock's article — public attention (ADR 0007).

    Covers both markets, unlike short interest and option chains, which the JSE does not publish
    free. Insert-only like the rest of the research branch; `article` records which title the
    views were counted on, so a later change of title in configs/attention.yaml is visible in the
    history rather than silently joined to it. No foreign key to `universe`, by design.
    """

    __tablename__ = "page_views"

    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    article: Mapped[str] = mapped_column(String(256))
    views: Mapped[int] = mapped_column(BigInteger)
    ingested_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (CheckConstraint("views >= 0", name="views_nonnegative"),)


class OptionBookPosition(Base):
    """One spread in the paper options book (ADR 0008), or a name it could not trade.

    Rebuilt in full from predictions, the share book's positions and the captured chains, like
    the share books. `status` is open, closed or skipped; a skipped row keeps the reason in
    `note` so the gaps in coverage are visible rather than silent. Prices are per share (a
    contract is 100); `quantity` is fractional, as paper allows.
    """

    __tablename__ = "option_book_positions"

    book: Mapped[str] = mapped_column(String(32), primary_key=True)
    opened: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
    exchange: Mapped[str] = mapped_column(String(8))
    side: Mapped[str] = mapped_column(String(8))  # 'long' | 'short', from the share book
    phase: Mapped[str] = mapped_column(String(8))  # 'replay' | 'live'
    status: Mapped[str] = mapped_column(String(8))  # 'open' | 'closed' | 'skipped'
    note: Mapped[str | None] = mapped_column(String(200))
    option_type: Mapped[str | None] = mapped_column(String(4))
    expiry: Mapped[dt.date | None] = mapped_column(Date)
    long_strike: Mapped[float | None] = mapped_column(Float)
    short_strike: Mapped[float | None] = mapped_column(Float)
    entry_debit: Mapped[float | None] = mapped_column(Float)
    quantity: Mapped[float | None] = mapped_column(Float)
    mark_date: Mapped[dt.date | None] = mapped_column(Date)
    mark_value: Mapped[float | None] = mapped_column(Float)
    mark_basis: Mapped[str | None] = mapped_column(String(16))  # 'quote' | 'intrinsic' | 'settled'
    exit_date: Mapped[dt.date | None] = mapped_column(Date)
    model_version: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (
        CheckConstraint("side IN ('long', 'short')", name="option_book_side_valid"),
        CheckConstraint("phase IN ('replay', 'live')", name="option_book_phase_valid"),
        CheckConstraint("status IN ('open', 'closed', 'skipped')", name="option_book_status_valid"),
    )


class OptionBookDay(Base):
    """The paper options book's equity on each snapshot day (ADR 0008), starting at 1.0."""

    __tablename__ = "option_book_daily"

    book: Mapped[str] = mapped_column(String(32), primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    exchange: Mapped[str] = mapped_column(String(8))
    equity: Mapped[float] = mapped_column(Float)
    cash: Mapped[float] = mapped_column(Float)
    open_positions: Mapped[int] = mapped_column(Integer)
    phase: Mapped[str] = mapped_column(String(8))

    __table_args__ = (
        CheckConstraint("phase IN ('replay', 'live')", name="option_book_daily_phase_valid"),
    )


class _QuoteColumns:
    """The columns of one captured contract, shared by the captures kept apart from `option_quotes`.

    Each extra capture has its own table so the marts over the model universe's chains, and the
    checks on how complete each night was, read exactly the band and the names they always have.
    """

    snapshot_date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
    expiry: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    strike: Mapped[float] = mapped_column(Float, primary_key=True)
    option_type: Mapped[str] = mapped_column(String(4), primary_key=True)  # 'call' | 'put'

    underlying_close: Mapped[float] = mapped_column(Float)
    bid: Mapped[float | None] = mapped_column(Float)
    ask: Mapped[float | None] = mapped_column(Float)
    last_price: Mapped[float | None] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(BigInteger, default=0)
    open_interest: Mapped[int] = mapped_column(BigInteger, default=0)
    implied_volatility: Mapped[float] = mapped_column(Float)
    in_the_money: Mapped[bool] = mapped_column(Boolean)
    theo_value: Mapped[float] = mapped_column(Float)
    delta: Mapped[float] = mapped_column(Float)
    gamma: Mapped[float] = mapped_column(Float)
    theta: Mapped[float] = mapped_column(Float)
    vega: Mapped[float] = mapped_column(Float)

    ingested_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class HeldOptionQuote(_QuoteColumns, Base):
    """Every contract the paper options book holds, captured each night at any distance from spot.

    `option_quotes` keeps strikes within a band around spot, so a held strike the stock moved away
    from used to drop out and its spread was marked at its last quote. Captured from the same
    download as `option_quotes`, so the two agree wherever both hold a contract.
    """

    __tablename__ = "held_option_quotes"
    __table_args__ = (
        CheckConstraint("option_type IN ('call', 'put')", name="held_option_type_valid"),
    )


class WatchlistName(Base):
    """A name the research branch follows that the model does not (ADR 0007).

    Synced from configs/watchlist.yaml. A name in the universe is refused, so nothing here can
    reach a feature, a prediction or a paper book: those tables keep their foreign key to the
    universe, and the watchlist's prices and chains have tables of their own.
    """

    __tablename__ = "watchlist"

    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
    exchange: Mapped[str] = mapped_column(String(8))
    asset_type: Mapped[str] = mapped_column(String(8))  # 'stock' | 'etf'
    why: Mapped[str] = mapped_column(String(300))
    wikipedia: Mapped[str | None] = mapped_column(String(200))
    added_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("asset_type IN ('stock', 'etf')", name="watchlist_asset_type_valid"),
    )


class WatchlistPrice(Base):
    """Daily adjusted bars for the watchlist's names, from the same vendor as `prices`.

    Refetched in full each evening, so a split or dividend adjustment is picked up: nothing
    trains on these, so the rule that fixes a trained-on day (ADR 0006) does not apply. No
    foreign key, so a name's history survives its removal from the watchlist.
    """

    __tablename__ = "watchlist_prices"

    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(BigInteger)
    ingested_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "close > 0 AND open > 0 AND high > 0 AND low > 0", name="watchlist_prices_positive"
        ),
        CheckConstraint("high >= low", name="watchlist_high_gte_low"),
    )


class WatchlistOptionQuote(_QuoteColumns, Base):
    """The watchlist's option chains, captured each evening in the same ±20% band as the universe's.

    Its own table, so the universe's chains, their completeness checks and the options book read
    only the model's names.
    """

    __tablename__ = "watchlist_option_quotes"
    __table_args__ = (
        CheckConstraint("option_type IN ('call', 'put')", name="watchlist_option_type_valid"),
    )


class EdgarFiling(Base):
    """Every EDGAR filing the ownership fetch has read, and what came of it (ADR 0007).

    A company's filing list also holds filings it makes about other companies — its own stakes in
    them — and Form 4s with nothing in common stock. Those are read once, logged here with their
    outcome, and never fetched again; the next run fetches only accessions not in this table.
    """

    __tablename__ = "edgar_filings"

    accession: Mapped[str] = mapped_column(String(25), primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16))
    form: Mapped[str] = mapped_column(String(16))
    filed: Mapped[dt.date] = mapped_column(Date)
    outcome: Mapped[str] = mapped_column(String(16))  # 'stored' | 'other issuer' | 'nothing'
    ingested_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "outcome IN ('stored', 'other issuer', 'nothing')", name="edgar_filing_outcome_valid"
        ),
        Index("ix_edgar_filings_ticker", "ticker"),
    )


class InsiderTransaction(Base):
    """One trade in a company's stock by one of its insiders, from a Form 4 on SEC EDGAR (ADR 0007).

    Directors, officers and over-10% owners must report each trade within two business days.
    `code` is the SEC's transaction code: P an open-market purchase, S an open-market sale, others
    grants, exercises and tax withholding. `planned` is the filer's own statement that the trade
    was made under a plan set in advance (Rule 10b5-1); null on forms older than that field.
    Insert-only by (accession, seq): a filing never changes, and an amendment is its own filing.
    """

    __tablename__ = "insider_transactions"

    accession: Mapped[str] = mapped_column(String(25), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16))
    form: Mapped[str] = mapped_column(String(8))
    filed: Mapped[dt.date] = mapped_column(Date)
    owner: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(200))
    planned: Mapped[bool | None] = mapped_column(Boolean)
    transaction_date: Mapped[dt.date] = mapped_column(Date)
    code: Mapped[str] = mapped_column(String(2))
    shares: Mapped[float] = mapped_column(Float)
    price: Mapped[float | None] = mapped_column(Float)
    acquired: Mapped[str | None] = mapped_column(String(1))  # 'A' acquired | 'D' disposed
    shares_after: Mapped[float | None] = mapped_column(Float)
    ingested_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (Index("ix_insider_transactions_ticker_date", "ticker", "transaction_date"),)


class HolderFiling(Base):
    """A disclosure of a stake over 5% in a company, from a Schedule 13D or 13G (ADR 0007).

    13D is filed by a holder who may seek to influence the company, 13G by a passive one. Only the
    structured form in use since December 2024 is stored, since a percentage read from free text
    would too often be wrong. An exit is a filing too: an amendment reporting under 5%.
    """

    __tablename__ = "holder_filings"

    accession: Mapped[str] = mapped_column(String(25), primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16))
    form: Mapped[str] = mapped_column(String(16))
    filed: Mapped[dt.date] = mapped_column(Date)
    event_date: Mapped[dt.date | None] = mapped_column(Date)
    filer: Mapped[str] = mapped_column(String(200))
    shares: Mapped[float | None] = mapped_column(Float)
    percent: Mapped[float | None] = mapped_column(Float)
    #: The class the stake is in, as the filing names it. A company with several classes is filed
    #: on per class, so a percentage means nothing without it. Empty when the filing names none.
    share_class: Mapped[str | None] = mapped_column(String(200))
    ingested_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (Index("ix_holder_filings_ticker_filed", "ticker", "filed"),)


class FinancialFact(Base):
    """One tagged figure from a company's 10-K or 10-Q, from SEC EDGAR's XBRL facts (ADR 0007).

    Kept as reported, one row per filing, so a figure a later filing restates sits beside the
    original; `filed` says when each became known. `duration_days` is the length of the period
    for a flow such as revenue and zero for a balance at a moment, so a quarter, a year-to-date
    and a year of the same line never collide. Insert-only; US stocks only.
    """

    __tablename__ = "financial_facts"

    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
    concept: Mapped[str] = mapped_column(String(100), primary_key=True)
    unit: Mapped[str] = mapped_column(String(16), primary_key=True)
    period_end: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    duration_days: Mapped[int] = mapped_column(Integer, primary_key=True)
    accession: Mapped[str] = mapped_column(String(25), primary_key=True)
    period_start: Mapped[dt.date | None] = mapped_column(Date)
    value: Mapped[float] = mapped_column(Float)
    fiscal_year: Mapped[int | None] = mapped_column(Integer)
    fiscal_period: Mapped[str | None] = mapped_column(String(4))
    form: Mapped[str] = mapped_column(String(8))
    filed: Mapped[dt.date] = mapped_column(Date)
    ingested_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (Index("ix_financial_facts_ticker_concept", "ticker", "concept"),)


class FundamentalsFetch(Base):
    """When each company's XBRL facts were last fetched, and the newest statement seen then.

    EDGAR's facts document can lag a filing, or never carry it: Coca-Cola's 10-Q of 2026-07-29 was
    still absent from it in October. Fetching whenever a statement is missing from the stored facts
    would download several MB for such a company every morning, so a missing statement is retried
    weekly and a new one at once.
    """

    __tablename__ = "fundamentals_fetches"

    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
    newest_statement: Mapped[str] = mapped_column(String(25))
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))


class PipelineAlert(Base):
    """Pipeline failures, recorded by the Dagster run-failure sensor.

    In Postgres rather than a file: the daemon writes these and the API serves them from a
    different container. A file under DAGSTER_HOME is visible to neither the other container
    nor the next `compose up`, since it lives in a writable layer rather than a volume, so
    alerts written there are recorded correctly and never surface.
    """

    __tablename__ = "pipeline_alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_name: Mapped[str] = mapped_column(String(64))
    run_id: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class StepMemory(Base):
    """Each finished Dagster step's peak memory, recorded by a hook in the step's own process.

    The daemon container's cap is shared by the daemon, its code server, each run's worker and
    the run's step processes, and its cgroup counts page cache too, so the cap being reached says
    little. The container reading is what `resource_report` judges the heaviest run on; a step's own
    peak shows how that step grows as markets are added.
    """

    __tablename__ = "step_memory"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    step_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    job_name: Mapped[str] = mapped_column(String(64))
    pid: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)
    peak_rss_bytes: Mapped[int] = mapped_column(BigInteger)
    # The container's anon + kernel memory as the step finished: shared pages counted once.
    container_bytes: Mapped[int | None] = mapped_column(BigInteger)
