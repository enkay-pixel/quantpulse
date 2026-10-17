"""Reading a company's XBRL facts (ADR 0007): which figures are kept, and how periods are keyed."""

import datetime as dt

from quantpulse.research.fundamentals import (
    FIRST_PERIOD,
    _newest_statement,
    parse_company_facts,
)


def _fact(start: str | None, end: str, val: float, form: str = "10-Q", accn: str = "a1") -> dict:
    base = {
        "end": end,
        "val": val,
        "accn": accn,
        "fy": 2026,
        "fp": "Q2",
        "form": form,
        "filed": "2026-07-31",
    }
    return {**base, "start": start} if start else base


def test_only_listed_concepts_and_statement_forms_from_the_first_period_are_kept() -> None:
    data = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            _fact("2026-01-01", "2026-06-30", 60.0),
                            _fact("2026-01-01", "2026-06-30", 61.0, form="8-K"),
                            _fact("2014-01-01", "2014-12-31", 9.0, form="10-K"),
                        ]
                    }
                },
                "Assets": {"units": {"USD": [_fact(None, "2026-06-30", 500.0)]}},
                "SomethingElse": {"units": {"USD": [_fact("2026-01-01", "2026-06-30", 1.0)]}},
            },
            "dei": {
                "EntityCommonStockSharesOutstanding": {
                    "units": {"shares": [_fact(None, "2026-07-20", 10.0)]}
                }
            },
        }
    }
    rows = parse_company_facts("AAA", data)
    keyed = {(r["concept"], r["duration_days"]): r for r in rows}
    assert set(keyed) == {
        ("Revenues", 180),
        ("Assets", 0),
        ("EntityCommonStockSharesOutstanding", 0),
    }, "an 8-K, a concept not listed and a period before FIRST_PERIOD are all left out"
    assert keyed[("Revenues", 180)]["period_start"] == dt.date(2026, 1, 1)
    assert keyed[("Assets", 0)]["period_start"] is None
    assert dt.date(2016, 1, 1) == FIRST_PERIOD


def test_the_newest_statement_is_the_first_10k_or_10q_listed() -> None:
    submissions = {
        "filings": {
            "recent": {
                "form": ["8-K", "4", "10-Q", "10-K"],
                "accessionNumber": ["x", "y", "q2", "k1"],
            }
        }
    }
    assert _newest_statement(submissions) == "q2"
    assert (
        _newest_statement({"filings": {"recent": {"form": ["8-K"], "accessionNumber": ["x"]}}})
        is None
    )
