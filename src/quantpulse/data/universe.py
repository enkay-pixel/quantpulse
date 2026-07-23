"""Load the configured trading universe and sync it into the database."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from quantpulse.data.calendar import DEFAULT_EXCHANGE, get_exchange
from quantpulse.db import UniverseMember


@dataclass(frozen=True)
class UniverseEntry:
    ticker: str
    asset_type: str  # 'stock' | 'etf'
    exchange: str = DEFAULT_EXCHANGE


def load_universe(path: Path) -> list[UniverseEntry]:
    """Parse the universe file.

    Accepts both shapes: the flat `etfs:`/`stocks:` layout (treated as the default
    exchange) and the nested `exchanges: {CODE: {etfs, stocks}}` layout.
    """
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"Universe file {path} must be a mapping")

    blocks: list[tuple[str, Any]]
    if "exchanges" in raw:
        blocks = [(code.upper(), block or {}) for code, block in (raw["exchanges"] or {}).items()]
    else:
        blocks = [(DEFAULT_EXCHANGE, raw)]

    entries: list[UniverseEntry] = []
    for code, block in blocks:
        get_exchange(code)  # reject typos here rather than at ingest time
        for asset_type, key in (("etf", "etfs"), ("stock", "stocks")):
            for ticker in block.get(key) or []:
                entries.append(
                    UniverseEntry(ticker=str(ticker).upper(), asset_type=asset_type, exchange=code)
                )
    if not entries:
        raise ValueError(f"Universe file {path} contains no tickers")
    tickers = [e.ticker for e in entries]
    duplicates = {t for t in tickers if tickers.count(t) > 1}
    if duplicates:
        raise ValueError(f"Duplicate tickers in universe: {sorted(duplicates)}")
    return entries


def sync_universe(session: Session, entries: list[UniverseEntry]) -> dict[str, int]:
    """Upsert configured entries; deactivate members that left the file. Returns counts."""
    existing = {m.ticker: m for m in session.scalars(select(UniverseMember))}
    configured = {e.ticker for e in entries}
    added = updated = deactivated = 0
    for entry in entries:
        member = existing.get(entry.ticker)
        if member is None:
            session.add(
                UniverseMember(
                    ticker=entry.ticker,
                    asset_type=entry.asset_type,
                    exchange=entry.exchange,
                    active=True,
                )
            )
            added += 1
        elif (
            not member.active
            or member.asset_type != entry.asset_type
            or member.exchange != entry.exchange
        ):
            member.active = True
            member.asset_type = entry.asset_type
            member.exchange = entry.exchange
            updated += 1
    for ticker, member in existing.items():
        if ticker not in configured and member.active:
            member.active = False
            deactivated += 1
    return {"added": added, "updated": updated, "deactivated": deactivated}


def active_tickers(session: Session, exchange: str | None = None) -> list[str]:
    """Active tickers, optionally for one exchange (None = every market)."""
    stmt = select(UniverseMember.ticker).where(UniverseMember.active)
    if exchange:
        stmt = stmt.where(UniverseMember.exchange == exchange)
    return list(session.scalars(stmt.order_by(UniverseMember.ticker)))


def active_exchanges(session: Session) -> list[str]:
    """Exchange codes that currently have active members."""
    return list(
        session.scalars(
            select(UniverseMember.exchange)
            .where(UniverseMember.active)
            .distinct()
            .order_by(UniverseMember.exchange)
        )
    )
