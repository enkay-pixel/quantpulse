# Feature ablation result (2026-08-22)

`quantpulse ablation` refits without each feature in turn and with each feature alone, on
the same holdout the gate uses. Hyperparameters are held at defaults rather than retuned per
subset, so the "full model" below is a freshly fitted default-parameter model, **not the
champion**. It measures the feature set, not the deployed model.

## The first reading of this was wrong

The sweep was originally judged against each market's `ic_promotion_margin` (0.0060 XNYS,
0.0080 XJSE), and on that basis it was written up as having found the root cause: no feature
carrying signal on the NYSE, eight of thirteen actively costing it, single features scoring
double the full model.

That margin was the wrong yardstick, and the error was not small. It was measured on *tuned*
models selected by the gate. An ablation refits at default parameters, where early stopping
lands on a different tree count for every seed, and the spread under that procedure is far
larger. Measured directly — same panel, same parameters, same holdout, only the seed varied:

| market | seed IC spread (5 seeds) | sd | **2 sd** | margin originally used |
|---|---|---|---|---|
| XNYS | 0.0284 – 0.0726 | 0.0188 | **0.0375** | 0.0060 |
| XJSE | −0.0051 – 0.0250 | 0.0114 | **0.0228** | 0.0080 |

Every delta reported as a finding sat inside that floor. The largest, +0.0361, is below even
the 0.0375 it should have been judged against. The ranked list of "harmful" features was
seed noise, sorted.

`ablation_report` and `forward_select` now measure the floor themselves on each run rather
than borrowing one, and `forward_select` measures a second floor on the inner split, which
is smaller and therefore noisier than the full panel.

## What the corrected sweep shows

Two changes made the sweep able to resolve anything:

1. **Score across walk-forward folds, not one holdout.** A single holdout is one draw. Its
   seed-to-seed spread on this panel was wider than any effect a feature has, so a sweep
   judged on it ranks noise however carefully the margin is set. Averaging over the four
   purged folds shrinks that spread roughly with the square root of the fold count.
2. **Pair every comparison on the seed.** Each subset is scored against the full model
   fitted with the *same* seed, so the seed cancels rather than being carried into the
   comparison. Each feature then gets its own standard error instead of being judged against
   one global floor.

The second mattered more than the first. Fold-averaging alone dropped the floor from 0.0375
to 0.0136 on the NYSE, but it still reported **seven of thirteen** JSE features as
"costing signal" — and pairing showed **none of them** were. `ma_ratio_63` was the headline
of that list at +0.0238; paired across ten seeds it is +0.0032 ± 0.0033 (t +0.97), and its
per-seed differences change sign. The +0.0238 was simply the seed-42 draw, the largest of ten.

**A global floor cannot catch that.** It asks whether a point estimate is large; pairing asks
whether the difference is repeatable. Those come apart exactly when a draw is lucky, which is
the case the whole exercise is trying to detect.

## Results (paired, 4 folds x 10 seeds, re-run after the early-stopping fix)

Everything below was re-measured once `_fit_one` began stopping on IC. The earlier numbers on
this page were taken with RMSE stopping, which ended the NYSE fits after a single boosting
round, so they are superseded. The full-model IC roughly doubled on both markets (XNYS 0.0121
to 0.0272, XJSE 0.0114 to 0.0248) and the findings held with tighter errors.

**XNYS** — full-model IC 0.0272. Four features actively hurt:

| feature | delta | std err | t | verdict |
|---|---|---|---|---|
| vol_63 | **+0.0153** | 0.0017 | **+9.14** | costs signal |
| ma_ratio_63 | +0.0076 | 0.0011 | **+6.99** | costs signal |
| mom_63 | +0.0055 | 0.0014 | +3.99 | costs signal |
| ret_1 | +0.0035 | 0.0014 | +2.48 | costs signal |
| *(other nine)* | −0.0000 to +0.0030 | | \|t\| < 2 | within noise |

**XJSE** — full-model IC 0.0248. One helps, one hurts:

| feature | delta | std err | t | verdict |
|---|---|---|---|---|
| vol_63 | **−0.0133** | 0.0025 | **−5.35** | carries signal |
| ma_ratio_63 | +0.0047 | 0.0017 | +2.73 | costs signal |
| *(other eleven)* | −0.0036 to +0.0026 | | \|t\| < 1.9 | within noise |

**The markets still disagree about `vol_63`, and more sharply than before.** It is the most
harmful feature on the NYSE (t +9.14) and the only one on the JSE shown to help (t −5.35).
Both sides are now better resolved than in the pre-fix run, so this is not an artifact of the
stopping rule. `ma_ratio_63` hurts on both.

## Pruning, measured rather than inferred

`quantpulse prune` selects a set on the training portion, paired on the seed, and measures it
once on the untouched holdout — also paired.

| market | selected | pruned IC | full IC | paired delta | momentum |
|---|---|---|---|---|---|
| XNYS | vol_21 | 0.0645 | 0.0465 | **+0.0180** (t +5.76) | 0.0174 |
| XJSE | vol_63, vol_21, ret_21, ret_5_cs_rank | 0.0312 | 0.0569 | **−0.0256** (t −4.24) | 0.1094 |

