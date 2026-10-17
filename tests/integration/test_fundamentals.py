"""Company fundamentals from SEC XBRL, end to end (ADR 0007).

What has to hold, each from something the live data showed:
- a company's facts are fetched again for a new statement, and a statement the facts document
  lacks (Coca-Cola's) is retried weekly, not daily;
- twelve months = last fiscal year + this year so far - the same months a year earlier;
- the tag a company uses now wins over one it dropped (Apple), and two tags filed together for
  different things resolve to the broader one every period (Berkshire);
- a ratio divides figures over the same months, so annual-only revenue (banks) is not set
  against a later profit;
- market value needs a current whole-company share count, or it is left empty.
"""

import datetime as dt
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from quantpulse.api.app import create_app
from quantpulse.api.deps import engine_dep, session_dep
from quantpulse.data.universe import UniverseEntry, sync_universe
from quantpulse.db import FinancialFact, Price
from quantpulse.research.fundamentals import FACTS_URL, refresh_fundamentals
from quantpulse.research.ownership import SUBMISSIONS_URL, TICKERS_URL

pytestmark = pytest.mark.integration

NOW = dt.datetime(2026, 10, 17, 12, tzinfo=dt.UTC)


class FakeEdgar:
    def __init__(self, newest: str = "q2", facts_accessions: tuple[str, ...] = ("q2",)) -> None:
        self.newest = newest
        self.facts_accessions = facts_accessions
        self.facts_calls = 0

    def get_json(self, url: str) -> Any:
        if url == TICKERS_URL:
            return {"0": {"ticker": "AAA", "cik_str": 1}}
        if url == SUBMISSIONS_URL.format(cik=1):
            return {"filings": {"recent": {"form": ["10-Q"], "accessionNumber": [self.newest]}}}
        assert url == FACTS_URL.format(cik=1)
        self.facts_calls += 1
        return {
            "facts": {
                "us-gaap": {
                    "Revenues": {
                        "units": {
                            "USD": [
                                {
                                    "start": "2026-01-01",
                                    "end": "2026-06-30",
                                    "val": 60.0,
                                    "accn": a,
                                    "fy": 2026,
                                    "fp": "Q2",
                                    "form": "10-Q",
                                    "filed": "2026-07-31",
                                }
                                for a in self.facts_accessions
                            ]
                        }
                    }
                }
            }
        }

    def get_text(self, url: str) -> str:
        raise AssertionError("no document is read as text here")


@pytest.fixture
def make_session(db_engine: Engine) -> Callable[[], Any]:
    @contextmanager
    def make() -> Iterator[Session]:
        with Session(db_engine) as s:
            yield s
            s.commit()

    return make


def test_a_new_statement_is_fetched_and_one_the_document_lacks_is_retried_weekly(
    make_session: Callable[[], Any],
) -> None:
    lagging = FakeEdgar(newest="q3", facts_accessions=("q2",))
    first = refresh_fundamentals(make_session, ["AAA"], lagging, NOW)
    assert first.refreshed == ["AAA"] and first.lagging == ["AAA"]
    refresh_fundamentals(make_session, ["AAA"], lagging, NOW + dt.timedelta(days=1))
    assert lagging.facts_calls == 1, "not again the next day"
    refresh_fundamentals(make_session, ["AAA"], lagging, NOW + dt.timedelta(days=8))
    assert lagging.facts_calls == 2, "again a week later"
    caught_up = FakeEdgar(newest="q3", facts_accessions=("q2", "q3"))
    refresh_fundamentals(make_session, ["AAA"], caught_up, NOW + dt.timedelta(days=16))
    refresh_fundamentals(make_session, ["AAA"], caught_up, NOW + dt.timedelta(days=30))
    assert caught_up.facts_calls == 1, "once the statement is stored, nothing until the next"
    newer = FakeEdgar(newest="k4", facts_accessions=("q2", "q3"))
    refresh_fundamentals(make_session, ["AAA"], newer, NOW + dt.timedelta(days=31))
    assert newer.facts_calls == 1, "a new statement is fetched at once"


def _f(
    ticker: str, concept: str, start: str | None, end: str, value: float, filed: str, accession: str
) -> FinancialFact:
    s = dt.date.fromisoformat(start) if start else None
    e = dt.date.fromisoformat(end)
    return FinancialFact(
        ticker=ticker,
        concept=concept,
        unit="USD",
        period_end=e,
        duration_days=(e - s).days if s else 0,
        period_start=s,
        value=value,
        form="10-Q",
        filed=dt.date.fromisoformat(filed),
        accession=accession,
    )


FY = ("2025-01-01", "2025-12-31")
YTD = ("2026-01-01", "2026-06-30")
PRIOR_YTD = ("2025-01-01", "2025-06-30")
RFC = "RevenueFromContractWithCustomerExcludingAssessedTax"


