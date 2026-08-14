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
| ML Infrastructure | 4.0 | Strong gate and integration testing; no rollback, no canary |
| Monitoring | 6.0 | Strongest — this is where the incident log's lessons went |

**ML Test Score = 2.5** (the minimum), which the rubric reads as *basic productionisation* —
a first pass complete, with real gaps remaining. Was 2.0 at the first scoring; closing the
baseline gap moved Model Development from 2.0 to 2.5.

The shape is the finding. Monitoring at 6.0 against model development at 2.5 says the
**pipeline around the model has had far more adversarial attention than the model itself**.
That is the direct consequence of how this was built: thirty incidents, almost all of them in
data movement, orchestration and serving, each one hardening the plumbing. Nothing forced
comparable scrutiny onto the modelling.

## Features and Data — 5.0

| # | Test | Score | Evidence |
|---|---|---|---|
| 1 | Feature expectations captured in a schema | 1 | `FEATURE_COLUMNS` + `FEATURE_VERSION`, DB CHECK constraints, 59 dbt data tests, `data/quality.py` |
| 2 | All features are beneficial | **0** | No importance, ablation or permutation study anywhere. 13 features chosen a priori and never pruned |
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

## ML Infrastructure — 4.0

| # | Test | Score | Evidence |
|---|---|---|---|
| 1 | Training is reproducible | 0.5 | `seed=42` through LightGBM and Optuna; but the panel grows with each backfill, so the same code on a later day draws a different holdout (incident 24). Deterministic given fixed data, not stable over time |
| 2 | Model specs unit tested | 1 | Promotion gate, CV, metrics and training config all covered |
| 3 | Full pipeline integration tested | 1 | 133 integration tests against a disposable DB running a real `dbt build` |
| 4 | Model quality validated before serving | 1 | The promotion gate — IC margin from measured seed noise, IC ≥ 0, drawdown floor, Sharpe veto, first-champion floor, incumbent re-scored on the candidate's exact holdout. The project's strongest single component |
| 5 | Debuggable on single examples | 0.5 | `/predictions/latest` and the positions endpoint allow inspecting a ticker-date; no dedicated debug path |
| 6 | Canary before serving | **0** | Promotion is an atomic alias switch to 100%. Mitigated by this being a paper book — nothing real is at risk |
| 7 | Quick and safe rollback | **0** | **No code performs a demotion.** The two demotion rows in `model_runs` were inserted by hand during incidents 17 and 24. Undoing a bad promotion means hand-editing MLflow *and* Postgres, with no tested procedure |

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

## Baseline comparison result (2026-08-14)

`quantpulse baseline` scores every competitor on one shared holdout, cut exactly as the
promotion gate would cut it, through the same `pipeline.score_holdout`. Momentum and reversal
are fitted on nothing at all; ridge is fitted on the training window; the champion is only
*scored*, exactly as the gate re-scores an incumbent.

**XJSE** — holdout 2025-04-15 → 2026-07-14, 311 sessions:

| model | IC | Sharpe | ann. return | max DD |
|---|---|---|---|---|
| noise | −0.0216 | −1.49 | −7.83% | −12.31% |
| **momentum** | **0.1167** | **2.28** | 19.34% | **−3.58%** |
| ridge | 0.0777 | 1.96 | 21.37% | −7.53% |
| champion v3 | 0.0681 | 1.84 | 19.35% | −7.53% |
| reversal | −0.0031 | −1.47 | −12.72% | −21.53% |

**XNYS** — holdout 2025-04-15 → 2026-07-15, 313 sessions:

| model | IC | Sharpe | ann. return | max DD |
|---|---|---|---|---|
| **champion v1** | **0.1907** | **2.48** | 54.43% | **−5.13%** |
| ridge | 0.0532 | 1.53 | 27.77% | −7.25% |
| momentum | 0.0161 | −0.22 | −5.01% | −10.86% |
| noise | −0.0015 | 0.47 | 5.70% | −6.53% |
| reversal | −0.0388 | −0.73 | −14.01% | −31.21% |

**The JSE champion does not earn its place.** Plain 63-day momentum beats it on every metric
— IC 0.117 against 0.068, Sharpe 2.28 against 1.84, and half the drawdown — with zero
parameters and zero fitting. The linear ridge beats it too. Momentum had no fitting advantage
whatsoever in this comparison, which makes the result harder to explain away, not easier.

**The NYSE champion clearly does.** IC 0.191 against ridge's 0.053 and momentum's 0.016, on
the same window. Whatever the model is finding on the US panel, momentum is not it.

Two things this also settles:

- **Noise scored Sharpe +0.47 on XNYS** while its IC was −0.0015. A signal containing nothing
  produced a positive-looking Sharpe. That is direct support for the project's decision to
  gate on IC rather than Sharpe, previously argued from a seed re-roll and now visible from
  a pure control.
- **Momentum and reversal score oppositely** (0.117 vs −0.003 on XJSE, 0.016 vs −0.039 on
  XNYS), so the backtest is responding to signal direction rather than to some artefact that
  would flatter anything ranked.

Caveats that belong with the numbers. This is **one holdout window**, and it overlaps the
momentum-rich stretch incident 24 identified (raw 63-day momentum IC +0.039 Mar–Dec 2025,
−0.004 after). One noise draw is not a distribution. Neither observation rescues the JSE
champion — momentum beat it *on the window the gate itself would have used* — but both mean
the right next step is repeating this across several windows before concluding how general it is.

## Gaps, ranked by value per unit of effort

1. ~~No simpler-model baseline~~ — **built, and momentum is now a standing competitor in
   the gate (2026-08-14).** No candidate is promoted on either market without beating a
   fit-free momentum rule by the per-market IC margin, first champions included. What
   remains is the *existing* XJSE champion, which loses to momentum and which the gate
   cannot touch: it governs promotion, not incumbency. Removing it needs the rollback path
   in Infra 7, which is why that is now the top gap.
2. **No rollback path** (Infra 7). Bad promotions are not hypothetical — two have happened.
   Recovery is currently hand-editing two systems that can disagree. A `quantpulse demote`
   that writes the audit row and moves the alias, with a test, closes it.
3. **Model staleness unmeasured** (Model 4). The weekly retrain cadence is arbitrary. One
   experiment — score a frozen champion forward and watch IC decay — turns it into a
   measurement.
4. **No feature ablation** (Data 2). Thirteen features, none justified individually.
5. **Offline/online correlation** (Model 2). Cannot be closed by work, only by time; it is
   what the live track record accrues toward.
6. **No canary** (Infra 6). Genuinely low priority while the book is paper.

## What the rubric does not cover

Three of this week's findings were environmental — a vendor misdating a bar into a gap,
JSE bars publishing two days late, an outage cascade. No rubric predicts vendor behaviour,
and those came from reality rather than review.

One more sits outside it entirely: on 2026-08-13 a wrong inference was written into
`CLAUDE.md` and the data dictionary as guidance, and a change was proposed on top of it that
would have written corrupt data. No checklist catches believing your own bad inference —
only measuring before acting does. Both failure sources are real, and they need different
remedies.
