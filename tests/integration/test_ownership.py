"""Ownership filings from SEC EDGAR, end to end against a fake EDGAR (ADR 0007).

What has to hold:
- each new filing is stored once; a second run fetches nothing it already has;
- a document that fails to read is left out and fetched again next run;
- every filing list failing is an error, one failing is not;
- open-market trades only count as buying and selling, and planned sales are measured by value;
- a holder's latest filing decides whether it is over 5%, so an exit amendment removes it.
"""

import datetime as dt
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from edgar_docs import form4, schedule13d, schedule13g
from quantpulse.api.app import create_app
from quantpulse.api.deps import engine_dep, session_dep
from quantpulse.data.universe import UniverseEntry, sync_universe
from quantpulse.research.ownership import (
    SUBMISSIONS_URL,
    TICKERS_URL,
    NoOwnershipReturned,
    refresh_ownership,
)

pytestmark = pytest.mark.integration

TODAY = dt.date(2026, 10, 16)
CIK = {"AAPL": 320193, "GME": 1326380}


def _filing(accession: str, filed: str, form: str, doc: str = "primary_doc.xml") -> dict[str, str]:
    return {"accessionNumber": accession, "filingDate": filed, "form": form, "primaryDocument": doc}


FILINGS = {
    "AAPL": [
        _filing("0001-26-000001", "2026-10-14", "4", "xslF345X06/form4.xml"),
        _filing(
            "0001-26-000002", "2026-03-26", "SCHEDULE 13G", "xslSCHEDULE_13G_X02/primary_doc.xml"
        ),
    ],
    "GME": [
        _filing("0002-26-000001", "2026-10-13", "4", "xslF345X06/form4.xml"),
        _filing("0002-26-000002", "2026-05-04", "SCHEDULE 13D"),
        _filing("0002-26-000003", "2026-10-13", "SCHEDULE 13D/A"),
        _filing("0002-26-000004", "2025-04-02", "SCHEDULE 13G"),
        _filing("0002-26-000005", "2026-01-23", "SCHEDULE 13G/A"),  # the same holder's exit
        _filing("0002-26-000006", "2026-07-17", "SCHEDULE 13D/A"),
        _filing("0002-26-000007", "2026-10-01", "4", "xslF345X06/form4.xml"),
    ],
}

DOCS = {
    "0001-26-000001": form4(
        ("2026-10-10", "S", 10000, 250.0),  # planned sale
        ("2026-10-10", "F", 3000, 250.0),  # shares withheld for tax: pay, not a decision
        issuer=CIK["AAPL"],
    ),
    "0001-26-000002": schedule13g("Vanguard Capital Management", 7.48, 1.1e9, CIK["AAPL"]),
    "0002-26-000001": form4(("2026-10-12", "P", 1000, 25.0), issuer=CIK["GME"], planned="0"),
    "0002-26-000002": schedule13d("Cohen Ryan", 8.6, 4.0e7, CIK["GME"], "05/01/2026"),
    "0002-26-000003": schedule13d("Cohen Ryan", 9.1, 4.6e7, CIK["GME"]),
    "0002-26-000004": schedule13g("BlackRock Inc.", 6.2, 2.7e7, CIK["GME"], "03/31/2025"),
    "0002-26-000005": schedule13g("BlackRock Inc.", 4.1, 1.8e7, CIK["GME"], "12/31/2025"),
    # GameStop's own 13D about another company: on its filing list, but not about GameStop.
    "0002-26-000006": schedule13d("GameStop Corp.", 9.8, 1.0e7, 999999),
    # A Form 4 with only option lines: nothing in common stock to store.
    "0002-26-000007": form4(issuer=CIK["GME"]),
}


class FakeEdgar:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.broken: set[str] = set()
        self.lists_fail = False

    def get_json(self, url: str) -> Any:
        self.calls.append(url)
        if url == TICKERS_URL:
            return {str(i): {"ticker": t, "cik_str": c} for i, (t, c) in enumerate(CIK.items())}
        if self.lists_fail:
            raise RuntimeError("EDGAR down")
        ticker = next(t for t, c in CIK.items() if url == SUBMISSIONS_URL.format(cik=c))
        rows = FILINGS[ticker]
        keys = ("accessionNumber", "filingDate", "form", "primaryDocument")
        return {"filings": {"recent": {k: [r[k] for r in rows] for k in keys}}}

    def get_text(self, url: str) -> str:
        self.calls.append(url)
        accession = next(a for a in DOCS if a.replace("-", "") in url)
        if accession in self.broken:
            raise RuntimeError("document unreadable")
        return DOCS[accession]


@pytest.fixture
def session_factory(db_engine: Engine) -> Callable[[], Any]:
    @contextmanager
    def make() -> Iterator[Session]:
        with Session(db_engine) as s:
            yield s
            s.commit()

    return make


def _count(engine: Engine, table: str) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text(f"SELECT count(*) FROM {table}")).scalar() or 0)


