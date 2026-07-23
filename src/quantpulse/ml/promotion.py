"""Champion/challenger promotion gate — the decision half of the self-adapting loop."""

import logging
import math
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Keys expected in the metric dicts compared below
SHARPE = "holdout_sharpe"
IC = "holdout_ic"
DRAWDOWN = "holdout_max_drawdown"


@dataclass(frozen=True)
class PromotionPolicy:
    min_sharpe_improvement: float = 0.05  # challenger must beat champion by this margin
    max_drawdown_floor: float = -0.35  # reject anything with worse drawdown than this
    min_ic: float = 0.0  # reject negative-IC models outright
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

    champ_sharpe = champion.get(SHARPE, float("nan"))
    if math.isnan(champ_sharpe):
        return PromotionDecision(True, "champion has no comparable Sharpe — promoting candidate")
    required = champ_sharpe + p.min_sharpe_improvement
    if cand_sharpe >= required:
        return PromotionDecision(
            True, f"candidate Sharpe {cand_sharpe:.3f} beats champion {champ_sharpe:.3f} + margin"
        )
    return PromotionDecision(
        False,
        f"candidate Sharpe {cand_sharpe:.3f} does not beat champion {champ_sharpe:.3f} "
        f"+ margin {p.min_sharpe_improvement}",
    )
