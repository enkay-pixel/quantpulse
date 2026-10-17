"""Company fundamentals from SEC EDGAR's XBRL facts (ADR 0007) — US stocks only.

Every 10-K and 10-Q is filed with its financial statements tagged in XBRL, and EDGAR serves each
company's tagged facts as one document: revenue, earnings, cash flow and the balance sheet, each
with the period it covers, the filing it came from and the day it was filed. Free, with the same
contact rule as the ownership filings.

Only the concepts in CONCEPTS are kept, from FIRST_PERIOD on. A fact is stored as reported, keyed
by its filing, so a figure a later filing restates sits beside the original and either can be read:
the marts use the latest, and the filing date says when each became known.

A company's document is large (several MB), so it is fetched again only when the company has filed
a new 10-K or 10-Q since the last fetch, or a week after a fetch that did not yet carry the newest
one: the facts document can lag a filing, or never carry it.
"""

import datetime as dt
import logging
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from quantpulse.db import FinancialFact, FundamentalsFetch
from quantpulse.research.ownership import SUBMISSIONS_URL, EdgarClient, Http, ticker_ciks
from quantpulse.utils import chunked

logger = logging.getLogger(__name__)

FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

#: The tagged concepts kept, by (taxonomy, concept, unit). Several mean the same line under
#: different names, and companies move between them (Apple's revenue left `Revenues` in 2018,
#: Alphabet's left the contract-revenue tag in 2025), so the marts pick per period, not per name.
CONCEPTS: tuple[tuple[str, str, str], ...] = (
    ("us-gaap", "Revenues", "USD"),
    ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax", "USD"),
    ("us-gaap", "RevenueFromContractWithCustomerIncludingAssessedTax", "USD"),
    ("us-gaap", "SalesRevenueNet", "USD"),
    # Banks' revenue: net of the interest they pay (Wells Fargo, Goldman Sachs).
    ("us-gaap", "RevenuesNetOfInterestExpense", "USD"),
    ("us-gaap", "OperatingIncomeLoss", "USD"),
    ("us-gaap", "NetIncomeLoss", "USD"),
    # Net profit under other names: Caterpillar, Mastercard and Broadcom file one of these instead.
    ("us-gaap", "NetIncomeLossAvailableToCommonStockholdersBasic", "USD"),
    ("us-gaap", "ProfitLoss", "USD"),
    ("us-gaap", "EarningsPerShareDiluted", "USD/shares"),
    ("us-gaap", "NetCashProvidedByUsedInOperatingActivities", "USD"),
    ("us-gaap", "PaymentsToAcquirePropertyPlantAndEquipment", "USD"),
    # NVIDIA, among others, reports capital spending under this broader name.
    ("us-gaap", "PaymentsToAcquireProductiveAssets", "USD"),
    ("us-gaap", "Assets", "USD"),
    ("us-gaap", "Liabilities", "USD"),
    ("us-gaap", "StockholdersEquity", "USD"),
    ("us-gaap", "CashAndCashEquivalentsAtCarryingValue", "USD"),
    ("us-gaap", "LongTermDebtNoncurrent", "USD"),
    ("us-gaap", "LongTermDebt", "USD"),
    ("dei", "EntityCommonStockSharesOutstanding", "shares"),
)
#: The forms whose statements are read. Amendments restate; they are kept like any other filing.
FORMS = frozenset({"10-K", "10-Q", "10-K/A", "10-Q/A"})
#: Facts for periods ending before this are left out: enough history for growth and a few years
#: of context, without a decade of rows per company.
FIRST_PERIOD = dt.date(2016, 1, 1)


class NoFundamentalsReturned(RuntimeError):
    """Not one company's filing list could be read: EDGAR is unreachable or refusing this client."""


@dataclass
class FundamentalsReport:
    tickers: int = 0
    refreshed: list[str] = field(default_factory=list)
    up_to_date: int = 0
    facts: int = 0
    #: Fetched, but EDGAR's facts document did not yet carry the newest statement.
    lagging: list[str] = field(default_factory=list)
    no_cik: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)


