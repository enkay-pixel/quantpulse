"""The advisor brief's wording (ADR 0007): fixed rules over evidence, and never an instruction.

The brief is the page most likely to be read as advice, so the boundary is tested on the text
itself: whatever the evidence, no sentence may tell the reader to buy, sell or hold.
"""

import dataclasses
import datetime as dt
import re

import pytest

from quantpulse.research.brief import Evidence, _price_evidence, compose, share_class

AS_OF = dt.date(2026, 10, 16)


def _loaded(**over: object) -> Evidence:
    """A model name with every source present and every rule triggered."""
    base = Evidence(
        ticker="GME",
        exchange="XNYS",
        followed_by="model",
        name="GameStop Corp.",
        as_of=AS_OF,
        close=27.0,
        returns={"1m": 0.12, "3m": -0.05, "12m": 0.40},
        volatility=0.85,
        from_high=-0.45,
        model_rank=3,
        model_count=40,
        model_date=AS_OF,
        book_side="long",
        live_sessions=60,
        live_alpha=0.12,
        live_alpha_se=0.20,
        live_alpha_t=0.6,
        short_pct_float=0.22,
        days_to_cover=4.0,
        short_settlement_date=dt.date(2026, 9, 30),
        call_gamma_share_of_adv=0.40,
        attention_ratio=4.2,
        bought_usd_90d=99e6,
        buyers_90d=1,
        sold_usd_90d=3e6,
        planned_sold_share_90d=0.3,
        top_holder="Cohen Ryan",
        top_holder_percent=9.1,
        activist_holder=True,
        option_spread="Bull call spread 27/30, expiring 20 Nov 2026",
    )
    return dataclasses.replace(base, **over)  # type: ignore[arg-type]


#: Phrasing that would turn an assessment into an instruction.
INSTRUCTION = re.compile(
    r"\b(you should|we recommend|i recommend|recommend(ed)? (buying|selling|holding)|"
    r"(buy|sell|hold) (it|now|this)|consider (buying|selling)|strong (buy|sell)|"
    r"price target|time to (buy|sell))\b",
    re.IGNORECASE,
)


def _all_text(brief: object) -> list[str]:
    b = dataclasses.asdict(brief)  # type: ignore[call-overload]
    out = [b["summary"], *b["for_points"], *b["against_points"], *b["risks"], *b["questions"]]
    out += b["limits"] + [f"{f['fact']} {f['value']} {f['note'] or ''}" for f in b["facts"]]
    return out


@pytest.mark.parametrize(
    "evidence",
    [
        _loaded(),
        _loaded(model_rank=39, short_pct_float=0.01, bought_usd_90d=0.0, buyers_90d=0),
        _loaded(followed_by="watchlist", model_rank=None, model_count=None, live_sessions=None),
        Evidence(ticker="NPN.JO", exchange="XJSE", followed_by="model", has_options=False),
    ],
    ids=["every-rule", "bottom-fifth", "watchlist", "jse-bare"],
)
def test_no_sentence_tells_the_reader_what_to_do(evidence: Evidence) -> None:
    brief = compose(evidence)
    offending = [t for t in _all_text(brief) if INSTRUCTION.search(t)]
    assert not offending, f"assessments only, never instructions: {offending}"
    assert "not a recommendation" in brief.disclaimer


def test_a_top_fifth_rank_leans_in_favour_but_an_unproven_model_is_named_as_a_limit() -> None:
    brief = compose(_loaded())
    assert any("top fifth" in p for p in brief.for_points)
    assert any("cannot yet be told apart from luck" in limit for limit in brief.limits)
    assert any("has not separated from luck" in q for q in brief.questions)


def test_a_bottom_fifth_rank_leans_against() -> None:
    assert any("bottom fifth" in p for p in compose(_loaded(model_rank=39)).against_points)


