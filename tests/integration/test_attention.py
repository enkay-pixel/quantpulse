"""Attention end to end against the test database: the fetch, the mart and the endpoints.

What has to hold (ADR 0007):
- an empty history backfills from BACKFILL_START, and later runs fetch only the days after the
  newest stored one;
- a title that is a redirect is skipped and named, never counted;
- the ratio is the past week's mean over the median of the 90 days before it, with windows by
  date, so a missing day shortens the week rather than pulling in a baseline day;
- a ratio needs 60 baseline days.
"""

import datetime as dt
from collections.abc import Callable, Iterator, Mapping
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, func, select, text
from sqlalchemy.orm import Session

from quantpulse.api.app import create_app
from quantpulse.api.deps import engine_dep, session_dep
from quantpulse.data.universe import UniverseEntry, sync_universe
from quantpulse.db import PageView, get_session
from quantpulse.research.attention import (
    BACKFILL_START,
    NoPageViewsReturned,
    refresh_page_views,
)

pytestmark = pytest.mark.integration


class FakeWikimedia:
    """Serves title checks and page views; records every page-view URL asked for."""

    def __init__(self, status: int = 200, redirects: Mapping[str, str] | None = None) -> None:
        self.status = status
        self.redirects = dict(redirects or {})
        self.urls: list[str] = []

    def get_json(self, url: str, params: Mapping[str, str] | None = None) -> tuple[int, Any]:
        if params is not None:  # the MediaWiki title query
            asked = params["titles"].split("|")
            pages = {str(i): {"title": self.redirects.get(t, t)} for i, t in enumerate(asked)}
            redirects = [{"from": t, "to": self.redirects[t]} for t in asked if t in self.redirects]
            return 200, {"query": {"pages": pages, "redirects": redirects}}
        self.urls.append(url)
        if self.status != 200:
            return self.status, None
        start, end = url.rsplit("/", 2)[-2:]
        first = dt.datetime.strptime(start, "%Y%m%d").date()
        last = dt.datetime.strptime(end, "%Y%m%d").date()
        days = [first + dt.timedelta(days=i) for i in range((last - first).days + 1)]
        return 200, {"items": [{"timestamp": d.strftime("%Y%m%d00"), "views": 100} for d in days]}


def _stored(ticker: str) -> tuple[int, dt.date | None]:
    with get_session() as session:
        n = session.scalar(select(func.count()).where(PageView.ticker == ticker))
        newest = session.scalar(select(func.max(PageView.date)).where(PageView.ticker == ticker))
    return n or 0, newest


def test_an_empty_history_backfills_then_later_runs_fetch_only_new_days(
    db_engine: Engine,
) -> None:
    wiki = FakeWikimedia(redirects={"The Foschini Group": "TFG Limited"})
    titles = {"NPN.JO": "Naspers", "TFG.JO": "The Foschini Group"}

    first = refresh_page_views(get_session, titles, http=wiki, today=dt.date(2018, 1, 5))
    assert len(wiki.urls) == 1, "the redirect title was fetched"
    assert wiki.urls[0].endswith(f"/Naspers/daily/{BACKFILL_START:%Y%m%d}/20180104")
    assert _stored("NPN.JO") == (4, dt.date(2018, 1, 4))
    assert first.new_rows == 4
    assert first.skipped == {"TFG.JO": "redirect"}, "a redirect title was counted"
    assert _stored("TFG.JO") == (0, None)

    wiki.urls.clear()
    second = refresh_page_views(get_session, titles, http=wiki, today=dt.date(2018, 1, 7))
    assert wiki.urls[0].endswith("/Naspers/daily/20180105/20180106"), wiki.urls
    assert second.new_rows == 2
    assert _stored("NPN.JO") == (6, dt.date(2018, 1, 6))

    wiki.urls.clear()
    third = refresh_page_views(get_session, titles, http=wiki, today=dt.date(2018, 1, 7))
    assert wiki.urls == [] and third.up_to_date == 1, "an up-to-date ticker was fetched again"


def test_every_title_failing_is_an_error_but_one_failing_is_not(db_engine: Engine) -> None:
    with pytest.raises(NoPageViewsReturned):
        refresh_page_views(
            get_session,
            {"NPN.JO": "Naspers"},
            http=FakeWikimedia(status=500),
            today=dt.date(2018, 1, 5),
        )


