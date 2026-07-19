"""Load the configured trading universe and sync it into the database."""

from dataclasses import dataclass
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from quantpulse.db import UniverseMember


@dataclass(frozen=True)
class UniverseEntry:
    ticker: str
    asset_type: str  # 'stock' | 'etf'


def load_universe(path: Path) -> list[UniverseEntry]:
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"Universe file {path} must be a mapping of asset types to tickers")
    entries: list[UniverseEntry] = []
    for asset_type, key in (("etf", "etfs"), ("stock", "stocks")):
        for ticker in raw.get(key) or []:
            entries.append(UniverseEntry(ticker=str(ticker).upper(), asset_type=asset_type))
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
                UniverseMember(ticker=entry.ticker, asset_type=entry.asset_type, active=True)
            )
            added += 1
        elif not member.active or member.asset_type != entry.asset_type:
            member.active = True
            member.asset_type = entry.asset_type
            updated += 1
    for ticker, member in existing.items():
        if ticker not in configured and member.active:
            member.active = False
            deactivated += 1
    return {"added": added, "updated": updated, "deactivated": deactivated}


def active_tickers(session: Session) -> list[str]:
    return list(
        session.scalars(
            select(UniverseMember.ticker)
            .where(UniverseMember.active)
            .order_by(UniverseMember.ticker)
        )
    )
