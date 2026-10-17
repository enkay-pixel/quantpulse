"""Ownership and insider activity from SEC EDGAR (ADR 0007) — US names only.

Two kinds of public filing:

- **Form 4**: a company's directors, officers and over-10% owners must report each trade in its
  stock within two business days. Stored per transaction in `insider_transactions`.
- **Schedules 13D and 13G**: anyone who comes to own more than 5% of a class must disclose it, on
  13D if they may seek to influence the company, 13G if passive. Stored per filing in
  `holder_filings`. Only the structured form in use since December 2024 is read: older filings
  are free text, and a percentage scraped from prose would be wrong often enough to mislead.

Both are insert-only by accession number, since a filing never changes once accepted (an amendment
is a filing of its own). EDGAR is free and needs no key, but its fair-access policy requires a
contact in the User-Agent and at most 10 requests a second; `quantpulse_sec_contact` supplies the
first, and the client spaces requests well under the second.
"""

import datetime as dt
import logging
import time
import xml.etree.ElementTree as ET  # types only: parsing goes through defusedxml
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Any, Protocol

from defusedxml import ElementTree as SafeET
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from quantpulse.config import get_settings
from quantpulse.db import EdgarFiling, HolderFiling, InsiderTransaction

logger = logging.getLogger(__name__)

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"

INSIDER_FORMS = frozenset({"4", "4/A"})
HOLDER_FORMS = frozenset({"SCHEDULE 13D", "SCHEDULE 13D/A", "SCHEDULE 13G", "SCHEDULE 13G/A"})
#: How far back the first fetch reaches. Later runs fetch only filings not yet stored.
LOOKBACK_DAYS = 730
#: Seconds between requests: about six a second, well under EDGAR's limit of ten.
MIN_INTERVAL = 0.15


class SecContactMissing(RuntimeError):
    """EDGAR refuses requests that do not declare a contact, so fetching without one would only
    collect refusals. Named rather than skipped, so a missing setting is seen the first morning."""


class NoOwnershipReturned(RuntimeError):
    """No ticker's filing list could be read. One failing is ordinary; all of them means EDGAR is
    unreachable or is refusing this client."""


class Http(Protocol):
    def get_json(self, url: str) -> Any: ...
    def get_text(self, url: str) -> str: ...


class EdgarClient:
    """The real client: declares the contact EDGAR requires and paces itself under its limit."""

    def __init__(self, contact: str | None = None) -> None:
        import httpx

        contact = contact or get_settings().quantpulse_sec_contact
        if not contact:
            raise SecContactMissing(
                "SEC EDGAR requires a contact email in each request. Set QUANTPULSE_SEC_CONTACT "
                "in the local .env (never in the repository, which is public)."
            )
        self._client = httpx.Client(
            headers={"User-Agent": f"quantpulse {contact}", "Accept-Encoding": "gzip, deflate"},
            timeout=30,
            transport=httpx.HTTPTransport(retries=2),
        )
        self._last = 0.0

    def _get(self, url: str) -> Any:
        wait = self._last + MIN_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        response = self._client.get(url)
        self._last = time.monotonic()
        response.raise_for_status()
        return response

    def get_json(self, url: str) -> Any:
        return self._get(url).json()

    def get_text(self, url: str) -> str:
        return str(self._get(url).text)


def _text(node: ET.Element | None, path: str) -> str | None:
    if node is None:
        return None
    found = node.find(path)
    if found is None or found.text is None:
        return None
    value = found.text.strip()
    return value or None


def _float(value: str | None) -> float | None:
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _role(owner: ET.Element | None) -> str:
    """The insider's relation to the company in plain words, most senior first."""
    rel = owner.find("reportingOwnerRelationship") if owner is not None else None
    parts = []
    title = _text(rel, "officerTitle")
    if _text(rel, "isOfficer") in ("1", "true"):
        parts.append(title or "officer")
    if _text(rel, "isDirector") in ("1", "true"):
        parts.append("director")
    if _text(rel, "isTenPercentOwner") in ("1", "true"):
        parts.append("over-10% owner")
    if not parts and _text(rel, "isOther") in ("1", "true"):
        parts.append(_text(rel, "otherText") or "other")
    return ", ".join(parts) or "insider"


