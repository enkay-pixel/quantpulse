-- One row per (market, champion) over the live phase only: what each deployed model has
-- actually earned, rather than what the market has earned across all of them.
--
-- fct_track_record answers "how is this market doing live", which pools every champion that
-- has ever held the alias. That is the right question for the market and the wrong one for a
-- model: after a demotion the headline is dominated by the model that was withdrawn, and
-- stays that way for months. On 2026-08-26 the NYSE live record was 26 sessions, of which 25
-- belonged to a champion demoted three days earlier.
--
-- Replay is excluded on purpose. Every replay day was scored by whichever champion existed
-- when the backfill ran, so attributing in-sample days to a model says nothing about it.
--
-- Ratios are nulled below `min_days_for_ratios`, the same floor fct_track_record uses. A
-- champion with one live day has a win rate of 100% and a Sharpe that does not exist; the
-- count and the total return are honest at any size, and the rest is not.
{% set min_days = var('min_days_for_ratios', 20) %}
-- The model holding the alias right now: the latest promotion not since withdrawn. Taken
-- from the audit trail rather than from the live days, because a champion promoted on a
-- non-trading day has no live days at all — v10 was promoted on a Saturday and the previous
-- champion would have been labelled "current" until Monday's session landed.
--
-- Not from max(model_version) either: that column is text, so it ranks 'v9' above 'v10'.
with current_champion as (
    select distinct on (exchange) exchange, model_version
    from {{ ref('stg_model_runs') }} m
    where run_type = 'train' and decision = 'promoted'
      and not exists (
          select 1 from {{ ref('stg_model_runs') }} d
          where d.run_type = 'demotion' and d.exchange = m.exchange
            and d.model_version = m.model_version and d.created_at > m.created_at)
    order by exchange, created_at desc
),

daily as (
    select
        exchange,
        model_version,
        date,
        daily_return,
        equity / max(equity) over (
            partition by exchange, model_version order by date rows unbounded preceding
        ) - 1 as champion_drawdown
    from {{ ref('fct_portfolio_daily') }}
    where phase = 'live' and daily_return > -1
),

scored as (
    select
        d.exchange,
        d.model_version,
        count(*) as n_days,
        min(d.date) as start_date,
        max(d.date) as end_date,
        exp(sum(ln(1 + d.daily_return))) - 1 as total_return,
        avg(d.daily_return) as avg_daily_return,
        min(d.champion_drawdown) as max_drawdown,
        case
            when count(*) >= {{ min_days }} and stddev_samp(d.daily_return) > 0
                then avg(d.daily_return) / stddev_samp(d.daily_return) * sqrt(252)
        end as sharpe,
        case
            when count(*) >= {{ min_days }}
                then avg(case when d.daily_return > 0 then 1.0 else 0.0 end)
        end as win_rate
    from daily d
    group by d.exchange, d.model_version
)

-- Full join, so the model holding the alias appears even before it has scored anything. A
-- champion promoted on a Saturday has no live days until Monday, and dropping its row would
-- leave the card showing only withdrawn models with nothing marking the one actually running
-- — the precise omission this table exists to correct.
select
    coalesce(s.exchange, c.exchange) as exchange,
    coalesce(s.model_version, c.model_version) as model_version,
    coalesce(s.n_days, 0) as n_days,
    s.start_date,
    s.end_date,
    s.total_return,
    s.avg_daily_return,
    s.max_drawdown,
    s.sharpe,
    s.win_rate,
    c.model_version is not null as is_current
from scored s
full join current_champion c
    on c.exchange = s.exchange and c.model_version = s.model_version