def test_heavy_shorting_leans_against_and_is_a_risk_both_ways() -> None:
    brief = compose(_loaded())
    assert any("sold short" in p for p in brief.against_points)
    assert any("GameStop did in 2021" in r and "fall hard" in r for r in brief.risks)


def test_insider_buying_leans_in_favour_and_raises_a_question() -> None:
    brief = compose(_loaded())
    assert any("Insiders bought $99M" in p for p in brief.for_points)
    assert any("Insiders have been buying" in q for q in brief.questions)


def test_a_watchlist_name_has_no_model_view_and_says_so() -> None:
    brief = compose(_loaded(followed_by="watchlist", model_rank=None, model_count=None))
    assert not any("rank" in p for p in brief.for_points + brief.against_points)
    assert any("does not follow this name" in limit for limit in brief.limits)


def test_a_jse_name_names_what_its_market_does_not_publish() -> None:
    brief = compose(
        Evidence(ticker="NPN.JO", exchange="XJSE", followed_by="model", has_options=False)
    )
    assert any("not published free for this market" in limit for limit in brief.limits)
    assert brief.summary.startswith("Nothing in the evidence here leans clearly either way")


def test_a_jse_price_is_shown_in_rand_not_cents() -> None:
    brief = compose(
        Evidence(ticker="NPN.JO", exchange="XJSE", followed_by="model", as_of=AS_OF, close=79787.0)
    )
    assert brief.facts[0].value == "R797.87"


def test_price_evidence_reads_returns_volatility_and_the_fall_from_the_high() -> None:
    days = [AS_OF - dt.timedelta(days=299 - i) for i in range(300)]
    closes = [100.0 * (1.01 if i % 2 else 0.99) ** 1 for i in range(299)] + [80.0]
    closes[50] = 125.0  # the 12-month high
    e = Evidence(ticker="X", exchange="XNYS", followed_by="model")
    _price_evidence(e, list(zip(days, closes, strict=True)))
    assert e.as_of == AS_OF and e.close == 80.0
    assert e.from_high == pytest.approx(80 / 125 - 1)
    assert e.returns["1m"] == pytest.approx(80 / closes[-22] - 1)
    assert e.volatility is not None and e.volatility > 0.1


def test_the_summary_counts_risks_in_plain_words() -> None:
    quiet = Evidence(ticker="KO", exchange="XNYS", followed_by="model")
    assert "no risk stands out beyond those of owning any single stock" in compose(quiet).summary
    one = dataclasses.replace(quiet, volatility=0.9)
    assert "1 risk is worth raising" in compose(one).summary
    assert "risks are worth raising" in compose(_loaded()).summary


def test_the_summary_says_which_way_points_lean_without_a_zero_count() -> None:
    against = compose(
        _loaded(
            model_rank=39, short_pct_float=0.01, bought_usd_90d=0.0, buyers_90d=0, sold_usd_90d=0.0
        )
    )
    assert "1 point in the evidence leans against it and none in its favour" in against.summary
    both = compose(_loaded())
    assert "points in the evidence lean in its favour and 1 against it" in both.summary
    assert "0 point" not in against.summary + both.summary


def test_a_stock_at_its_high_says_so_rather_than_zero_percent() -> None:
    brief = compose(Evidence(ticker="KO", exchange="XNYS", followed_by="model", from_high=-0.001))
    assert {f.fact: f.value for f in brief.facts}["Below its 12-month high"] == "At its high"


def test_a_stake_names_its_class_where_the_company_has_several() -> None:
    assert share_class("Class A Common Stock, Par Value $5.00 per share") == "Class A"
    assert share_class("Common Stock") is None
    brief = compose(
        _loaded(
            top_holder="Warren E. Buffett",
            top_holder_percent=38.2,
            top_holder_class="Class A Common Stock, Par Value $5.00 per share",
        )
    )
    facts = {f.fact: f.value for f in brief.facts}
    assert facts["Largest holder over 5%"] == "Warren E. Buffett, 38.2% of Class A"