**The two markets now answer differently, and the JSE answer is negative.** On the NYSE a
one-feature model beats all thirteen on data it never saw. On the JSE the selected set is
measurably *worse* than the full one: selection found four features that improved the inner
split and they did not carry to the holdout. That is selection overfitting, caught by the
holdout doing its job — "selected" is not "better", which is the entire reason the set is
measured after being chosen rather than inferred from the sweep.

A one-feature NYSE model beating thirteen is not a stopping artifact, as first suspected:
`vol_21` alone scores 0.0532 against the full model's 0.0272 *after* the fix.

The JSE's full model still scores 0.0569 against momentum's 0.1094, so none of this rescues
that market.

## The sweeps hold hyperparameters fixed, and that limits what they can say

Both the drop-one sweep and forward selection train at `DEFAULT_PARAMS`. That is deliberate:
retuning per subset varies two things at once, and the difference could no longer be
attributed to the feature. But it means every result above describes an **untuned** model,
and the deployed model is tuned by Optuna on every retrain.

Measured with tuning in the loop, at increasing sample size:

| market | untuned | tuned, 3 seeds | tuned, 8 seeds | tuned, 16 seeds |
|---|---|---|---|---|
| XNYS | +0.0180 (t +5.76) | +0.0150 ± 0.0147 (t 1.02) | +0.0128 ± 0.0072 (t 1.79) | **+0.0133 ± 0.0044 (t +3.00)** |
| XJSE | −0.0256 (t −4.24) | +0.0138 ± 0.0151 (t 0.92) | +0.0123 ± 0.0106 (t 1.16) | not run |

**On the NYSE, pruning survives tuning.** This page previously said it did not, twice, on
three and then eight seeds. That was a power problem read as a null result: the mean barely
moved across sample sizes (+0.0150, +0.0128, +0.0133) while the standard error fell as the
square root of n, which is a stable estimate waiting for resolution rather than an absent
effect. Eleven of sixteen seeds are positive.

The JSE remains unresolved at t +1.16 and would need roughly twenty-four seeds. It is not
worth the compute while that market loses to a fit-free momentum rule regardless.

Two caveats sit on the NYSE number, and they are the reason this is reported rather than
acted on:

- **`vol_21` was chosen on this panel.** Forward selection picked it from thirteen candidates
  using walk-forward folds *inside the training portion*, so the choice never saw the
  holdout — but the holdout has now been read many times across this work, and repeated
  looks at one window inflate confidence in whatever survives them. The claim this supports
  is "pruning helps here", not "`vol_21` is the right column".
- **+0.0133 is smaller than the ~0.03 round-to-round spread** from the early-stopping
  finding above. Pairing on the seed controls part of that, since both arms are tuned, but
  not all of it.

Confirming on a fresh panel period is what would settle both. Until then
`Exchange.feature_columns` stays at "all" on both markets: the field exists to carry this
decision, and the decision is a modelling change rather than a measurement.

## What actually survives as a finding

Stripping out everything the noise floor now disallows, two results stand:

- **The JSE model has no measurable skill.** Full-model IC 0.0054 ± 0.0114 across seeds —
  indistinguishable from zero — while fit-free momentum scores 0.1094 on the same holdout.
  This agrees with the standing-competitor comparison and is the stronger statement of it.
- **The NYSE model has weak positive skill.** IC 0.0521 ± 0.0188, against momentum's 0.0174.
  Small, noisy, but the model is doing something momentum alone does not.

The earlier conclusion — "the problem is the feature set" — is not supported. The feature
set has not been shown to be the problem or not to be; the measurement was never powerful
enough to say. What can be said is that the JSE model does not beat a one-line rule, which
was already known before this sweep ran.

Making the sweep able to answer the question needs more resolution than one holdout provides:
repeated splits or several walk-forward windows, averaging IC across them so the floor falls
below the effects being tested. That is the prerequisite for any feature decision, and it is
worth more than any change to the current feature list.

## Audit note (2026-08-30)

Checked against
[the seed-is-not-a-sample rule](../measurement.md#the-seed-is-not-a-sample-of-the-market)
after it refuted two sibling findings. **This page holds up better than any of them**, and for
the reason it states itself: it scores across four walk-forward folds rather than one holdout,
and pairs every comparison on the seed. That is most of the fix, arrived at independently.

Two limits remain, neither of which is a reason to discard anything here:

- The four folds are **fixed**. Averaging over them shrinks the noise floor but still describes
  one partition of one panel; it is not the same as rolling an origin across the period. The
  errors quoted are across seeds of a fold-averaged quantity, so they inherit the same
  weakness in weaker form.
- `vol_63` now has **two measurements pointing opposite ways**. This page has it carrying
  signal on the JSE (t −5.35) and costing it on the NYSE (t +9.14); scored as a univariate
  forward signal across 46 rolling origins it is
  [+0.0018 (t +0.0) on the JSE and +0.0878 (t +2.5) on the NYSE](model-staleness.md#what-the-jse-model-actually-learns).
  These are different quantities — marginal contribution inside a fitted model versus
  standalone forward IC — and they are not required to agree. But the same feature cannot be
  the one the JSE model most needs *and* carry no forward signal there, so one of the two is
  measuring something other than what it is being read as. Reconciling them is open work.

## Related

- [How to measure things here](../measurement.md) — the noise-floor and pairing rules
  this finding is the origin of
- [Baseline comparison](baseline-comparison.md) — the momentum rule the pruned sets are
  measured against
- [Why the champion has three trees](three-tree-champion.md) — the early-stopping fix
  that made these numbers worth re-running
