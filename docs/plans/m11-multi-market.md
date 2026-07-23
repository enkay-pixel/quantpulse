# M11 — Multi-market: making "exchange" a first-class dimension

**Status: APPROVED 2026-07-23, Phase 1 in progress.** Written 2026-07-23.

## Decisions (settled at approval)

| | Decision |
|---|---|
| Q1 universe | JSE Top 40 (~28 usable). Widen only if evidence asks. |
| **Q2 shorting** | **Both.** Long/short *and* long-only, as separate books — not a choice. |
| Q3 models | Two — one champion per exchange. Attribution beats data volume. |
| Q4 currency | Convert ZAc → ZAR for display, label the axis. |
| Q5 staging | Split. Phase 1 alone, verified unchanged, before Phase 2. |

**Q2 generalises into a standing rule** (also in CLAUDE.md): where a *feature* decision has
several defensible answers, build each in its own context and let evidence choose. Not for
infrastructure or design decisions, where one answer is simply correct.

This changes the book invariant. Today `test_books_differ_only_in_rebalance_frequency`
requires every book to differ in exactly one field, which a long-only book would break.
The correct generalisation: books are **variations from a shared baseline**, each differing
from the baseline in exactly one dimension.

```
baseline   daily long/short          (rebalance 1d, short_weight 0.5)
  ├─ horizon    rebalance 1d → 21d   ← isolates trading cost
  └─ long_only  short_weight 0.5 → 0 ← isolates the contribution of the short leg
```

Each variation is comparable **to the baseline**, not to each other — `horizon` vs
`long_only` differs in two dimensions and is not a valid comparison. The test becomes
"every book differs from the baseline in exactly one field", and the API labels which
dimension each varies so the dashboard cannot invite an invalid comparison.

Long-only also answers a question the long/short book cannot: it is what an SA retail
investor could actually execute, given how thin scrip lending is.

## Goal

Run the platform against more than one exchange — NYSE today, the JSE next — with the
dashboard switching between them. The strategy, the evidence layer and the adaptation loop
should work per market, independently and comparably.

## What was verified first (not assumed)

Checked live against yfinance and `exchange_calendars` on 2026-07-23:

| Question | Answer |
|---|---|
| JSE daily bars, free? | **Yes** — `.JO` suffix. NPN/SOL/SBK return clean bars, current to today. |
| JSE trading calendar? | **Yes** — `XJSE` in `exchange_calendars`, 09:00–17:00 SAST. |
| Enough names? | **28 of 30** Top-40 constituents have >200 days of history. |
| Benchmark ETF? | **`STX40.JO`** (Satrix Top 40) — the SPY equivalent. Also `ETFT40.JO`. |
| Option chains? | **No.** `.options` is empty for every JSE name tried. |
| Currency? | **`ZAc`** — South African *cents*. NPN closed at 79,787 = R797.87. |

One finding argues *for* the JSE: mean pairwise correlation across the Top 40 is **0.207**,
against ~0.45 for US large caps. More idiosyncratic variation is more for a
cross-sectional model to rank, so the JSE may suit this strategy better than the S&P does.

Two findings argue for caution, and neither is a blocker so much as something to size
honestly:

- **28 names at 20% quintiles is ~6 per side**, against 10 for the US book. Per-position
  idiosyncratic risk roughly doubles. Expect a noisier equity curve and wider error bars on
  any conclusion.
- **Shorting the JSE is materially harder and dearer** than the 1%/yr the backtest charges
  for US large caps. Scrip lending is thinner and concentrated. See open question Q2.

## The change that actually matters

Not the plumbing. This, in `features/engineering.py`:

```python
df[f"{col}_cs_rank"] = df.groupby("date")[col].rank(pct=True)
```

Every ticker is ranked against every other on a date. Add JSE names and it ranks **Naspers
against Apple** — different currency, different session, different macro drivers. The
cross-sectional features silently degrade into noise, and nothing fails loudly.

That single line is why this is an architectural change and not a config change: exchange
has to be a real dimension carried through features, models, books, marts and API, not a
convention hidden in a ticker suffix.

## Staging — and why it is two phases

**Phase 1 makes exchange a dimension with NYSE as the only tenant. Phase 2 adds the JSE.**

The point of splitting them: if the abstraction and the second market land together, any
change in the numbers is unattributable — was it the refactor or the new data? Phase 1 has
an exact success criterion: **the champion, every metric, and all 172 tests are unchanged.**
Same discipline that made the two-book comparison meaningful.

---

## Phase 1 — exchange as a dimension (NYSE only)

### Schema (one Alembic migration)

Minimal denormalization; `universe` stays the source of truth.

| Table | Change | Why |
|---|---|---|
| `universe` | `+ exchange String(8) NOT NULL DEFAULT 'XNYS'` | source of truth |
| `portfolio_snapshots` | `+ exchange`, PK → `(date, exchange, variant)` | a book is per-market; it has no ticker to join through |
| `model_runs` | `+ exchange` | which market's champion this decision was about |

`prices`, `features`, `predictions` get **no** column — tickers are globally unique
(`.JO` suffix), so they join `universe` when exchange is needed. Keeps the migration small
and avoids denormalisation drift.

### Code

