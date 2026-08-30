# Can the boosting round count be chosen well? (2026-08-24)

> **The headline result was wrong, corrected 2026-08-30.** "25 rounds beats early stopping on
> the JSE" was measured on **one holdout** across eight seeds. That error describes how much
> refitting moves the number on that window, not whether the effect holds; rolled across 46
> origins tiling 2022–2026 the advantage is **−0.0004 ± 0.0045 (t −0.10)** and fixed-25 wins in
> 12 of 46 origins. Same class of error as
> [model staleness](model-staleness.md#what-was-reported-and-how-it-failed), found in the same
> audit.

[Why the champion has three trees](three-tree-champion.md) established that the
early-stopping split does not predict holdout performance, and that following it costs about
0.025 IC against an oracle. Two ways out were proposed there. Both were tested. Neither works
in general.

## Lowering the learning rate does not flatten the curve

If the IC-versus-rounds curve were flat, the round choice would stop mattering. Spread of
holdout IC across rounds 20–200, three seeds:

| learning rate | XNYS spread | XNYS best IC | XJSE spread | XJSE best IC |
|---|---|---|---|---|
| 0.0176 (current) | 0.0274 ± 0.0034 | 0.0641 | 0.0472 ± 0.0065 | 0.0750 |
| 0.005 | 0.0223 ± 0.0010 | 0.0643 | 0.0624 ± 0.0062 | 0.0601 |
| 0.002 | 0.0169 ± 0.0005 | 0.0598 | 0.0492 ± 0.0073 | 0.0440 |

On the NYSE the spread does fall, but the change from 0.0176 to 0.005 is t ≈ 1.45 — not
resolved — and pushing to 0.002 costs peak IC. On the JSE the spread does not fall at all and
peak IC drops by 0.031. A slower learner is not a fix.

## A fixed round count beats early stopping on one market only

Holdout IC against the current early-stopping fit, paired on the seed, eight seeds:

| rounds | XNYS vs early-stop | XJSE vs early-stop |
|---|---|---|
| 10 | +0.0114 ± 0.0068 (t +1.67) | −0.0136 ± 0.0075 (t −1.82) |
| 25 | +0.0020 ± 0.0047 (t +0.42) | **+0.0166 ± 0.0048 (t +3.43)** |
| 50 | −0.0092 ± 0.0056 (t −1.65) | **+0.0121 ± 0.0037 (t +3.27)** |

~~**On the JSE, simply training 25 rounds beats early stopping outright.**~~ **It does not.**
Re-measured with the origin rolled every 21 trading days, three seeds per origin, paired the
same way:

| | 25 rounds vs early stopping, XJSE |
|---|---|
| published — 8 seeds, one holdout | +0.0166 ± 0.0048 (t +3.43) |
| 46 origins, error across origins | **−0.0004 ± 0.0045 (t −0.10)** |
| origins where fixed-25 wins | 12 / 46 (26%) |

The published figure was one window's draw. On the NYSE nothing resolved either, so what
survives from this table is only that **no round count has been shown to suit either market** —
not that they disagree.

## What this settles

~~The round count is a **per-market quantity**~~ — this followed from the JSE result above,
and falls with it. Neither market has a demonstrated preference; the two are not shown to
disagree about the round count, only to be equally unresolved about it.

What still stands from this page is the negative half: **lowering the learning rate does not
flatten the curve**, so the round choice cannot be made to stop mattering that way. That
measurement has the same one-holdout weakness as the one above and has not been re-run across
origins, so treat it as unconfirmed rather than established.

It also means the early-stopping problem has no general fix. It can only be replaced
per-market, by a number that would itself need choosing on evidence.

Two caveats before anyone acts on this:

- The candidate counts {10, 25, 50} were chosen after seeing the tree sweep in
  [the three-tree finding](three-tree-champion.md), which showed IC peaking near 10–25.
  Testing three pre-specified values is milder than taking an argmax, but it is not clean.
- Both markets' figures come from one holdout that has been read many times. A fresh panel
  period is what would confirm them. **This caveat was the right one and was not acted on**;
  rolling the origin is what eventually refuted the headline.

Nothing is changed in the model. Setting a per-market round count is a modelling decision.

## Related

- [Why the champion has three trees](three-tree-champion.md) — the problem this tried to solve
- [Feature ablation and pruning](feature-ablation-and-pruning.md) — the other per-market
  disagreement
- [How to measure things here](../measurement.md)