def test_each_filing_is_stored_once_and_a_rerun_fetches_nothing_new(
    db_engine: Engine, session_factory: Callable[[], Any]
) -> None:
    edgar = FakeEdgar()
    report = refresh_ownership(session_factory, ["AAPL", "GME", "SPY-NO-CIK"], edgar, TODAY)
    assert (report.trades, report.holder_filings, report.no_cik) == (3, 5, ["SPY-NO-CIK"])
    assert _count(db_engine, "insider_transactions") == 3
    assert _count(db_engine, "holder_filings") == 5
    assert any("/320193/000126000001/form4.xml" in c for c in edgar.calls), "raw XML, not the view"

    assert report.other_issuer == 1
    with db_engine.connect() as conn:
        outcomes = dict(conn.execute(text("SELECT accession, outcome FROM edgar_filings")).all())
    assert outcomes["0002-26-000006"] == "other issuer"
    assert outcomes["0002-26-000007"] == "nothing"

    again = FakeEdgar()
    refresh_ownership(session_factory, ["AAPL", "GME"], again, TODAY)
    assert not [c for c in again.calls if "Archives" in c], (
        "no filing already read is fetched again, including one about another company"
    )


def test_an_unreadable_document_is_fetched_again_next_run(
    db_engine: Engine, session_factory: Callable[[], Any]
) -> None:
    edgar = FakeEdgar()
    edgar.broken = {"0002-26-000003"}
    refresh_ownership(session_factory, ["GME"], edgar, TODAY)
    assert _count(db_engine, "holder_filings") == 3
    refresh_ownership(session_factory, ["GME"], FakeEdgar(), TODAY)
    assert _count(db_engine, "holder_filings") == 4


def test_every_list_failing_is_an_error_but_one_ticker_without_a_cik_is_not(
    session_factory: Callable[[], Any],
) -> None:
    edgar = FakeEdgar()
    edgar.lists_fail = True
    with pytest.raises(NoOwnershipReturned):
        refresh_ownership(session_factory, ["AAPL", "GME"], edgar, TODAY)
    assert refresh_ownership(session_factory, ["NOPE"], FakeEdgar(), TODAY).no_cik == ["NOPE"]


@pytest.fixture(scope="module")
def client(test_db_url: str, dbt_build: Callable[..., None]) -> Iterator[TestClient]:
    engine = create_engine(test_db_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE insider_transactions, holder_filings, edgar_filings, watchlist, universe "
                "RESTART IDENTITY CASCADE"
            )
        )
    with Session(engine) as session:
        sync_universe(session, [UniverseEntry("AAPL", "stock")])
        session.execute(
            text(
                "INSERT INTO watchlist (ticker, exchange, asset_type, why) "
                "VALUES ('GME', 'XNYS', 'stock', 'The 2021 squeeze.')"
            )
        )
        session.commit()

    @contextmanager
    def make() -> Iterator[Session]:
        with Session(engine) as s:
            yield s
            s.commit()

    refresh_ownership(make, ["AAPL", "GME"], FakeEdgar(), TODAY)
    dbt_build(test_db_url, "+fct_ownership +fct_insider_trades +fct_large_holders")

    app = create_app()
    app.dependency_overrides[engine_dep] = lambda: engine

    def _session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[session_dep] = _session
    yield TestClient(app)
    engine.dispose()


def test_only_open_market_trades_count_and_planned_sales_are_measured(client: TestClient) -> None:
    rows = {r["ticker"]: r for r in client.get("/research/ownership").json()["rows"]}
    aapl, gme = rows["AAPL"], rows["GME"]
    assert aapl["sold_usd_90d"] == pytest.approx(2_500_000), "the tax withholding is left out"
    assert aapl["planned_sold_share_90d"] == pytest.approx(1.0)
    assert (gme["bought_usd_90d"], gme["buyers_90d"], gme["followed_by"]) == (
        25_000,
        1,
        "watchlist",
    )


def test_a_holders_latest_filing_decides_and_an_exit_removes_it(client: TestClient) -> None:
    rows = {r["ticker"]: r for r in client.get("/research/ownership").json()["rows"]}
    gme = rows["GME"]
    assert (gme["holders_over_5pct"], gme["top_holder"], gme["top_holder_percent"]) == (
        1,
        "Cohen Ryan",
        9.1,
    ), "BlackRock's latest filing reports 4.1%, so it has exited; Cohen's latest is 9.1%"
    assert gme["activist_holder"] is True
    detail = client.get("/research/ownership/gme").json()
    assert [(h["filer"], h["percent"]) for h in detail["holders"]] == [("Cohen Ryan", 9.1)]
    assert [(t["trade"], t["value_usd"]) for t in detail["trades"]] == [("bought", 25_000)]


def test_a_jse_market_has_no_ownership_rows(client: TestClient) -> None:
    assert client.get("/research/ownership?exchange=XJSE").json()["rows"] == []