def parse_company_facts(ticker: str, data: dict[str, Any]) -> list[dict[str, Any]]:
    """The kept facts of one company's XBRL document, one row per reported value."""
    rows = []
    for taxonomy, concept, unit in CONCEPTS:
        values = data.get("facts", {}).get(taxonomy, {}).get(concept, {}).get("units", {}).get(unit)
        for v in values or []:
            if v.get("form") not in FORMS or v.get("val") is None or not v.get("end"):
                continue
            end = dt.date.fromisoformat(v["end"])
            if end < FIRST_PERIOD:
                continue
            start = dt.date.fromisoformat(v["start"]) if v.get("start") else None
            rows.append(
                {
                    "ticker": ticker,
                    "concept": concept,
                    "unit": unit,
                    "period_end": end,
                    # Zero for a balance at a moment (an instant), the length of the period for a
                    # flow, so one key covers both and a quarter is never confused with a year.
                    "duration_days": (end - start).days if start else 0,
                    "period_start": start,
                    "value": float(v["val"]),
                    "fiscal_year": v.get("fy"),
                    "fiscal_period": v.get("fp"),
                    "form": v["form"],
                    "filed": dt.date.fromisoformat(v["filed"]),
                    "accession": v["accn"],
                }
            )
    return rows


#: How long to wait before fetching again for a statement the facts document did not carry.
RETRY_MISSING = dt.timedelta(days=7)


def _newest_statement(submissions: dict[str, Any]) -> str | None:
    """The accession of the company's newest 10-K or 10-Q (EDGAR lists newest first)."""
    recent = submissions.get("filings", {}).get("recent", {})
    return next(
        (
            accession
            for form, accession in zip(
                recent.get("form", []), recent.get("accessionNumber", []), strict=False
            )
            if form in FORMS
        ),
        None,
    )


def _due(session: Session, ticker: str, newest: str, now: dt.datetime) -> bool:
    """Fetch when the newest statement is new since the last fetch, or still absent from the
    stored facts a week after it was last looked for."""
    last = session.get(FundamentalsFetch, ticker)
    if last is None or last.newest_statement != newest:
        return True
    have = session.scalar(
        select(func.count())
        .select_from(FinancialFact)
        .where(FinancialFact.ticker == ticker, FinancialFact.accession == newest)
    )
    return not have and now - last.fetched_at >= RETRY_MISSING


def _insert(session: Session, rows: list[dict[str, Any]]) -> int:
    inserted = 0
    for chunk in chunked(rows):
        result = session.execute(
            pg_insert(FinancialFact)
            .values(list(chunk))
            .on_conflict_do_nothing()
            .returning(FinancialFact.ticker)
        )
        inserted += len(result.all())
    return inserted


def refresh_fundamentals(
    session_factory: Callable[[], AbstractContextManager[Session]],
    tickers: Iterable[str],
    http: Http | None = None,
    now: dt.datetime | None = None,
) -> FundamentalsReport:
    """Fetch the XBRL facts of every company with a statement newer than those stored.

    Insert-only, committing per company, so a failure costs that company until the next run.
    """
    http = http or EdgarClient()
    now = now or dt.datetime.now(dt.UTC)
    tickers = list(dict.fromkeys(tickers))
    report = FundamentalsReport()
    ciks = ticker_ciks(http)
    for ticker in tickers:
        cik = ciks.get(ticker.upper())
        if cik is None:
            report.no_cik.append(ticker)
            continue
        try:
            newest = _newest_statement(http.get_json(SUBMISSIONS_URL.format(cik=cik)))
        except Exception as exc:
            report.failed[ticker] = type(exc).__name__
            logger.warning("EDGAR filing list failed for %s", ticker, exc_info=True)
            continue
        report.tickers += 1
        with session_factory() as session:
            if newest is None or not _due(session, ticker, newest, now):
                report.up_to_date += 1
                continue
            try:
                rows = parse_company_facts(ticker, http.get_json(FACTS_URL.format(cik=cik)))
            except Exception as exc:
                report.failed[ticker] = type(exc).__name__
                logger.warning("EDGAR facts failed for %s", ticker, exc_info=True)
                continue
            report.facts += _insert(session, rows)
            report.refreshed.append(ticker)
            if not any(r["accession"] == newest for r in rows):
                report.lagging.append(ticker)
            session.merge(FundamentalsFetch(ticker=ticker, newest_statement=newest, fetched_at=now))
    if report.tickers == 0 and len(report.no_cik) < len(tickers):
        raise NoFundamentalsReturned(
            f"No filing list could be read for any of {len(tickers)} tickers: {report.failed}"
        )
    return report
