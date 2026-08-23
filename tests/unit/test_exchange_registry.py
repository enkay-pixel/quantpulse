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


def test_dbt_ratio_threshold_matches_the_python_constant() -> None:
    """The marts null small-sample ratios; the API and UI trust them to. If dbt and Python
    disagree, one consumer publishes a statistic another suppresses."""
    from quantpulse.reporting import MIN_DAYS_FOR_RATIOS

    project = yaml.safe_load(DBT_PROJECT.read_text())
    assert project["vars"]["min_days_for_ratios"] == MIN_DAYS_FOR_RATIOS


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


# --- per-market feature sets --------------------------------------------------------------


def test_every_market_names_only_features_that_exist() -> None:
    """A misspelled column would be dropped silently and the market would train a shorter
    model that still fits, still scores and still reports a number. The failure would look
    like a worse model weeks later, attributed to anything but a typo."""
    from quantpulse.features.engineering import FEATURE_COLUMNS, feature_columns_for

    for code in EXCHANGES:
        cols = feature_columns_for(code)
        assert cols, f"{code} resolved to an empty feature list"
        assert set(cols) <= set(FEATURE_COLUMNS)


def test_an_unknown_feature_name_is_rejected_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    from dataclasses import replace

    from quantpulse.data import calendar
    from quantpulse.features.engineering import feature_columns_for

    broken = replace(calendar.XNYS, feature_columns=("vol_21", "vol_21_typo"))
    monkeypatch.setitem(calendar.EXCHANGES, "XNYS", broken)
    with pytest.raises(ValueError, match="not engineered"):
        feature_columns_for("XNYS")


def test_an_empty_list_means_every_engineered_column(monkeypatch: pytest.MonkeyPatch) -> None:
    """The default has to stay 'all', or adding a market would silently train it on nothing."""
    from dataclasses import replace

    from quantpulse.data import calendar
    from quantpulse.features.engineering import FEATURE_COLUMNS, feature_columns_for

    monkeypatch.setitem(calendar.EXCHANGES, "XNYS", replace(calendar.XNYS, feature_columns=()))
    assert feature_columns_for("XNYS") == list(FEATURE_COLUMNS)


def test_a_market_can_carry_its_own_list(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both markets currently train on everything, so this pins the mechanism rather than
    today's values — the field is what lets them diverge when evidence supports it."""
    from dataclasses import replace

    from quantpulse.data import calendar
    from quantpulse.features.engineering import FEATURE_COLUMNS, feature_columns_for

    monkeypatch.setitem(
        calendar.EXCHANGES, "XNYS", replace(calendar.XNYS, feature_columns=("vol_21",))
    )
    assert feature_columns_for("XNYS") == ["vol_21"]
    assert feature_columns_for("XJSE") == list(FEATURE_COLUMNS)
