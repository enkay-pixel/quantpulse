"""The exchange registry is the single source of truth for market facts. Where a fact has
to be duplicated for another tool (dbt cannot read Python), a test pins them together —
two sources of truth for the same fact drift silently."""

from pathlib import Path

import pytest
import yaml

from quantpulse.data.calendar import (
    DEFAULT_EXCHANGE,
    EXCHANGES,
    XJSE,
    XNYS,
    get_exchange,
)

DBT_PROJECT = Path(__file__).parents[2] / "transform" / "dbt_project.yml"


def test_dbt_benchmarks_match_the_registry() -> None:
    """dbt picks the buy-and-hold comparison per market from a var. If it drifts from the
    registry, the dashboard would benchmark a market against the wrong index."""
    project = yaml.safe_load(DBT_PROJECT.read_text())
    dbt_benchmarks = project["vars"]["benchmarks"]
    assert dbt_benchmarks == {code: ex.benchmark for code, ex in EXCHANGES.items()}


def test_default_exchange_is_registered() -> None:
    assert DEFAULT_EXCHANGE in EXCHANGES


def test_lookup_is_case_insensitive_and_rejects_typos() -> None:
    assert get_exchange("xnys") is XNYS
    assert get_exchange(None) is XNYS  # default keeps single-market callers working
    with pytest.raises(ValueError, match="Unknown exchange"):
        get_exchange("NASDAQ")


def test_jse_quotes_in_cents_not_rand() -> None:
    """Yahoo reports JSE prices in ZAc: a 79787 quote is R797.87. Getting this wrong
    would misprice every position by 100x."""
    assert XJSE.currency == "ZAc"
    assert XJSE.display_divisor == 100.0
    assert XJSE.display_symbol == "R"
    assert XNYS.display_divisor == 1.0


def test_only_markets_with_free_chain_data_claim_options() -> None:
    """No vendor we can use sells JSE option chains, so the options layer must not be
    offered for it — an empty Options tab reads as a bug rather than a data limit."""
    assert XNYS.has_options
    assert not XJSE.has_options


def test_each_exchange_has_a_distinct_session_clock() -> None:
    assert XNYS.timezone != XJSE.timezone
    assert XJSE.close_hour == 17  # JSE closes 17:00 SAST
    assert XNYS.close_hour == 16