- **`data/calendar.py`** — replace the `XNYS` constant with a small registry:
  ```python
  @dataclass(frozen=True)
  class Exchange:
      code: str          # 'XNYS'
      calendar: str      # 'XNYS'
      tz: ZoneInfo       # America/New_York
      close_hour: int    # 16
      currency: str      # 'USD'
      benchmark: str     # 'SPY'
      has_options: bool  # True
  ```
  `market_today(exchange)`, `is_post_close(exchange)`, `trading_days(exchange, …)`,
  `is_trading_day(exchange, day)` all take it. Default `XNYS` so nothing else changes yet.
- **`features/engineering.py`** — `compute_features` takes bars carrying `exchange` and
  groups cross-sectional ranks by `["date", "exchange"]`. **The core fix.**
- **`ml/registry.py`** — `MODEL_NAME` becomes `f"quantpulse-lgbm-{exchange.lower()}"`.
  Existing `quantpulse-lgbm` is renamed to `quantpulse-lgbm-xnys` in MLflow (one API call,
  preserves versions and the `@champion` alias).
- **`ml/portfolio.py`** — books built per exchange; `variant` unchanged, `exchange` added
  alongside it.
- **`data/universe.py`** — `universe.yaml` gains exchange grouping (below); `UniverseEntry`
  gains `exchange`.
- **`orchestration/`** — see partitioning, below.
- **`api/routes.py`** — every portfolio/evidence endpoint takes `?exchange=XNYS` (default
  preserves current behaviour). `/exchanges` lists what is configured, for the UI switcher.

### dbt

Seven marts gain an `exchange` dimension by joining `stg_universe`:
`dim_universe`, `fct_daily_returns`, `fct_signal_performance`, `fct_portfolio_daily`,
`fct_portfolio_vs_benchmark`, `fct_track_record`, `fct_alpha_beta`.

The benchmark ticker moves from hardcoded `'SPY'` to a per-exchange var. The two options
marts (`fct_option_summary`, `fct_iv_surface`) stay single-market by design.

### Config shape

```yaml
exchanges:
  XNYS:
    calendar: XNYS
    timezone: America/New_York
    close_hour: 16
    currency: USD
    benchmark: SPY
    has_options: true
    etfs: [SPY, QQQ, ...]
    stocks: [AAPL, MSFT, ...]
```

### Phase 1 done when

- `make test` green with the **same 172 tests** plus new ones for the registry and grouping
- champion unchanged, `holdout_sharpe` **0.205** unchanged
- both books' numbers unchanged: daily **7.76% / 0.73**, horizon **14.40% / 1.31**
- dashboard visually identical
- a new test asserts cross-sectional ranks never mix exchanges

---

## Phase 2 — add the JSE

- `configs/universe.yaml` gains the `XJSE` block: ~28 Top-40 names + `STX40.JO` benchmark.
- **Options tab hidden** when `has_options: false`, with a one-line explanation rather than
  an empty panel — no free JSE chain data exists, and the UI should say so.
- **Currency formatting**: `formatMoney(value, exchange)`. JSE quotes in cents, so display
  divides by 100 and renders `R797.87`. 15 components currently hardcode `$`.
- **Backfill**: `quantpulse backfill --exchange XJSE` from 2018 where history allows.
- **Schedules**: JSE post-close ingest at 17:30 SAST, processing 18:00 SAST — during your
  working day, unlike NYSE's 00:30 SAST.
- **First champion** trained for XJSE; promotion gate unchanged.

### Phase 2 done when

- Both markets ingest on their own calendars, including divergent holidays
- The dashboard switches markets, and the switch is in the URL (alongside the tab hash)
- The JSE Evidence tab reads honestly with ~6 names per side — including a caveat about
  breadth that the US book does not need

---

## Partitioning — a real decision, not a detail

`raw_prices` is currently `DailyPartitionsDefinition(timezone="America/New_York")`.

**Recommended: `MultiPartitionsDefinition({"date": daily, "exchange": static})`.** It is the
honest model — a JSE holiday is not an NYSE holiday, and each market needs its own
post-close schedule.

The cost is that existing daily partition keys are orphaned. **This is cosmetic**: the
`prices` table is untouched, and the catch-up sensor reads coverage from `prices`, not from
Dagster's partition state. What is lost is materialization *history* in the Dagster UI.

Alternative — keep one date dimension and loop exchanges inside the asset — avoids that,
but forces one schedule to serve both closes (00:30 SAST, losing the working-day benefit)
and makes per-market backfill clumsy. **I recommend eating the cosmetic loss.**

---

## Risks

| Risk | Mitigation |
|---|---|
| Silent cross-exchange contamination in features | Explicit test; Phase 1 gate is "numbers unchanged" |
| MLflow rename loses champion history | Rename preserves versions + alias; verify before deleting anything |
| JSE thinness produces noisy, over-read results | State breadth in the UI; quintiles may need to widen to 30% |
| Scope creep into currency conversion / cross-market portfolios | **Explicitly out of scope.** Books never mix currencies. |
| Options layer assumed multi-market | `has_options` flag; tab hidden, marts untouched |

## Explicitly out of scope

- Cross-market portfolios or FX conversion — each book is one market, one currency
- JSE options (no free data)
- Intraday anything
- Replacing the NYSE book as the primary track record

## Effort

Phase 1 ≈ 1–2 sessions (schema, calendar registry, features, registry, marts, API, tests).
Phase 2 ≈ 1 session (config, backfill, currency, switcher, first JSE champion).
Comparable to M9 (options).

---

## Resolved

All five settled at approval — see the decisions table at the top. Q2 became "build both",
which reshaped the book invariant and added a third book to Phase 1's scope.
