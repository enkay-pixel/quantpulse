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
    source: Mapped[str] = mapped_column(String(16))  # 'yfinance' | 'stooq'
    ingested_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("close > 0 AND open > 0 AND high > 0 AND low > 0", name="prices_positive"),
        CheckConstraint("high >= low", name="high_gte_low"),
        Index("ix_prices_date", "date"),
    )


class Feature(Base):
    __tablename__ = "features"

    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    feature_version: Mapped[str] = mapped_column(String(32), primary_key=True)
    values: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (Index("ix_features_date", "date"),)


class Prediction(Base):
    __tablename__ = "predictions"

    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
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
    run_type: Mapped[str] = mapped_column(String(16))  # 'train' | 'promotion'
    mlflow_run_id: Mapped[str | None] = mapped_column(String(64))
    model_version: Mapped[str | None] = mapped_column(String(64))
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    decision: Mapped[str | None] = mapped_column(String(16))  # 'promoted'|'rejected'|'initial'
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
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
