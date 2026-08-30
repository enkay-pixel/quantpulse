# ML Test Score audit (2026-08-14)

Scored against the rubric in **"The ML Test Score: A Rubric for ML Production Readiness and
Technical Debt Reduction"** (Breck, Cai, Nielsen, Salib, Sculley — Google, IEEE Big Data
2017): 28 tests in four sections, scored 0 (absent), 0.5 (done manually or documented but
not automated), 1 (automated and repeatable). The final score is the **minimum** of the four
section totals, not the average — the rubric's whole point is that balance matters, and a
system is only as production-ready as its weakest dimension.

> Scored from the rubric's structure as recalled, not from a copy of the paper open at the
> time. The 28 item headings and the scoring bands should be checked against the original
> before this is quoted externally. The per-item evidence below is from the codebase and is
> exact.

**Why this exists.** Seven fault-injection drills on 2026-08-13 found four bugs, and every
one mapped to a documented failure pattern with a known preventive — two root causes
(boundary-value testing, duplicated state) accounted for all of them. Ad-hoc drilling was
rediscovering textbook material at high cost. A published rubric says what to look for
instead of waiting to be surprised, and produces a claim that can be cited.

## Score

| Section | Total | Reading |
|---|---|---|
| Features and Data | 5.0 | Strong — schema, quality gates, tested feature code |
| **Model Development** | **2.5** | **Weakest. Sets the final score.** |
| ML Infrastructure | 5.0 | Strong gate, integration testing and rollback; no canary |
| Monitoring | 6.0 | Strongest — this is where the incident log's lessons went |

**ML Test Score = 2.5** (the minimum), which the rubric reads as *basic productionisation* —
a first pass complete, with real gaps remaining. Was 2.0 at the first scoring; the baseline
gate moved Model Development to 2.5 and the rollback path moved Infrastructure to 5.0.

Note what the second of those did to the headline: **nothing**. Infrastructure went from 4.0
to 5.0 and the score did not move, because Model Development is the binding constraint. That
is the rubric working as designed — it refuses to let strength in one dimension pay for
weakness in another, and it says plainly where the next effort belongs.

The shape is the finding. Monitoring at 6.0 against model development at 2.5 says the
**pipeline around the model has had far more adversarial attention than the model itself**.
That is the direct consequence of how this was built: thirty incidents, almost all of them in
data movement, orchestration and serving, each one hardening the plumbing. Nothing forced
comparable scrutiny onto the modelling.

## Features and Data — 5.0

| # | Test | Score | Evidence |
|---|---|---|---|
| 1 | Feature expectations captured in a schema | 1 | `FEATURE_COLUMNS` + `FEATURE_VERSION`, DB CHECK constraints, 59 dbt data tests, `data/quality.py` |
| 2 | All features are beneficial | 0.5 | `quantpulse ablation` and `quantpulse prune` run drop-one, single-feature and forward-selection sweeps against a floor measured per run. The study exists, but **it is underpowered**: on one holdout the seed-only spread (2 sd 0.0375 / 0.0228) exceeds every effect being tested, so no feature is shown to help or hurt |
| 3 | No feature's cost is too much | 0.5 | All derived from stored OHLCV, vectorized, full recompute ~4s — bounded in practice, never measured per feature |
| 4 | Features meet meta-level requirements | 1 | Market data only, no PII; gitleaks over every staged diff on a public repo |
| 5 | Pipeline has privacy controls | 1 | No personal data exists; loopback-only ports; credentials in `.env` |
| 6 | New features can be added quickly | 0.5 | Vectorized `compute_features` + version bump, but no automated history migration |
| 7 | All input feature code is tested | 1 | `tests/unit/test_features.py` |

## Model Development — 2.5

