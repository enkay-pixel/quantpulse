import pytest

from quantpulse.options.strategy import ChainRow, build_idea, classify_signal


def chain(spot: float = 100.0) -> list[ChainRow]:
    rows = []
    for strike in [80.0, 90.0, 100.0, 110.0, 120.0]:
        # crude but monotone: further OTM is cheaper
        rows.append(ChainRow(strike, "call", max(spot - strike, 0) + 5 - abs(strike - spot) * 0.03))
        rows.append(ChainRow(strike, "put", max(strike - spot, 0) + 5 - abs(strike - spot) * 0.03))
    return rows


def test_classify_signal_thresholds() -> None:
    assert classify_signal(0.05) == "bullish"
    assert classify_signal(-0.05) == "bearish"
    assert classify_signal(0.005) == "neutral"
    assert classify_signal(-0.005) == "neutral"


def test_neutral_signal_yields_no_idea() -> None:
    assert build_idea(0.001, 100.0, chain()) is None


def test_bullish_signal_builds_call_spread() -> None:
    idea = build_idea(0.05, 100.0, chain())
    assert idea is not None
    assert idea.direction == "bullish"
    assert idea.structure == "bull call spread"
    assert [leg.option_type for leg in idea.legs] == ["call", "call"]
    assert idea.legs[0].action == "buy"
    assert idea.legs[1].action == "sell"
    # long leg at the money, short leg further out
    assert idea.legs[0].strike == 100.0
    assert idea.legs[1].strike > idea.legs[0].strike
    assert idea.breakeven > idea.legs[0].strike  # must rise to profit


def test_bearish_signal_builds_put_spread() -> None:
    idea = build_idea(-0.05, 100.0, chain())
    assert idea is not None
    assert idea.direction == "bearish"
    assert idea.structure == "bear put spread"
    assert [leg.option_type for leg in idea.legs] == ["put", "put"]
    assert idea.legs[1].strike < idea.legs[0].strike
    assert idea.breakeven < idea.legs[0].strike  # must fall to profit


def test_risk_metrics_are_bounded_and_consistent() -> None:
    idea = build_idea(0.05, 100.0, chain())
    assert idea is not None
    width = abs(idea.legs[1].strike - idea.legs[0].strike)
    assert idea.max_loss == pytest.approx(idea.net_debit)
    assert idea.max_profit == pytest.approx(width - idea.net_debit)
    assert idea.max_loss > 0  # a debit spread costs something


def test_thin_chain_yields_no_idea() -> None:
    assert build_idea(0.05, 100.0, [ChainRow(100.0, "call", 5.0)]) is None