@pytest.fixture(scope="module")
def client(test_db_url: str, dbt_build: Callable[..., None]) -> Iterator[TestClient]:
    engine = create_engine(test_db_url)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE financial_facts, prices, universe RESTART IDENTITY CASCADE"))
    with Session(engine) as session:
        sync_universe(session, [UniverseEntry(t, "stock") for t in ("AAA", "BBB", "CCC")])
        session.commit()
    with Session(engine) as session:
        facts = [
            # AAA: moved from `Revenues` (last used 2019) to the contract-revenue tag.
            _f("AAA", "Revenues", "2018-01-01", "2018-12-31", 70, "2019-02-01", "k18"),
            _f("AAA", RFC, *FY, 100, "2026-02-01", "k25"),
            _f("AAA", RFC, *YTD, 60, "2026-07-31", "q26"),
            _f("AAA", RFC, *PRIOR_YTD, 50, "2026-07-31", "q26"),
            _f("AAA", "OperatingIncomeLoss", *FY, 20, "2026-02-01", "k25"),
            _f("AAA", "OperatingIncomeLoss", *YTD, 12, "2026-07-31", "q26"),
            _f("AAA", "OperatingIncomeLoss", *PRIOR_YTD, 10, "2026-07-31", "q26"),
            _f("AAA", "EarningsPerShareDiluted", *FY, 2.0, "2026-02-01", "k25"),
            _f("AAA", "EarningsPerShareDiluted", *YTD, 1.2, "2026-07-31", "q26"),
            _f("AAA", "EarningsPerShareDiluted", *PRIOR_YTD, 1.0, "2026-07-31", "q26"),
            _f(
                "AAA",
                "EntityCommonStockSharesOutstanding",
                None,
                "2026-07-20",
                10,
                "2026-07-31",
                "q26",
            ),
            # BBB: files its total and a part of it under two tags in the same statements.
            *[
                _f("BBB", concept, *period, value, filed, acc)
                for concept, scale in (("Revenues", 3), (RFC, 2))
                for period, value, filed, acc in (
                    (FY, 100 * scale, "2026-02-01", "k25b"),
                    (YTD, 60 * scale, "2026-07-31", "q26b"),
                    (PRIOR_YTD, 50 * scale, "2026-07-31", "q26b"),
                )
            ],
            # BBB's only share count is years old, as for a company with several classes.
            _f(
                "BBB",
                "EntityCommonStockSharesOutstanding",
                None,
                "2020-02-01",
                99,
                "2020-03-01",
                "k19b",
            ),
            # CCC, a bank: revenue only yearly, profit quarterly.
            _f("CCC", "Revenues", *FY, 100, "2026-02-01", "k25c"),
            _f("CCC", "Revenues", "2024-01-01", "2024-12-31", 90, "2026-02-01", "k25c"),
            _f("CCC", "NetIncomeLoss", *FY, 30, "2026-02-01", "k25c"),
            _f("CCC", "NetIncomeLoss", *YTD, 20, "2026-07-31", "q26c"),
            _f("CCC", "NetIncomeLoss", *PRIOR_YTD, 15, "2026-07-31", "q26c"),
        ]
        session.add_all(facts)
        for ticker in ("AAA", "BBB", "CCC"):
            day = pd.Timestamp("2026-10-16").date()
            session.add(
                Price(
                    ticker=ticker,
                    date=day,
                    open=20,
                    high=20,
                    low=20,
                    close=20,
                    volume=1,
                    source="yfinance",
                )
            )
        session.commit()
    dbt_build(test_db_url, "+fct_fundamentals")

    app = create_app()
    app.dependency_overrides[engine_dep] = lambda: engine

    def _session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[session_dep] = _session
    yield TestClient(app)
    engine.dispose()


def _rows(client: TestClient) -> dict[str, dict[str, Any]]:
    return {r["ticker"]: r for r in client.get("/research/fundamentals").json()["rows"]}


def test_twelve_months_is_the_year_plus_this_year_so_far_less_the_same_months_before(
    client: TestClient,
) -> None:
    aaa = _rows(client)["AAA"]
    assert aaa["revenue_ttm"] == pytest.approx(110), "100 + 60 - 50, from the tag in use now"
    assert aaa["revenue_growth"] == pytest.approx(0.2)
    assert aaa["revenue_growth_basis"] == "year to date"
    assert aaa["operating_margin"] == pytest.approx(22 / 110)


def test_market_value_needs_a_current_share_count(client: TestClient) -> None:
    rows = _rows(client)
    assert rows["AAA"]["market_cap"] == pytest.approx(200)
    assert rows["AAA"]["pe_ratio"] == pytest.approx(20 / 2.2)
    assert rows["BBB"]["market_cap"] is None, "a count from 2020 is not current"


def test_two_tags_filed_together_resolve_to_the_broader_one_every_period(
    client: TestClient,
) -> None:
    assert _rows(client)["BBB"]["revenue_ttm"] == pytest.approx(330), "300 + 180 - 150, all totals"


def test_a_ratio_never_sets_this_years_profit_against_last_years_revenue(
    client: TestClient,
) -> None:
    ccc = _rows(client)["CCC"]
    assert ccc["revenue_growth_basis"] == "fiscal year"
    assert ccc["revenue_growth"] == pytest.approx(100 / 90 - 1)
    assert ccc["net_income_ttm"] == pytest.approx(35)
    assert ccc["net_margin"] == pytest.approx(30 / 100), "fiscal year against fiscal year"


def test_the_brief_reads_the_business_figures(client: TestClient) -> None:
    facts = {f["fact"]: f["value"] for f in client.get("/research/brief/AAA").json()["facts"]}
    assert facts["Revenue, 12 months"] == "$110, +20% on a year earlier"
    assert facts["Operating margin"] == "20%"


def test_a_jse_market_has_no_rows(client: TestClient) -> None:
    assert client.get("/research/fundamentals?exchange=XJSE").json()["rows"] == []
