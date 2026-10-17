"""Tier 2 — translate the equity model's directional signal into a HYPOTHETICAL option
structure. This is an illustration of the model's view, not a recommendation: options
carry leverage and total-loss risk, and none of this is investment advice.

Pure functions over a current option chain; no I/O, fully tested.
"""

from dataclasses import dataclass
from typing import Literal

# A signal is "actionable" only past this magnitude (21-day forward-return forecast).
SIGNAL_THRESHOLD = 0.02
#: How far out of the money the short leg sits, in the signal's direction: it caps the risk.
SHORT_LEG_DISTANCE = 0.10

Direction = Literal["bullish", "bearish", "neutral"]


@dataclass(frozen=True)
class OptionLeg:
    action: str  # 'buy' | 'sell'
    option_type: str  # 'call' | 'put'
    strike: float
    price: float  # mid or last, per contract (per share)


@dataclass(frozen=True)
class OptionIdea:
    structure: str  # e.g. 'long call', 'bull call spread'
    direction: Direction
    rationale: str
    legs: list[OptionLeg]
    net_debit: float  # cost per share (x100 = per contract)
    max_profit: float | None  # None = unbounded
    max_loss: float
    breakeven: float


def classify_signal(score: float) -> Direction:
    if score >= SIGNAL_THRESHOLD:
        return "bullish"
    if score <= -SIGNAL_THRESHOLD:
        return "bearish"
    return "neutral"


def _nearest(strikes: list[float], target: float) -> float:
    return min(strikes, key=lambda s: abs(s - target))


def spread_strikes(
    direction: Direction, spot: float, strikes: list[float]
) -> tuple[float, float] | None:
    """(long strike, short strike) for a vertical spread in the signal's direction.

    The long leg sits nearest the money; the short leg sits about SHORT_LEG_DISTANCE further out
    in the signal's direction, which caps both the cost and the payoff. The one strike rule shared
    by the Options tab's illustration and the paper options book (ADR 0008).
    """
    available = sorted(set(strikes))
    if direction == "neutral" or len(available) < 2:
        return None
    long_strike = _nearest(available, spot)
    target = spot * (1 + SHORT_LEG_DISTANCE if direction == "bullish" else 1 - SHORT_LEG_DISTANCE)
    short_strike = _nearest([k for k in available if k != long_strike], target)
    return long_strike, short_strike


@dataclass(frozen=True)
class ChainRow:
    strike: float
    option_type: str  # 'call' | 'put'
    price: float


def build_idea(score: float, spot: float, chain: list[ChainRow]) -> OptionIdea | None:
    """Suggest a hypothetical single-leg + vertical-spread structure for the signal.

    Bullish → long call / bull call spread; bearish → long put / bear put spread;
    neutral → no idea. Strikes are picked ~at-the-money and ~10% out for the spread.
    """
    direction = classify_signal(score)
    if direction == "neutral":
        return None

    kind = "call" if direction == "bullish" else "put"
    priced = {c.strike: c.price for c in chain if c.option_type == kind}
    picked = spread_strikes(direction, spot, list(priced))
    if picked is None:
        return None
    long_strike, short_strike = picked
    long_price = priced[long_strike]
    short_price = priced[short_strike]

    net_debit = round(long_price - short_price, 2)
    width = abs(short_strike - long_strike)
    max_loss = round(net_debit, 2)
    max_profit = round(width - net_debit, 2)
    if direction == "bullish":
        breakeven = round(long_strike + net_debit, 2)
    else:
        breakeven = round(long_strike - net_debit, 2)

    verb = "above" if direction == "bullish" else "below"
    return OptionIdea(
        structure=f"{'bull call' if direction == 'bullish' else 'bear put'} spread",
        direction=direction,
        rationale=(
            f"Model's 21-day forecast is {score:+.1%} ({direction}); a defined-risk "
            f"{kind} spread profits if the stock moves {verb} the breakeven by expiry."
        ),
        legs=[
            OptionLeg("buy", kind, long_strike, long_price),
            OptionLeg("sell", kind, short_strike, short_price),
        ],
        net_debit=net_debit,
        max_profit=max_profit,
        max_loss=max_loss,
        breakeven=breakeven,
    )
