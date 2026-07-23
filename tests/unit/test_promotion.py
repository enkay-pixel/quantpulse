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


def test_first_champion_must_clear_a_sharpe_floor() -> None:
    """A first candidate has nothing to beat, so the margin rule cannot gate it. Without a
    floor a model that lost money out-of-sample becomes the champion whose signals the
    dashboard presents — which is how the first JSE model was promoted at Sharpe -0.069."""
    losing = {"holdout_sharpe": -0.069, "holdout_ic": 0.024, "holdout_max_drawdown": -0.12}
    decision = decide_promotion(losing, None)
    assert not decision.promote
    assert "below the floor" in decision.reason


def test_first_champion_with_positive_sharpe_is_promoted() -> None:
    winner = {"holdout_sharpe": 0.205, "holdout_ic": 0.026, "holdout_max_drawdown": -0.05}
    assert decide_promotion(winner, None).promote


def test_the_floor_applies_only_to_the_first_champion() -> None:
    """Once an incumbent exists the margin rule governs; a challenger is judged against it,
    not against zero."""
    champion = {"holdout_sharpe": -0.50}
    challenger = {"holdout_sharpe": -0.10, "holdout_ic": 0.01, "holdout_max_drawdown": -0.10}
    assert decide_promotion(challenger, champion).promote
