"""Public attention per stock, from daily Wikipedia page views (ADR 0007).

Attention is the part of a squeeze that arrives all at once: GameStop's article went from about
a thousand views a day in early January 2021 to 174,157 on the 28th. Of the sources that measure
it, Wikimedia's page-view API is the one that is free, needs no key, has daily history back to
2015, and covers JSE companies as well as US ones. (Google Trends' API is an application-only
alpha; GDELT's news API refused requests from here with HTTP 429, even one a minute.)

Two properties of the API shape this module:

- **It counts the exact title, not its redirects.** A title that has become a redirect returns a
  small, plausible number that is simply wrong. So every run resolves the titles first and skips
  any that is not a canonical article, naming it, rather than storing the wrong count.
- **Days are UTC, and a day is published once it has ended.** The newest day asked for is
  yesterday in UTC; a day not yet published is fetched on the next run.
"""

import datetime as dt
import logging
import urllib.parse
from collections.abc import Callable, Iterable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import yaml
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from quantpulse.db import PageView
from quantpulse.utils import chunked

logger = logging.getLogger(__name__)

USER_AGENT = "quantpulse/0.1 (https://github.com/enkay-pixel/quantpulse)"
WIKI_API = "https://en.wikipedia.org/w/api.php"
PAGEVIEWS = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/"
    "user/{article}/daily/{start}/{end}"
)
#: Where an empty history starts: the price history begins in 2018, and nothing earlier is read.
BACKFILL_START = dt.date(2018, 1, 1)


class Http(Protocol):
    def get_json(self, url: str, params: Mapping[str, str] | None = None) -> tuple[int, Any]: ...


class HttpxClient:
    """The real client. Wikimedia asks every caller to identify itself in the User-Agent."""

    def __init__(self) -> None:
        import httpx

        self._client = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=30,
            transport=httpx.HTTPTransport(retries=2),
        )

    def get_json(self, url: str, params: Mapping[str, str] | None = None) -> tuple[int, Any]:
        response = self._client.get(url, params=dict(params) if params else None)
        try:
            body = response.json()
        except ValueError:
            body = None
        return response.status_code, body


class NoPageViewsReturned(RuntimeError):
    """Every title that should have had views failed to return any. One failure is ordinary;
    all of them means the API changed or is unreachable."""


def load_titles(path: Path) -> dict[str, str]:
    data = yaml.safe_load(path.read_text())
    titles = data.get("titles", {}) if isinstance(data, dict) else {}
    return {str(ticker): str(title) for ticker, title in titles.items()}


def article_path(title: str) -> str:
    """The title as the page-view API wants it in a URL: underscores, then percent-encoded, so
    "Johnson & Johnson" and "AT&T" survive."""
    return urllib.parse.quote(title.replace(" ", "_"), safe="")


def resolve_titles(titles: Iterable[str], http: Http) -> dict[str, str]:
    """Each title's state: "ok", "redirect", "disambiguation" or "missing".

    "redirect" also covers a title that only differs from the article by normalization: the
    page-view API matches the exact string, so anything other than the canonical form undercounts.
    """
    titles = list(dict.fromkeys(titles))
    states: dict[str, str] = {}
    for batch in chunked(titles, 50):  # the MediaWiki API's limit per query
        status, body = http.get_json(
            WIKI_API,
            {
                "action": "query",
                "titles": "|".join(batch),
                "redirects": "1",
                "prop": "pageprops",
                "format": "json",
            },
        )
        if status != 200 or not isinstance(body, dict) or "query" not in body:
            raise NoPageViewsReturned(f"could not resolve titles: HTTP {status}")
        query = body["query"]
        renamed = {n["from"]: n["to"] for n in query.get("normalized", [])}
        renamed |= {r["from"]: r["to"] for r in query.get("redirects", [])}
        pages = {p.get("title"): p for p in query.get("pages", {}).values()}
        for title in batch:
            page = pages.get(title)
            if title in renamed:
                states[title] = "redirect"
            elif page is None or "missing" in page:
                states[title] = "missing"
            elif "disambiguation" in page.get("pageprops", {}):
                states[title] = "disambiguation"
            else:
                states[title] = "ok"
    return states


def parse_pageviews(ticker: str, title: str, body: Any) -> list[dict[str, Any]]:
    """Rows from one page-view response. A day absent from the response is absent here too:
    missing is not zero."""
    rows = []
    for item in body.get("items", []) if isinstance(body, dict) else []:
        stamp = str(item.get("timestamp", ""))
        views = item.get("views")
        if len(stamp) < 8 or not stamp[:8].isdigit() or not isinstance(views, int) or views < 0:
            continue
        day = dt.date(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:8]))
        rows.append({"ticker": ticker, "date": day, "article": title, "views": views})
    return rows


def insert_page_views(session: Session, rows: list[dict[str, Any]]) -> int:
    """Insert rows not already stored; returns how many were new. Never rewrites a stored day."""
    new = 0
    for batch in chunked(rows):
        result = session.execute(
            insert(PageView)
            .values(list(batch))
            .on_conflict_do_nothing(index_elements=[PageView.ticker, PageView.date])
            .returning(PageView.ticker)
        )
        new += len(result.all())
    return new


@dataclass
class RefreshReport:
    fetched: int = 0
    new_rows: int = 0
    up_to_date: int = 0
    skipped: dict[str, str] = field(default_factory=dict)  # ticker -> title state
    failed: dict[str, str] = field(default_factory=dict)  # ticker -> reason


def refresh_page_views(
    session_factory: Callable[[], AbstractContextManager[Session]],
    titles: Mapping[str, str],
    http: Http | None = None,
    today: dt.date | None = None,
) -> RefreshReport:
    """Fetch every ticker's views from the day after its newest stored one through yesterday.

    One ticker at a time, committed as it goes, so a first run that backfills years of history
    holds one ticker's rows in memory rather than every ticker's.
    """
    http = http or HttpxClient()
    # Wikimedia's days are UTC, so "yesterday" is too — not any exchange's date.
    end = (today or dt.datetime.now(dt.UTC).date()) - dt.timedelta(days=1)
    states = resolve_titles(titles.values(), http)
    report = RefreshReport()
    for ticker, title in titles.items():
        if states.get(title) != "ok":
            report.skipped[ticker] = states.get(title, "missing")
            logger.warning("skipping %s: %r is %s", ticker, title, report.skipped[ticker])
            continue
        with session_factory() as session:
            newest = session.scalar(
                select(func.max(PageView.date)).where(PageView.ticker == ticker)
            )
        start = newest + dt.timedelta(days=1) if newest else BACKFILL_START
        if start > end:
            report.up_to_date += 1
            continue
        url = PAGEVIEWS.format(
            article=article_path(title), start=start.strftime("%Y%m%d"), end=end.strftime("%Y%m%d")
        )
        try:
            status, body = http.get_json(url)
        except Exception as exc:  # one ticker's failure must not cost the others
            report.failed[ticker] = type(exc).__name__
            continue
        if status == 404:
            # No published day in the range yet: ordinary for a one-day window early in the day.
            report.up_to_date += 1
            continue
        if status != 200:
            report.failed[ticker] = f"HTTP {status}"
            continue
        rows = parse_pageviews(ticker, title, body)
        with session_factory() as session:
            report.new_rows += insert_page_views(session, rows)
        report.fetched += 1
    if report.failed:
        logger.warning("page views failed for %s", report.failed)
    resolvable = len(titles) - len(report.skipped)
    if resolvable and len(report.failed) == resolvable:
        raise NoPageViewsReturned(f"every one of {resolvable} titles failed: {report.failed}")
    return report
