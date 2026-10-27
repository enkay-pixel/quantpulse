"""Wikipedia attention without the network: title checks, URL encoding and response parsing."""

import datetime as dt
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from quantpulse.research.attention import (
    article_path,
    load_titles,
    parse_pageviews,
    resolve_titles,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class FakeWiki:
    """Answers the MediaWiki title query the way the real API does for a known set of pages."""

    def __init__(self, pages: dict[str, dict[str, Any]], redirects: dict[str, str]) -> None:
        self.pages = pages
        self.redirects = redirects

    def get_json(self, url: str, params: Mapping[str, str] | None = None) -> tuple[int, Any]:
        assert params is not None
        asked = params["titles"].split("|")
        redirects = [{"from": t, "to": self.redirects[t]} for t in asked if t in self.redirects]
        finals = {self.redirects.get(t, t) for t in asked}
        pages = {
            str(i): {"title": t, **self.pages.get(t, {"missing": ""})} for i, t in enumerate(finals)
        }
        return 200, {"query": {"redirects": redirects, "pages": pages}}


def test_every_configured_title_loads_as_a_string() -> None:
    titles = load_titles(PROJECT_ROOT / "configs/attention.yaml")
    suffixes = {
        "XJSE": ".JO",
        "XLON": ".L",
        "XETR": ".DE",
        "XPAR": ".PA",
        "XSWX": ".SW",
        "XAMS": ".AS",
    }
    by_market = {m: [k for k in titles if k.endswith(s)] for m, s in suffixes.items()}
    by_market["XNYS"] = [k for k in titles if "." not in k or k == "BRK-B"]
    # Every stock in each market has a title, less the six European companies with no English
    # article; a drop here is a title lost, not a count to update.
    assert {m: len(v) for m, v in by_market.items()} == {
        "XJSE": 28,
        "XLON": 40,
        "XNYS": 40,
        "XETR": 40,
        "XPAR": 40,
        "XSWX": 36,
        "XAMS": 25,
    }
    assert all(isinstance(t, str) and t and t != "None" for t in titles.values())


def test_a_company_with_no_english_article_is_named_not_counted(tmp_path: Path) -> None:
    """`null` is a decision that no article stands for the company. It must not become the string
    "None", which the fetch would then look up as a title."""
    from quantpulse.research.attention import without_article

    f = tmp_path / "attention.yaml"
    f.write_text("titles:\n  ASML.AS: ASML\n  IMCD.AS: null  # no English article\n")
    assert load_titles(f) == {"ASML.AS": "ASML"}
    assert without_article(f) == {"IMCD.AS"}
    configured = without_article(PROJECT_ROOT / "configs/attention.yaml")
    assert configured == {"HBAN.SW", "IMCD.AS", "TWEKA.AS", "BFIT.AS", "OCI.AS", "AMG.AS"}


def test_titles_with_ampersands_and_spaces_survive_the_url() -> None:
    assert article_path("Johnson & Johnson") == "Johnson_%26_Johnson"
    assert article_path("AT&T") == "AT%26T"
    assert article_path("Tesla, Inc.") == "Tesla%2C_Inc."
    assert article_path("Clicks (South Africa)") == "Clicks_%28South_Africa%29"


def test_redirects_disambiguation_and_missing_pages_are_named_not_counted() -> None:
    """A redirect's own count is small, plausible and wrong — why titles are checked at all."""
    wiki = FakeWiki(
        pages={"Naspers": {}, "Shoprite": {"pageprops": {"disambiguation": ""}}, "TFG Limited": {}},
        redirects={"The Foschini Group": "TFG Limited"},
    )
    states = resolve_titles(["Naspers", "Shoprite", "The Foschini Group", "Clicks Group"], wiki)
    assert states == {
        "Naspers": "ok",
        "Shoprite": "disambiguation",
        "The Foschini Group": "redirect",
        "Clicks Group": "missing",
    }


def test_a_response_becomes_one_row_per_published_day() -> None:
    body = {
        "items": [
            {"timestamp": "2021012800", "views": 174157},
            {"timestamp": "2021012900", "views": 56606},
        ]
    }
    rows = parse_pageviews("GME", "GameStop", body)
    assert rows == [
        {"ticker": "GME", "date": dt.date(2021, 1, 28), "article": "GameStop", "views": 174157},
        {"ticker": "GME", "date": dt.date(2021, 1, 29), "article": "GameStop", "views": 56606},
    ]


@pytest.mark.parametrize(
    "item",
    [
        {"timestamp": "2021012800", "views": -1},
        {"timestamp": "2021012800", "views": "many"},
        {"timestamp": "junk", "views": 10},
        {"views": 10},
    ],
)
def test_a_malformed_day_is_dropped_rather_than_stored_as_something_else(
    item: dict[str, Any],
) -> None:
    assert parse_pageviews("GME", "GameStop", {"items": [item]}) == []


def test_an_unexpected_body_is_no_rows_not_a_crash() -> None:
    assert parse_pageviews("GME", "GameStop", None) == []
    assert parse_pageviews("GME", "GameStop", {"detail": "not found"}) == []
