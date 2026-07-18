from quantpulse.ml.promotion import (
    DRAWDOWN,
    IC,
    SHARPE,
    PromotionPolicy,
    decide_promotion,
)

GOOD = {SHARPE: 1.2, IC: 0.05, DRAWDOWN: -0.10}


def test_first_viable_model_promotes_without_champion() -> None:
    decision = decide_promotion(GOOD, champion=None)
    assert decision.promote
    assert "no champion" in decision.reason


def test_nan_sharpe_never_promotes() -> None:
    decision = decide_promotion({SHARPE: float("nan")}, champion=None)
    assert not decision.promote


def test_negative_ic_rejected() -> None:
    decision = decide_promotion({**GOOD, IC: -0.02}, champion=None)
    assert not decision.promote
    assert "IC" in decision.reason


def test_drawdown_floor_rejected() -> None:
    decision = decide_promotion({**GOOD, DRAWDOWN: -0.50}, champion=None)
    assert not decision.promote
    assert "drawdown" in decision.reason


def test_challenger_must_beat_champion_by_margin() -> None:
    champion = {SHARPE: 1.0}
    policy = PromotionPolicy(min_sharpe_improvement=0.1)
    assert not decide_promotion({**GOOD, SHARPE: 1.05}, champion, policy).promote
    assert decide_promotion({**GOOD, SHARPE: 1.15}, champion, policy).promote


def test_champion_without_metrics_is_replaced() -> None:
    decision = decide_promotion(GOOD, champion={})
    assert decision.promote