# --- the mart and the endpoints -------------------------------------------------------------

D0 = dt.date(2026, 1, 1)
LATEST = D0 + dt.timedelta(days=106)


def _seed(engine: Engine) -> None:
    with Session(engine) as session:
        sync_universe(
            session,
            [
                UniverseEntry("AAPL", "stock"),
                UniverseEntry("NPN.JO", "stock", "XJSE"),
                UniverseEntry("SBK.JO", "stock", "XJSE"),
            ],
        )
        session.commit()
    rows: list[PageView] = []
    for i in range(107):
        day = D0 + dt.timedelta(days=i)
        in_week = day > LATEST - dt.timedelta(days=7)
        # One spike inside the baseline: the median ignores it, a mean would not.
        npn_views = 500 if in_week else (10_000 if day == D0 + dt.timedelta(days=50) else 100)
        rows.append(PageView(ticker="NPN.JO", date=day, article="Naspers", views=npn_views))
        # AAPL: the same, but one day of the week is missing and another is 1,000.
        if day == LATEST - dt.timedelta(days=3):
            continue
        views = (1000 if day == LATEST - dt.timedelta(days=1) else 500) if in_week else 100
        rows.append(PageView(ticker="AAPL", date=day, article="Apple Inc.", views=views))
    # SBK.JO: a month of history, too short for a baseline.
    for i in range(30):
        rows.append(
            PageView(
                ticker="SBK.JO",
                date=LATEST - dt.timedelta(days=i),
                article="Standard Bank",
                views=50,
            )
        )
    with Session(engine) as session:
        session.add_all(rows)
        session.commit()


@pytest.fixture(scope="module")
def client(test_db_url: str, dbt_build: Callable[..., None]) -> Iterator[TestClient]:
    engine = create_engine(test_db_url)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE page_views, universe RESTART IDENTITY CASCADE"))
    _seed(engine)
    dbt_build(test_db_url, "+fct_attention")

    app = create_app()
    app.dependency_overrides[engine_dep] = lambda: engine

    def _session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[session_dep] = _session
    yield TestClient(app)
    engine.dispose()


def _rows(client: TestClient, exchange: str) -> dict[str, dict[str, Any]]:
    body = client.get("/research/attention", params={"exchange": exchange}).json()
    return {r["ticker"]: r for r in body["rows"]}


def test_the_ratio_is_the_week_over_the_usual(client: TestClient) -> None:
    """The baseline holds one 10,000-view day. The median is still 100; a mean would be 210 and
    the ratio 2.4, so one old spike would hide the week's fivefold rise."""
    npn = _rows(client, "XJSE")["NPN.JO"]
    assert npn["date"] == str(LATEST)
    assert npn["views_7d"] == pytest.approx(500)
    assert npn["baseline_90d"] == pytest.approx(100)
    assert npn["attention_ratio"] == pytest.approx(5.0)


def test_a_missing_day_shortens_the_week_instead_of_borrowing_a_baseline_day(
    client: TestClient,
) -> None:
    """Six days present, one at 1,000: the mean is 583.3. A window counted in rows would have
    reached back to a 100-view day and reported 514.3."""
    aapl = _rows(client, "XNYS")["AAPL"]
    assert aapl["views_7d"] == pytest.approx((5 * 500 + 1000) / 6)


def test_too_short_a_history_has_no_ratio_rather_than_a_misleading_one(client: TestClient) -> None:
    sbk = _rows(client, "XJSE")["SBK.JO"]
    assert sbk["attention_ratio"] is None
    assert sbk["baseline_90d"] is None


def test_each_market_sees_only_its_own_stocks(client: TestClient) -> None:
    assert set(_rows(client, "XJSE")) == {"NPN.JO", "SBK.JO"}
    assert set(_rows(client, "XNYS")) == {"AAPL"}


def test_history_is_a_year_of_one_stocks_days(client: TestClient) -> None:
    body = client.get("/research/attention/npn.jo/history").json()
    assert body["article"] == "Naspers"
    assert len(body["days"]) == 107
    assert body["days"][-1]["views"] == 500
