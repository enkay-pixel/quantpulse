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
    run_type: Mapped[str] = mapped_column(String(16))  # 'train' | 'promotion' | 'demotion'
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
        CheckConstraint("run_type IN ('train', 'promotion', 'demotion')", name="run_type_valid"),
        CheckConstraint(
            "decision IN ('promoted', 'rejected') OR decision IS NULL", name="decision_valid"
        ),
    )


class DriftMetric(Base):
    __tablename__ = "drift_metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, index=True)
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
