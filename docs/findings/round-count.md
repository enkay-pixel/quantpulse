# Can the boosting round count be chosen well? (2026-08-24)

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

**On the JSE, simply training 25 rounds beats early stopping outright.** On the NYSE nothing
resolves, and the direction that looks best there (10 rounds) is the one that is worst on the
JSE. There is no round count that suits both.

## What this settles

The round count is a **per-market quantity**, like the quantile width and the promotion
margin already are — and like `vol_63`, which the ablation found helps one market and hurts
the other. That is now the third property where the two markets disagree rather than differ
in degree.

It also means the early-stopping problem has no general fix. It can only be replaced
per-market, by a number that would itself need choosing on evidence.

Two caveats before anyone acts on this:

- The candidate counts {10, 25, 50} were chosen after seeing the tree sweep in
  [the three-tree finding](three-tree-champion.md), which showed IC peaking near 10–25.
  Testing three pre-specified values is milder than taking an argmax, but it is not clean.
- Both markets' figures come from one holdout that has been read many times. A fresh panel
  period is what would confirm them.

Nothing is changed in the model. Setting a per-market round count is a modelling decision.

## Related

- [Why the champion has three trees](three-tree-champion.md) — the problem this tried to solve
- [Feature ablation and pruning](feature-ablation-and-pruning.md) — the other per-market
  disagreement
- [How to measure things here](../measurement.md)
