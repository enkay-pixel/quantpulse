"""Champion/challenger promotion gate — the decision half of the self-adapting loop."""

import logging
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # heavy/circular at runtime; this module stays importable on its own
    from sqlalchemy.orm import Session

    from quantpulse.db import ModelRun

logger = logging.getLogger(__name__)

# Keys expected in the metric dicts compared below
SHARPE = "holdout_sharpe"
IC = "holdout_ic"
DRAWDOWN = "holdout_max_drawdown"


@dataclass(frozen=True)
class PromotionPolicy:
    """What it takes to replace a champion.

    The comparison runs on **information coefficient**, not Sharpe. That is a measurement
    decision rather than a modelling one: refitting an identical specification with only
    the RNG changed moves holdout Sharpe by sd 0.12 (XNYS) and 0.24 (XJSE), and scoring one
    fixed model across six-month windows moves it by sd ~2.0 — while IC moves by 0.003 and
    0.004. The old gate compared Sharpe with a 0.05 margin, five to ten times *below* its
    own noise floor, so decisions inside that band were coin flips wearing a number.

    Sharpe is kept as a **veto, not a comparison**. A model can rank better while building
    a worse book, and `max_sharpe_regression` catches that — but the tolerance is wide on
    purpose. Sharpe cannot support a fine comparison, so it is only allowed to object when
    the drop is far larger than the noise that produced it.
    """

    #: Per-market IC margin (2 sd of the seed re-roll) lives on the Exchange registry;
    #: this is the fallback when a caller does not supply one.
    min_ic_improvement: float = 0.006
    max_drawdown_floor: float = -0.35  # reject anything with worse drawdown than this
    min_ic: float = 0.0  # reject negative-IC models outright
    # How far Sharpe may fall while IC improves. Roughly 2 sd of the seed re-roll, rounded
    # up: below this a "regression" is indistinguishable from reshuffling the RNG, so
    # objecting to it would just reintroduce the noise this gate was rewritten to escape.
    max_sharpe_regression: float = 0.50
    # A first champion has nothing to beat, so "better than the incumbent" cannot gate it.
    # It still has to be worth acting on: a model that lost money on data it never saw
    # must not become the signal a dashboard presents as its champion's view.
    min_first_sharpe: float = 0.0


@dataclass(frozen=True)
class PromotionDecision:
    promote: bool
    reason: str


def decide_promotion(
    candidate: dict[str, float],
    champion: dict[str, float] | None,
    policy: PromotionPolicy | None = None,
) -> PromotionDecision:
    """Pure decision: should `candidate` replace `champion`? (NaN-safe: NaN never promotes.)"""
    p = policy or PromotionPolicy()
    cand_sharpe = candidate.get(SHARPE, float("nan"))
    cand_ic = candidate.get(IC, float("nan"))
    cand_dd = candidate.get(DRAWDOWN, float("nan"))

    if math.isnan(cand_sharpe):
        return PromotionDecision(False, "candidate holdout Sharpe is NaN")
    if not math.isnan(cand_ic) and cand_ic < p.min_ic:
        return PromotionDecision(False, f"candidate IC {cand_ic:.4f} below floor {p.min_ic}")
    if not math.isnan(cand_dd) and cand_dd < p.max_drawdown_floor:
        return PromotionDecision(
            False, f"candidate drawdown {cand_dd:.2%} worse than floor {p.max_drawdown_floor:.2%}"
        )
    if champion is None:
        if cand_sharpe < p.min_first_sharpe:
            return PromotionDecision(
                False,
                f"first candidate holdout Sharpe {cand_sharpe:.3f} is below the floor "
                f"{p.min_first_sharpe:.2f} — no champion is better than a losing one",
            )
        return PromotionDecision(True, "no champion exists — promoting first viable model")

    # IC decides. The Sharpe veto is applied *after*, and only to a candidate that would
    # otherwise be promoted — a veto that runs first is not a veto, it is the primary test,
    # and it would quietly restore Sharpe as the decider this gate was rewritten to demote.
    champ_ic = champion.get(IC, float("nan"))
    if math.isnan(champ_ic):
        return PromotionDecision(True, "champion has no comparable IC — promoting candidate")
    if math.isnan(cand_ic):
        return PromotionDecision(False, "candidate IC is NaN")

    required = champ_ic + p.min_ic_improvement
    if cand_ic < required:
        return PromotionDecision(
            False,
            f"candidate IC {cand_ic:.4f} does not beat champion {champ_ic:.4f} "
            f"+ margin {p.min_ic_improvement:.4f}",
        )

    # Ranking better while the book gets materially worse is not an upgrade. Wide on
    # purpose: only a collapse far beyond the metric's own noise may overrule IC.
    champ_sharpe = champion.get(SHARPE, float("nan"))
    if not math.isnan(champ_sharpe) and cand_sharpe < champ_sharpe - p.max_sharpe_regression:
        return PromotionDecision(
            False,
            f"candidate IC {cand_ic:.4f} beats champion {champ_ic:.4f}, but Sharpe "
            f"{cand_sharpe:.3f} falls more than {p.max_sharpe_regression:.2f} below "
            f"{champ_sharpe:.3f} — better ranking, materially worse book",
        )
    return PromotionDecision(
        True,
        f"candidate IC {cand_ic:.4f} beats champion {champ_ic:.4f} "
        f"+ margin {p.min_ic_improvement:.4f}",
    )


def audit_champion(session: "Session", exchange: str) -> "ModelRun | None":
    """The champion according to the **audit trail**, independent of MLflow.

    `model_runs` is append-only, so a promotion that was later reversed is still in it. A
    demotion withdraws *its own version's* promotion, and the champion falls back to the
    most recent promotion with no later demotion; when every promotion is withdrawn (the
    first-champion rollback, incident 17) the market has no champion.

    Extracted so the API and the `champion_registry_agrees` asset check ask the question
    exactly once. Two copies of this query is the shape of bug the check exists to find:
    the platform would compare two answers that were never really independent, and agree
    with itself while disagreeing with the model that is actually scoring.
    """
    from sqlalchemy import exists, select
    from sqlalchemy.orm import aliased

    from quantpulse.db import ModelRun

    demoted = aliased(ModelRun)
    return session.scalars(
        select(ModelRun)
        .where(
            ModelRun.decision == "promoted",
            ModelRun.exchange == exchange,
            ~exists().where(
                demoted.exchange == ModelRun.exchange,
                demoted.run_type == "demotion",
                demoted.model_version == ModelRun.model_version,
                demoted.id > ModelRun.id,
            ),
        )
        .order_by(ModelRun.id.desc())
    ).first()