def parse_form4(xml: str) -> list[dict[str, Any]]:
    """One row per trade in common stock (the non-derivative table) of a Form 4.

    Options and other derivatives are left out: an exercise shows up as the stock it produced, and
    the derivative lines would count the same economic event twice.
    """
    root = SafeET.fromstring(xml)
    owner = root.find("reportingOwner")
    name = _text(owner, "reportingOwnerId/rptOwnerName") or "unknown"
    planned_flag = _text(root, "aff10b5One")
    planned = None if planned_flag is None else planned_flag in ("1", "true")
    rows = []
    for seq, trade in enumerate(root.findall("nonDerivativeTable/nonDerivativeTransaction")):
        shares = _float(_text(trade, "transactionAmounts/transactionShares/value"))
        day = _text(trade, "transactionDate/value")
        code = _text(trade, "transactionCoding/transactionCode")
        if shares is None or day is None or code is None:
            continue
        rows.append(
            {
                "seq": seq,
                "owner": name[:200],
                "role": _role(owner)[:200],
                "planned": planned,
                "transaction_date": dt.date.fromisoformat(day[:10]),
                "code": code[:2],
                "shares": shares,
                "price": _float(_text(trade, "transactionAmounts/transactionPricePerShare/value")),
                "acquired": _text(
                    trade, "transactionAmounts/transactionAcquiredDisposedCode/value"
                ),
                "shares_after": _float(
                    _text(trade, "postTransactionAmounts/sharesOwnedFollowingTransaction/value")
                ),
            }
        )
    return rows


def _strip_namespaces(root: ET.Element) -> ET.Element:
    for node in root.iter():
        if isinstance(node.tag, str) and "}" in node.tag:
            node.tag = node.tag.split("}", 1)[1]
    return root


def parse_schedule13(xml: str) -> dict[str, Any] | None:
    """The first reporting person, their shares and their percent of the class — and which class,
    since a company with several (Berkshire's A and B) is filed on per class — from a structured
    Schedule 13D or 13G. The first cover page names the principal filer; later ones are members of
    the same group reporting the same stake."""
    root = _strip_namespaces(SafeET.fromstring(xml))
    name = next((n.text.strip() for n in root.iter("reportingPersonName") if n.text), None)
    percent = next(
        (
            _float(n.text)
            for n in root.iter()
            if n.tag in ("percentOfClass", "classPercent") and _float(n.text) is not None
        ),
        None,
    )
    shares = next(
        (
            _float(n.text)
            for n in root.iter()
            if n.tag
            in ("aggregateAmountOwned", "reportingPersonBeneficiallyOwnedAggregateNumberOfShares")
            and _float(n.text) is not None
        ),
        None,
    )
    if name is None:
        return None
    event = next(
        (
            n.text.strip()
            for n in root.iter()
            if n.tag in ("dateOfEvent", "eventDateRequiresFilingThisStatement") and n.text
        ),
        None,
    )
    event_date = None
    if event:
        try:
            event_date = dt.datetime.strptime(event, "%m/%d/%Y").date()
        except ValueError:
            event_date = None
    share_class = next(
        (n.text.strip() for n in root.iter("securitiesClassTitle") if n.text and n.text.strip()),
        None,
    )
    return {
        "filer": name[:200],
        "percent": percent,
        "shares": shares,
        "event_date": event_date,
        "share_class": share_class[:200] if share_class else None,
    }


def issuer_cik(xml: str) -> int | None:
    """The CIK of the company a Form 4, 13D or 13G is about, as the document states it."""
    root = _strip_namespaces(SafeET.fromstring(xml))
    for node in root.iter():
        if node.tag in ("issuerCik", "issuerCIK") and node.text and node.text.strip().isdigit():
            return int(node.text.strip())
    return None


