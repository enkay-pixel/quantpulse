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
| **Model Development** | **2.0** | **Weakest. Sets the final score.** |
| ML Infrastructure | 4.0 | Strong gate and integration testing; no rollback, no canary |
| Monitoring | 6.0 | Strongest — this is where the incident log's lessons went |

**ML Test Score = 2.0** (the minimum), which the rubric reads as *basic productionisation* —
a first pass complete, with real gaps remaining.

The shape is the finding. Monitoring at 6.0 against model development at 2.0 says the
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

## Model Development — 2.0

| # | Test | Score | Evidence |
|---|---|---|---|
| 1 | Model specs reviewed and submitted | 0.5 | `TrainConfig` versioned in git, ADRs recorded; no second reviewer |
| 2 | Offline and online metrics correlate | **0** | The open question. Incident 24 showed stored holdout Sharpe 0.205 re-scoring to 2.570 — offline metrics are known unstable. Live record is 14–18 days, too short to correlate |
| 3 | All hyperparameters tuned | 1 | Optuna TPE, 15 trials, seeded |
| 4 | Impact of model staleness known | **0** | Retrains weekly by schedule, not by measured decay. No experiment relating performance to model age |
| 5 | A simpler model is not better | **0** | No baseline of any kind — no momentum-only, no linear, no zero-signal control |
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

## Gaps, ranked by value per unit of effort

1. **No simpler-model baseline** (Model 5). The cheapest and highest-signal gap. If a
   momentum-only rule or a linear model matches LightGBM-plus-Optuna on the same holdout,
   the entire ML layer is unjustified — and that is the first question any reviewer asks.
   Note the irony: the project's own standing preference is *build both, then measure*, and
   it has been applied to paper books but never to the model itself.
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
