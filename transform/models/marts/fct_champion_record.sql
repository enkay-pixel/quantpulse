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
with daily as (
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
)

select
    exchange,
    model_version,
    count(*) as n_days,
    min(date) as start_date,
    max(date) as end_date,
    exp(sum(ln(1 + daily_return))) - 1 as total_return,
    avg(daily_return) as avg_daily_return,
    min(champion_drawdown) as max_drawdown,
    case
        when count(*) >= {{ min_days }} and stddev_samp(daily_return) > 0
            then avg(daily_return) / stddev_samp(daily_return) * sqrt(252)
    end as sharpe,
    case
        when count(*) >= {{ min_days }}
            then avg(case when daily_return > 0 then 1.0 else 0.0 end)
    end as win_rate,
    -- Whether this model is the one currently scoring. A reader comparing two rows needs to
    -- know which is running now, and the dates alone do not say it: a demotion leaves the
    -- outgoing champion's last day adjacent to the incoming one's first.
    --
    -- Decided by the most recent live day, not by the highest version. model_version is text,
    -- so max() would rank 'v9' above 'v10' the moment a market reaches double digits — and
    -- the NYSE is already at nine.
    max(date) = max(max(date)) over (partition by exchange) as is_current
from daily
group by exchange, model_version