def raw_document(primary: str) -> str:
    """The filing's own XML rather than EDGAR's rendered view: `xslF345X06/form4.xml` is the
    stylesheet's path to `form4.xml`."""
    head, _, rest = primary.partition("/")
    return rest if head.startswith("xsl") and rest else primary


@dataclass
class OwnershipReport:
    tickers: int = 0
    trades: int = 0
    holder_filings: int = 0
    other_issuer: int = 0
    classes_filled: int = 0
    no_cik: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)


def ticker_ciks(http: Http) -> dict[str, int]:
    """EDGAR's ticker-to-CIK map, keyed the way Yahoo writes the ticker (BRK-B)."""
    data = http.get_json(TICKERS_URL)
    return {str(v["ticker"]).upper(): int(v["cik_str"]) for v in data.values()}


def _stored(session: Session, ticker: str) -> set[str]:
    return set(session.scalars(select(EdgarFiling.accession).where(EdgarFiling.ticker == ticker)))


def _recent(submissions: dict[str, Any], since: dt.date) -> list[dict[str, str]]:
    recent = submissions.get("filings", {}).get("recent", {})
    keys = ("accessionNumber", "filingDate", "form", "primaryDocument")
    rows = [
        dict(zip(keys, values, strict=True))
        for values in zip(*(recent.get(k, []) for k in keys), strict=True)
    ]
    return [
        r
        for r in rows
        if r["form"] in INSIDER_FORMS | HOLDER_FORMS
        and dt.date.fromisoformat(r["filingDate"]) >= since
    ]


def refresh_ownership(
    session_factory: Callable[[], AbstractContextManager[Session]],
    tickers: Iterable[str],
    http: Http | None = None,
    today: dt.date | None = None,
) -> OwnershipReport:
    """Fetch every new Form 4 and structured 13D/13G for each ticker, committing per ticker.

    Each filing read is logged in `edgar_filings` with its outcome, including one about another
    company, so it is never fetched again. A filing whose document cannot be read is left out of the
    log, and the next run tries it again.
    """
    http = http or EdgarClient()
    tickers = list(dict.fromkeys(tickers))
    since = (today or dt.date.today()) - dt.timedelta(days=LOOKBACK_DAYS)
    report = OwnershipReport()
    ciks = ticker_ciks(http)
    listed = 0
    for ticker in tickers:
        cik = ciks.get(ticker.upper())
        if cik is None:
            report.no_cik.append(ticker)
            continue
        try:
            filings = _recent(http.get_json(SUBMISSIONS_URL.format(cik=cik)), since)
        except Exception as exc:
            report.failed[ticker] = type(exc).__name__
            logger.warning("EDGAR filing list failed for %s", ticker, exc_info=True)
            continue
        listed += 1
        report.tickers += 1
        with session_factory() as session:
            stored = _stored(session, ticker)
            for f in filings:
                accession = f["accessionNumber"]
                if accession in stored:
                    continue
                url = ARCHIVE_URL.format(
                    cik=cik,
                    accession=accession.replace("-", ""),
                    document=raw_document(f["primaryDocument"]),
                )
                filed = dt.date.fromisoformat(f["filingDate"])
                try:
                    xml = http.get_text(url)
                    if issuer_cik(xml) != cik:
                        # The company's own filing about another company, such as its stake in
                        # one: on this company's list, but not about it.
                        outcome = "other issuer"
                        report.other_issuer += 1
                    elif f["form"] in INSIDER_FORMS:
                        n = _insert_trades(session, ticker, accession, f["form"], filed, xml)
                        report.trades += n
                        outcome = "stored" if n else "nothing"
                    else:
                        n = _insert_holder(session, ticker, accession, f["form"], filed, xml)
                        report.holder_filings += n
                        outcome = "stored" if n else "nothing"
                except Exception:
                    logger.warning(
                        "EDGAR filing %s (%s) not read", accession, ticker, exc_info=True
                    )
                    continue  # left out of the log, so the next run tries it again
                session.execute(
                    pg_insert(EdgarFiling)
                    .values(
                        accession=accession,
                        ticker=ticker,
                        form=f["form"],
                        filed=filed,
                        outcome=outcome,
                    )
                    .on_conflict_do_nothing()
                )
    with session_factory() as session:
        report.classes_filled = fill_share_classes(session, http, ciks)
    if listed == 0 and len(report.no_cik) < len(tickers):
        raise NoOwnershipReturned(
            f"No filing list could be read for any of {len(tickers)} tickers: {report.failed}"
        )
    return report