| # | Test | Score | Evidence |
|---|---|---|---|
| 1 | Model specs reviewed and submitted | 0.5 | `TrainConfig` versioned in git, ADRs recorded; no second reviewer |
| 2 | Offline and online metrics correlate | **0** | The open question. Incident 24 showed stored holdout Sharpe 0.205 re-scoring to 2.570 — offline metrics are known unstable. Live record is 14–18 days, too short to correlate |
| 3 | All hyperparameters tuned | 1 | Optuna TPE, 15 trials, seeded |
| 4 | Impact of model staleness known | **0** | Retrains weekly by schedule, not by measured decay. No experiment relating performance to model age |
| 5 | A simpler model is not better | 0.5 | `quantpulse baseline` runs the comparison, and since 2026-08-14 the promotion gate **enforces** it — no candidate is promoted without beating momentum. Still 0.5, not 1: the property remains violated for the XJSE *incumbent*, and the gate governs promotion, not incumbency |
| 6 | Quality sufficient on important slices | 0.5 | Per-market slices are first-class (own champion, own IC margin, own quantile width); no within-market slices by liquidity, size or volatility regime |
| 7 | Inclusion / fairness | **0** | No protected classes in market data. The honest analogue — does the signal work across liquidity and size tiers, or only in the largest names? — is unmeasured |

## ML Infrastructure — 5.0

| # | Test | Score | Evidence |
|---|---|---|---|
| 1 | Training is reproducible | 0.5 | `seed=42` through LightGBM and Optuna; but the panel grows with each backfill, so the same code on a later day draws a different holdout (incident 24). Deterministic given fixed data, not stable over time |
| 2 | Model specs unit tested | 1 | Promotion gate, CV, metrics and training config all covered |
| 3 | Full pipeline integration tested | 1 | 140 integration tests against a disposable DB running a real `dbt build` |
| 4 | Model quality validated before serving | 1 | The promotion gate — IC margin from measured seed noise, IC ≥ 0, drawdown floor, Sharpe veto, first-champion floor, incumbent re-scored on the candidate's exact holdout. The project's strongest single component |
| 5 | Debuggable on single examples | 0.5 | `/predictions/latest` and the positions endpoint allow inspecting a ticker-date; no dedicated debug path |
| 6 | Canary before serving | **0** | Promotion is an atomic alias switch to 100%. Mitigated by this being a paper book — nothing real is at risk |
| 7 | Quick and safe rollback | 1 | `quantpulse demote --exchange X --reason "…"` (2026-08-14), with `--dry-run`. Writes the audit row and moves the alias in an order that leaves the trail untouched if the registry refuses; falls back to the newest promotion with no later demotion, or clears the alias when there is none |

## Monitoring — 6.0

| # | Test | Score | Evidence |
|---|---|---|---|
| 1 | Dependency changes notify | 1 | Dependabot weekly, grouped, documented major ignores, CI on every PR |
| 2 | Data invariants hold | 1 | `run_quality_checks`, `recent_prices_quality`, `benchmark_freshness`, `option_snapshot_quality`, 59 dbt tests |
| 3 | Training and serving compute the same features | 1 | Structurally identical — one `features` table feeds both paths through the same `FEATURE_COLUMNS`. Skew is impossible by construction rather than checked for |
| 4 | Models are not too stale | 1 | `predictions_are_current` (4-day lag ceiling), drift sensor, weekly retrain |
| 5 | Model numerically stable | 0.5 | NaN never promotes; `dropna` guards on ingest; ratios nulled below 20 days. No explicit NaN/Inf monitoring on prediction output |
| 6 | Computing performance not regressed | 0.5 | `resource_headroom` covers memory and disk; training time and serving latency untracked |
| 7 | Prediction quality not regressed | 1 | Per-market KS/PSI drift, IC-based gate, `fct_signal_performance` quintile readout, live track record |

## Findings this audit produced

The gaps below were closed by measurement, and each investigation is written up separately in
[findings/](findings/) rather than inline here — this file is the scorecard, not the lab
notebook. The method they share is stated once in
[How to measure things here](measurement.md).

