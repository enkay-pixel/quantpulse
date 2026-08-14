import pandas as pd
import pytest

from quantpulse.ml.promotion import (
    DRAWDOWN,
    IC,
    SHARPE,
    PromotionDecision,
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


# --- the standing competitor ---
#
# Beating the incumbent is not enough. A lineage can beat each other while all of them lose
# to a rule that fits on one line, and that was measured rather than imagined: on the
# 311-session XJSE holdout, momentum scored IC 0.1167 against champion v3's 0.0681.

BASE = {"holdout_ic": 0.10, "holdout_sharpe": 2.0, "holdout_max_drawdown": -0.05}


def _cand(ic: float, sharpe: float = 1.5) -> dict[str, float]:
    return {"holdout_ic": ic, "holdout_sharpe": sharpe, "holdout_max_drawdown": -0.05}


def test_a_candidate_that_loses_to_the_baseline_is_rejected() -> None:
    """The XJSE case, in miniature: it beats the incumbent and still has not earned it."""
    incumbent = {"holdout_ic": 0.05, "holdout_sharpe": 1.8, "holdout_max_drawdown": -0.07}
    decision = decide_promotion(_cand(0.068), incumbent, baseline=BASE)
    assert not decision.promote
    assert "momentum" in decision.reason
    assert "fit-free rule" in decision.reason


def test_a_candidate_that_beats_the_baseline_still_faces_the_incumbent() -> None:
    """The baseline is an extra hurdle, not a replacement for the existing comparison."""
    incumbent = {"holdout_ic": 0.30, "holdout_sharpe": 2.4, "holdout_max_drawdown": -0.05}
    decision = decide_promotion(_cand(0.20), incumbent, baseline=BASE)
    assert not decision.promote
    assert "champion" in decision.reason


def test_beating_both_promotes() -> None:
    incumbent = {"holdout_ic": 0.11, "holdout_sharpe": 2.0, "holdout_max_drawdown": -0.05}
    assert decide_promotion(_cand(0.20), incumbent, baseline=BASE).promote


def test_the_margin_applies_to_the_baseline_too() -> None:
    """Matching the baseline is not beating it — inside the margin the difference is noise,
    and a tie against a fit-free rule is not evidence for a tuned model."""
    policy = PromotionPolicy(min_ic_improvement=0.006)
    incumbent = {"holdout_ic": 0.01, "holdout_sharpe": 1.0, "holdout_max_drawdown": -0.05}
    assert not decide_promotion(_cand(0.1005), incumbent, policy, baseline=BASE).promote
    assert decide_promotion(_cand(0.1070), incumbent, policy, baseline=BASE).promote


def test_a_first_champion_must_also_beat_the_baseline() -> None:
    """Where an unjustified model is least likely to be noticed: no incumbent to compare
    against, so without this the opening champion faces no justification test at all."""
    decision = decide_promotion(_cand(0.02), None, baseline=BASE)
    assert not decision.promote
    assert "momentum" in decision.reason


def test_a_first_champion_that_beats_the_baseline_is_promoted() -> None:
    assert decide_promotion(_cand(0.20), None, baseline=BASE).promote


def test_a_nan_baseline_blocks_rather_than_waves_through() -> None:
    """Fails closed. A justification check that promotes when it cannot run is not a check;
    the cost is that nothing promotes until it is fixed, which is the loud failure."""
    broken = {"holdout_ic": float("nan"), "holdout_sharpe": 2.0}
    decision = decide_promotion(_cand(0.5), None, baseline=broken)
    assert not decision.promote
    assert "NaN" in decision.reason


def test_omitting_the_baseline_leaves_the_other_rules_intact() -> None:
    """The parameter is optional so the rest of this file stays readable; that must not
    change any other verdict."""
    incumbent = {"holdout_ic": 0.05, "holdout_sharpe": 1.8, "holdout_max_drawdown": -0.07}
    assert decide_promotion(_cand(0.20), incumbent).promote


# --- scaffolding for the production-path wiring test below ---


def _panel(n_days: int = 40, n_tickers: int = 12) -> pd.DataFrame:
    """A frame shaped like the real holdout: every FEATURE_COLUMN, the real LABEL_COLUMN,
    and the (ticker, date) grain the backtest groups on. Built from the actual constants so
    it cannot drift from the panel the pipeline really produces."""
    import numpy as np

    from quantpulse.features.engineering import FEATURE_COLUMNS, LABEL_COLUMN

    rng = np.random.default_rng(7)
    rows = n_days * n_tickers
    data = {c: rng.normal(size=rows) for c in FEATURE_COLUMNS}
    data[LABEL_COLUMN] = rng.normal(scale=0.02, size=rows)
    # train_final_model returns the holdout with predictions already attached.
    data["pred"] = rng.normal(size=rows)
    data["ticker"] = [f"T{i % n_tickers}" for i in range(rows)]
    data["date"] = pd.to_datetime("2026-01-01") + pd.to_timedelta(
        np.arange(rows) // n_tickers, unit="D"
    )
    return pd.DataFrame(data)


class _Booster:
    def predict(self, x):  # type: ignore[no-untyped-def]
        import numpy as np

        return np.zeros(len(x))


class _Version:
    version = "9"
    run_id = "run9"


class _Session:
    def add(self, _obj):  # type: ignore[no-untyped-def]
        return None


def test_the_gate_is_always_given_a_baseline(monkeypatch: pytest.MonkeyPatch) -> None:
    """`baseline` is optional on the pure function, so the production path has to be pinned
    separately — an optional guard that the caller forgets is the failure mode this whole
    session kept finding. Asserts the real pipeline supplies one, without training anything.
    """
    import quantpulse.ml.pipeline as pipeline

    captured: dict[str, object] = {}

    def fake_decide(candidate, champion, policy=None, *, baseline=None):  # type: ignore[no-untyped-def]
        captured["baseline"] = baseline
        return PromotionDecision(False, "stubbed")

    monkeypatch.setattr(pipeline, "decide_promotion", fake_decide)
    monkeypatch.setattr(pipeline, "build_dataset", lambda *a, **k: _panel())
    monkeypatch.setattr(
        pipeline, "tune_hyperparameters", lambda *a, **k: {"objective": "regression"}
    )
    monkeypatch.setattr(
        pipeline, "train_final_model", lambda frame, cols, params, cfg: (_Booster(), _panel())
    )
    monkeypatch.setattr(pipeline.registry, "log_candidate", lambda *a, **k: _Version())
    monkeypatch.setattr(pipeline.registry, "load_champion", lambda **k: None)

    pipeline.train_evaluate_promote(object(), _Session(), exchange="XNYS")  # type: ignore[arg-type]

    assert captured["baseline"] is not None, "the gate ran without a standing competitor"
    assert "holdout_ic" in captured["baseline"]  # type: ignore[operator]