def fill_share_classes(session: Session, http: Http, ciks: dict[str, int]) -> int:
    """Read the share class of stake filings stored before it was recorded.

    Each such filing is read once more. One that names no class is marked empty, so it is not read
    again; one that fails to read is left for the next run.
    """
    missing = session.execute(
        select(HolderFiling.accession, HolderFiling.ticker).where(
            HolderFiling.share_class.is_(None)
        )
    ).all()
    filled = 0
    for accession, ticker in missing:
        cik = ciks.get(ticker.upper())
        share_class = ""
        if cik is not None:
            try:
                # Only structured filings are stored, and their document always has this name.
                xml = http.get_text(
                    ARCHIVE_URL.format(
                        cik=cik, accession=accession.replace("-", ""), document="primary_doc.xml"
                    )
                )
                share_class = (parse_schedule13(xml) or {}).get("share_class") or ""
            except Exception:
                logger.warning("Share class not read for %s (%s)", accession, ticker, exc_info=True)
                continue  # left null, so the next run tries again
        session.execute(
            update(HolderFiling)
            .where(HolderFiling.accession == accession)
            .values(share_class=share_class)
        )
        filled += bool(share_class)
    return filled


def _insert_trades(
    session: Session, ticker: str, accession: str, form: str, filed: dt.date, xml: str
) -> int:
    rows = [
        {**r, "ticker": ticker, "accession": accession, "form": form, "filed": filed}
        for r in parse_form4(xml)
    ]
    if not rows:
        return 0
    stmt = pg_insert(InsiderTransaction).values(rows).on_conflict_do_nothing()
    session.execute(stmt)
    return len(rows)


def _insert_holder(
    session: Session, ticker: str, accession: str, form: str, filed: dt.date, xml: str
) -> int:
    parsed = parse_schedule13(xml)
    if parsed is None:
        return 0
    stmt = pg_insert(HolderFiling).values(
        {
            **parsed,
            # Empty rather than null when the filing names no class: null marks a row stored
            # before the class was recorded, which the next fetch fills.
            "share_class": parsed["share_class"] or "",
            "ticker": ticker,
            "accession": accession,
            "form": form,
            "filed": filed,
        }
    )
    session.execute(stmt.on_conflict_do_nothing())
    return 1


def ownership_tickers(session: Session) -> list[str]:
    """The names EDGAR covers: the universe's US stocks and the watchlist's US stocks. ETFs are left
    out, since a fund has no officers trading its units, and JSE companies do not file with the SEC.
    """
    from quantpulse.data.calendar import EXCHANGES
    from quantpulse.db import UniverseMember
    from quantpulse.research.watchlist import load_watchlist

    us = [code for code, ex in EXCHANGES.items() if ex.has_options]
    universe = session.scalars(
        select(UniverseMember.ticker)
        .where(
            UniverseMember.active.is_(True),
            UniverseMember.asset_type == "stock",
            UniverseMember.exchange.in_(us),
        )
        .order_by(UniverseMember.ticker)
    )
    watch = [n.ticker for n in load_watchlist() if n.has_options and n.asset_type == "stock"]
    return [*universe, *watch]
