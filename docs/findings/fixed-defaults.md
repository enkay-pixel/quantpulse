# Can a fixed configuration replace the tuner? (pre-registered 2026-09-28)

**Measured 2026-10-04; everything above Results was on `main` before the run started**,
following the rule in [How to measure things here](../measurement.md#fix-the-decision-rule-before-the-run-where-the-merge-cannot-erase-it)
that a pre-registration committed to a feature branch is erased by the squash merge.

## Why this is being measured

[The tuning-budget work](tuning-budget.md) found that the tuner's search does no better than random,
that the folds do not order the holdout, and — the reason for both — that refitting identical
parameters with only the seed changed reproduces a trial's holdout score poorly: reliability 0.13
on XJSE and 0.33 on XNYS, so most of the variation the search tries to exploit is the fit's own
randomness.

That **predicts** a fixed configuration should do about as well as a searched one. The prediction
is stated here so that the test can falsify it; nothing is changed on the strength of it.

## The question is non-inferiority

A fixed configuration costs **1** fit per candidate. A tuned one costs **61** — fifteen trials
across four folds, then the chosen parameters fitted once more. A fixed configuration is also
deterministic, which removes the week-to-week parameter churn that the learning-rate collapses
came from. So it does not have to *win* to be worth adopting. It has to not *lose* by an amount that
matters.

That amount is the promotion gate's own margin, `Exchange.ic_promotion_margin`: **0.008 on XJSE,
0.006 on XNYS**, the difference the gate itself treats as luck rather than improvement. It is used
here as a threshold of **practical importance**, not as a noise floor — the statistics come from a
one-sided confidence bound. Borrowing a margin *as a significance test* is what the measurement rules
warn against; asking whether a loss is smaller than the gate would ever act on is a different use,
and the one that matches the decision.

## Arms

| arm | parameters | role |
|---|---|---|
| `tuned` | production's own tuner — `tune_hyperparameters`, 15 trials, default warm-up | **control** |
| `fixed_default` | `DEFAULT_PARAMS`, learning rate held under the market's ceiling | **the candidate** |
| `fixed_center` | the centre of the space the tuner searches | diagnostic only |

The exact configurations, derived by rule before any holdout was read:

| | learning rate | leaves | min data in leaf | feature fraction | L2 |
|---|---|---|---|---|---|
| XJSE `fixed_default` | 0.02 | 31 | 50 | 0.9 | 1.0 |
| XJSE `fixed_center` | 0.00447 | 52 | 110 | 0.75 | 0.1 |
| XNYS `fixed_default` | 0.05 | 31 | 50 | 0.9 | 1.0 |
| XNYS `fixed_center` | 0.01414 | 52 | 110 | 0.75 | 0.1 |

The centre is a geometric midpoint wherever the search is log-scaled (learning rate, L2) and an
arithmetic one elsewhere, read from the same bounds the search reads.

**Neither fixed arm is chosen by result.** Over ten thousand scored trials exist from the earlier
rounds, and picking whichever parameters did well in them would be selecting on the holdout. And
**only `fixed_default` is eligible for adoption**: choosing between the two fixed arms by which
scored better would be the same selection by a shorter route. `fixed_center` answers only whether
the particular fixed point matters.

## Design

- **The control is production**, not a reconstruction: the tuned arm calls the tuner the weekly
  retrain calls. On the shared origins it should reproduce the tuning-budget study's production arm
  **exactly**, cell by cell, and that is checked rather than assumed. A match would also confirm,
  after the fact, that the earlier rounds' production arm was faithful to production.
- The same origins as the tuning-budget work — XJSE 20, XNYS 36 — through the shared
  `rolling_origins`, and the same two seeds.
- Paired on origin and seed, seeds averaged within an origin, Newey-West across origins at
  `max_lag = 3`.
- **The floor for a paired difference is measured correctly this time**: how far the
  arm-minus-control difference moves when only the seed changes, inside an origin. The
  tuning-budget study's second round compared paired differences against the unpaired spread of a
  single arm, which double-counts the seed that pairing exists to cancel.

## Decision rule, fixed in advance

**0. Comparability first.** If the tuned arm does not reproduce the tuning-budget production arm cell
by cell, the run is not comparable to the earlier rounds and is reported that way. The comparison
*within* the run still stands, because both of its arms were fitted on identical panels.

Then, **per market**:

1. **If `fixed_default`'s one-sided 95% lower bound on (fixed − tuned) is above −margin**, it is
   non-inferior, and replacing the tuner on that market is **supported on this evidence, subject to
   a live check**. Nothing is changed in production from this run alone.
2. **Otherwise**, tuning is earning its cost on that market, and it stays.
3. **A point estimate near zero with a wide bound is not a pass.** It is an unresolved comparison, and
   is reported as one rather than as equivalence.

`fixed_center` feeds no decision. If it and `fixed_default` differ by more than the paired seed
spread, the report says the choice of fixed point matters — which would weaken any case for
"the defaults" as a single thing.

## Disclosures

- **XJSE's `fixed_default` sits exactly at the ceiling, 0.02**, and that ceiling was itself set on
  holdout IC by [the learning-rate experiment](learning-rate-ceiling.md), over panels that overlap
  these. So that arm is not wholly blind. The tuned arm searches under the same ceiling, so the
  dependence is shared by both arms and does not bias the comparison between them.
- The cost figure of 61 fits corrects one given in conversation while this was being designed,
  which said 75. That was the tuning-budget *experiment's* cost per trial, which also scored every
  trial on the holdout; production never does.
- Only holdout IC is compared. The gate's drawdown floor and Sharpe veto are not, so a
  non-inferiority result here is about the metric the gate decides on, not every check it runs.

## Disclosure: what the smoke test found, before the full run

Recorded here, on `main`, before the full run starts — the rule this page was written under.

**The origins moved between days, and rule 0 would have failed for a reason that had nothing to do
with the tuner.** The first smoke test ran after Monday's JSE ingest had added one labelled date,
and because `rolling_origins` lays its grid from the *end* of the data, that one date shifted every
XJSE origin by a few days. The tuning-budget rounds only reproduced each other because both ran on
the same Sunday. So the study was not reproducible across days, and nothing said so.

It now takes an `as_of` cutoff. **2026-08-26** reproduces the tuning-budget origins on both
markets — XJSE drops the one new date, and XNYS had none yet — and the full run is pinned to it,
which is what "the same origins as the tuning-budget work" requires.

**Rule 0 then passes, exactly.** On the three smoke origins the tuned arm reproduces the
tuning-budget study's production arm to 0.0 in holdout IC and in learning rate, all six cells. So
production's tuner and that study's production arm are the same thing — which retroactively
confirms that every round of the tuning-budget work was measuring the real tuner — and pinning
reproduces the panel, so Monday's ingest revised nothing historical in it.

**A near-miss worth recording.** The first attempt at the pinned run crashed on a date-type
mismatch, and a stale output file from the *unpinned* run was still in place. Compared against the
tuning-budget arm, it produced differences up to 0.024 and read as "rule 0 fails" — a conclusion
drawn from a crash. It was caught only because the run's own log lines were missing from the
output. The fix is covered by a test, and the smoke script now deletes its output before running
and checks the exit status. It is the same class as never piping a build to `/dev/null`: a hidden
failure plus an old artefact is indistinguishable from a result.

**The numbers the pinned smoke test showed**, recorded because they were seen, and three origins
is far below what the rule rests on:

| arm | vs `tuned` | lower bound | fits | median seconds |
|---|---|---|---|---|
| `fixed_default` | −0.0013 | −0.0023 | 1 | 0.42 |
| `fixed_center` | −0.0178 | −0.0244 | 1 | 0.34 |
| `tuned` | — | — | 61 | 23.4 |

Two things in it bear on the design rather than the answer:

- **The paired seed spread is several times the margin** — 0.036 for `fixed_default` against a
  margin of 0.008. A single retrain's tuned-versus-fixed difference is therefore dominated by the
  seed, and the rule relies on averaging over origins to resolve anything. That is what it was
  built to do, but it means the full run's bound, not any one origin, carries the verdict.
- **The cost claim holds in wall time**: about 23 seconds a tuned candidate against 0.4 for a fixed
  one, the ~60× the fit counts predict.

No threshold moves and no arm changes role. `fixed_default` stays the only candidate.

## Results

Measured 2026-10-04, pinned `--as-of 2026-08-26`. XJSE 20 origins, XNYS 36, two seeds — 336 cells.

**The first run of this measurement was lost unread.** It wrote to a session's temporary directory,
which a cleanup emptied before anyone looked; see
[How to measure things here](../measurement.md#keep-the-evidence-somewhere-that-outlives-the-session).
The figures below come from a rerun on the same pin, kept in
`~/quantpulse-experiments/fixed-defaults-asof-2026-08-26/`.

### Rule 0 holds on every cell that can still be checked

The tuning-budget trials it was to be checked against went with the same cleanup, so the check
survives only on the six cells the smoke test printed. On all six the tuned arm reproduces the
tuning-budget production arm **exactly**, to six decimals in holdout IC and in learning rate — a week
after the smoke test, with five more trading days in the database. The tuned arm's means also
reproduce the tuning-budget rounds exactly: 0.0353 on XJSE, 0.0340 on XNYS.

### XJSE — rule 1 fires: non-inferior, narrowly

| arm | holdout IC | vs `tuned` | t | worst plausible | favours |
|---|---|---|---|---|---|
| `tuned` | 0.0353 | — | — | — | — |
| **`fixed_default`** | 0.0330 | −0.0023 | −1.27 | **−0.0053** | 8/20 |
| `fixed_center` | 0.0264 | −0.0089 | −2.01 | −0.0162 | 4/20 |

Against a margin of −0.008, `fixed_default` is non-inferior under the pre-registered error. It stays
so under every error tried — but the paired differences autocorrelate at **−0.45**, which shrinks a
Newey-West error, and under the plain error that ignores it the worst case is **−0.0078**, inside the
line by 0.0002:

| error | worst plausible | verdict |
|---|---|---|
| plain | −0.0078 | non-inferior |
| Newey-West lag 1 | −0.0063 | non-inferior |
| Newey-West lag 3 (pre-registered) | −0.0053 | non-inferior |
| Newey-West lag 5 | −0.0049 | non-inferior |

An error of 0.0035 would flip it; the plain one is 0.0033. **Supported, but borderline.**

### XNYS — rule 1 fires, and the fixed configuration is better

| arm | holdout IC | vs `tuned` | t | worst plausible | favours |
|---|---|---|---|---|---|
| `tuned` | 0.0340 | — | — | — | — |
| **`fixed_default`** | **0.0464** | **+0.0123** | **+2.73** | **+0.0049** | **28/36** |
| `fixed_center` | 0.0323 | −0.0017 | −0.28 | −0.0118 | 14/36 |

The worst plausible case is above zero under every error tried (+0.0040 to +0.0073). The question
asked was non-inferiority; superiority is reported because it is there, not because it was the test,
and it should be read with that in mind.

### The fixed point matters

`fixed_center` fails non-inferiority on both markets while `fixed_default` passes. By the
pre-registered diagnostic the two differ by less than the paired seed spread (XJSE 0.0066 against
0.024–0.038; XNYS 0.014 against 0.027), so that rule does not flag it — but one fixed point passing
and the other failing on both markets says "a fixed configuration" is not one thing, and the case
here is for these defaults specifically, not for fixing parameters in general.

### Cost

A tuned candidate costs 61 fits and a median 13.8 s (XJSE) / 18.8 s (XNYS); a fixed one, 1 fit and
0.18 s / 0.24 s — about 76× faster, and deterministic.

### What this does not establish

- **These holdouts have been consulted many times.** Every tuning-budget round and this study read
  them, and the decision to look at fixed defaults at all came from them. A result on heavily-read
  windows is the kind this project has seen reverse before.
- **Holdout IC does not predict live returns well here** — the standing caveat on every holdout
  figure in this project.
- **XJSE already runs a fixed configuration in practice.** Its tuner has returned warm-up draw #2 for
  three straight weeks, so on XJSE the comparison is between two fixed points, not tuned and fixed.

## What follows

Not a switch. The pre-registered rule says replacing the tuner is supported *subject to a live
check*, and the caveats above are what that check is for. It is specified, before it starts, in
[the shadow run](shadow-run.md).
