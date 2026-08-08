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


def test_challenger_must_beat_champion_by_an_ic_margin() -> None:
    """IC carries the comparison. Sharpe is far too noisy to decide on: refitting the same
    spec with a different seed moves it by sd 0.12-0.24, while IC moves by 0.003-0.004."""
    champion = {SHARPE: 1.0, IC: 0.050}
    policy = PromotionPolicy(min_ic_improvement=0.01)
    assert not decide_promotion({**GOOD, IC: 0.055}, champion, policy).promote
    assert decide_promotion({**GOOD, IC: 0.065}, champion, policy).promote


def test_a_better_ranking_cannot_buy_a_materially_worse_book() -> None:
    """The Sharpe veto: IC may improve, but not while the portfolio collapses."""
    champion = {SHARPE: 1.5, IC: 0.05}
    collapsed = {SHARPE: 0.2, IC: 0.09, DRAWDOWN: -0.10}
    decision = decide_promotion(collapsed, champion)
    assert not decision.promote
    assert "materially worse book" in decision.reason


def test_sharpe_noise_alone_does_not_veto() -> None:
    """A drop inside the metric's own noise must not block a real IC improvement —
    objecting to it would reintroduce exactly the randomness this gate escapes."""
    champion = {SHARPE: 1.5, IC: 0.05}
    jittered = {SHARPE: 1.3, IC: 0.09, DRAWDOWN: -0.10}
    assert decide_promotion(jittered, champion).promote


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


def test_ic_decides_before_the_veto_is_consulted() -> None:
    """Ordering matters, and getting it wrong is invisible in the outcome.

    A first cut ran the Sharpe veto first. Every real rejection then came back citing
    Sharpe, so the gate still *decided* on Sharpe while claiming to have demoted it — same
    verdicts, wrong reasons, and no test would have noticed. A veto that runs before the
    test it overrules is not a veto; it is the primary test wearing a different name.
    """
    champion = {SHARPE: 2.5, IC: 0.20}
    # Fails on both counts: IC is far below, and Sharpe has collapsed past the tolerance.
    doomed = {SHARPE: 1.6, IC: 0.08, DRAWDOWN: -0.10}
    decision = decide_promotion(doomed, champion)
    assert not decision.promote
    assert "IC" in decision.reason
    assert "materially worse book" not in decision.reason