| Finding | What it settled |
|---|---|
| [Baseline comparison](findings/baseline-comparison.md) | The JSE model loses to a one-line momentum rule; momentum is now a standing competitor in the gate |
| [Feature ablation and pruning](findings/feature-ablation-and-pruning.md) | The markets disagree about the same feature; pruning helps the NYSE under tuning |
| [Why nothing could beat the NYSE incumbent](findings/unbeatable-incumbent.md) | The promotion stall was a training-panel artifact, not skill |
| [Model staleness](findings/model-staleness.md) | **Corrected 2026-08-30** — no decay on either market at 46 origins; the original six-week result was a five-origin artifact |
| [Why the champion has three trees](findings/three-tree-champion.md) | **Re-measured 2026-08-30** — the inner split neither predicts nor anti-predicts the holdout; stopping on it is indistinguishable from picking a round at random |
| [Can the round count be chosen well?](findings/round-count.md) | **Corrected 2026-08-30** — the per-market result was one holdout's draw; no round count is shown to suit either market |

## Gaps, ranked by value per unit of effort

1. ~~No simpler-model baseline~~ — **built, and momentum is now a standing competitor in
   the gate (2026-08-14).** No candidate is promoted on either market without beating a
   fit-free momentum rule by the per-market IC margin, first champions included. What
   remains is the *existing* XJSE champion, which loses to momentum and which the gate
   cannot touch: it governs promotion, not incumbency. Withdrawing it is now a single
   command (`quantpulse demote`, built the same day) — but whether to pull it is a judgement
   call, not something the pipeline should make.
2. **Model staleness still unmeasured** — measured 2026-08-23, **retracted 2026-08-30**. The
   six-week NYSE bound and the rising JSE curve were both artifacts of a five-origin sample;
   at 46 origins neither market decays. The weekly cadence has no measured support and no
   measured objection. Re-opening this is cheap — the harness is right, it simply needs the
   origin rolled across the period rather than sampled at five points — and it is worth doing
   before any cadence change is argued from evidence.
3. ~~No feature ablation~~ — **built and run 2026-08-22; the sweep is underpowered on one
   holdout.** Drop-one, single-feature and forward selection all exist, and all report the
   same thing: the seed-only noise floor (0.0375 XNYS, 0.0228 XJSE) is larger than any
   effect being measured, so nothing survives pruning and nothing is shown to be harmful.
   The next step is not a feature change but more resolution — repeated splits or several
   walk-forward windows, averaged, so the floor drops below the effects. Every feature
   decision waits on that.
4. **Offline/online correlation** (Model 2). Still open, and still not closeable by work —
   only by time. The live record is 24 NYSE and 20 JSE sessions, which is far too short to
   correlate against anything. Worth revisiting at roughly 250 sessions, and worth noting
   that the strongest evidence gathered this year points the wrong way: the NYSE incumbent
   scored 0.1777 on its holdout while the live book lost money, which is one data point
   against holdout IC predicting live behaviour at all.
5. **No canary** (Infra 6). Declined for now rather than merely deprioritised. A canary
   answers "does the new model behave sanely on live traffic before it takes over", and
   this book is paper — the promotion gate already re-scores both models on the same
   holdout, and a bad promotion costs a paper drawdown and a `quantpulse demote`. Revisit
   if real money is ever attached.

## What the rubric does not cover

Three of this week's findings were environmental — a vendor misdating a bar into a gap,
JSE bars publishing two days late, an outage cascade. No rubric predicts vendor behaviour,
and those came from reality rather than review.

One more sits outside it entirely: on 2026-08-13 a wrong inference was written into
`CLAUDE.md` and the data dictionary as guidance, and a change was proposed on top of it that
would have written corrupt data. No checklist catches believing your own bad inference —
only measuring before acting does. Both failure sources are real, and they need different
remedies.
