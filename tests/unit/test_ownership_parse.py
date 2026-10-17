"""Reading SEC filings (ADR 0007): the parsers against documents shaped like real ones.

Imports `edgar_docs` from tests/, which pytest puts on the path for its root conftest.
"""

import datetime as dt

import pytest

from edgar_docs import form4, schedule13d, schedule13g
from quantpulse.research.ownership import (
    EdgarClient,
    SecContactMissing,
    _recent,
    issuer_cik,
    parse_form4,
    parse_schedule13,
    raw_document,
)


def test_a_form4_yields_its_common_stock_trades_and_not_its_derivatives() -> None:
    rows = parse_form4(
        form4(
            ("2026-10-12", "S", 15480, 27.0),
            ("2026-10-12", "F", 300, 27.0),
            ("2026-10-13", "P", 100, None),
            issuer=1326380,
        )
    )
    assert [(r["code"], r["shares"], r["price"]) for r in rows] == [
        ("S", 15480, 27.0),
        ("F", 300, 27.0),
        ("P", 100, None),
    ], "the derivative table's exercise must not appear"
    first = rows[0]
    assert first["owner"] == "Moore Daniel William"
    assert first["role"] == "Chief Financial Officer"
    assert first["planned"] is True
    assert first["transaction_date"] == dt.date(2026, 10, 12)
    assert first["acquired"] == "D" and first["shares_after"] == 1000


def test_an_older_form4_without_the_plan_question_says_nothing_rather_than_no() -> None:
    assert (
        parse_form4(form4(("2026-10-12", "S", 1, 1.0), issuer=1, planned=None))[0]["planned"]
        is None
    )


def test_a_13d_and_a_13g_give_the_principal_filer_and_stake_through_their_namespaces() -> None:
    d = parse_schedule13(schedule13d("Cohen Ryan", 9.1, 46227436, issuer=1326380))
    assert d == {
        "filer": "Cohen Ryan",
        "percent": 9.1,
        "shares": 46227436,
        "event_date": dt.date(2026, 10, 13),
        "share_class": "Class A Common Stock",
    }
    g = parse_schedule13(
        schedule13g("Vanguard Capital Management", 7.48, 1099168953, issuer=320193)
    )
    assert g is not None
    assert (g["filer"], g["percent"]) == ("Vanguard Capital Management", 7.48), "first cover page"


def test_the_raw_document_drops_edgars_stylesheet_folder() -> None:
    assert raw_document("xslF345X06/wk-form4_1791940906.xml") == "wk-form4_1791940906.xml"
    assert raw_document("xslSCHEDULE_13G_X02/primary_doc.xml") == "primary_doc.xml"
    assert raw_document("primary_doc.xml") == "primary_doc.xml"


def test_only_ownership_forms_inside_the_window_are_kept() -> None:
    submissions = {
        "filings": {
            "recent": {
                "accessionNumber": ["a", "b", "c", "d", "e"],
                "filingDate": [
                    "2026-10-13",
                    "2026-10-01",
                    "2026-09-01",
                    "2024-01-01",
                    "2026-10-02",
                ],
                "form": ["4", "SCHEDULE 13D/A", "10-Q", "4", "SC 13G/A"],
                "primaryDocument": ["x.xml"] * 5,
            }
        }
    }
    kept = _recent(submissions, dt.date(2024, 10, 17))
    assert [r["accessionNumber"] for r in kept] == ["a", "b"], (
        "a 10-Q is not an ownership form, a 2024 filing is outside the window, and a free-text "
        "SC 13G is not read"
    )


def test_without_a_contact_the_client_refuses_to_start(monkeypatch: pytest.MonkeyPatch) -> None:
    from quantpulse.config import get_settings

    monkeypatch.delenv("QUANTPULSE_SEC_CONTACT", raising=False)
    get_settings.cache_clear()
    monkeypatch.setattr(
        "quantpulse.research.ownership.get_settings",
        lambda: type("S", (), {"quantpulse_sec_contact": None})(),
    )
    with pytest.raises(SecContactMissing, match="QUANTPULSE_SEC_CONTACT"):
        EdgarClient()


def test_each_document_names_the_company_it_is_about() -> None:
    """The check that keeps a company's filings about other companies off its own page."""
    assert issuer_cik(form4(("2026-10-12", "S", 1, 1.0), issuer=1326380)) == 1326380
    assert issuer_cik(schedule13d("Cohen Ryan", 9.1, 1, issuer=1326380)) == 1326380
    assert issuer_cik(schedule13g("Vanguard", 7.0, 1, issuer=320193)) == 320193
