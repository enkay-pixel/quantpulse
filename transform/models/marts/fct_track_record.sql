-- One row per (market, evidence phase): the in-sample 'replay' and the accruing 'live'
-- out-of-sample record. Drawdown peaks reset at the phase boundary so the live record
-- stands on its own, and everything is scoped per exchange so one market's history
-- cannot leak into another's statistics.
--
-- Ratios are nulled below `min_days_for_ratios`. A live phase three days old annualizes
-- to a Sharpe of -54.93, which is noise wearing a precise-looking number. Counts and
-- totals stay: those are honest at any sample size.
{% set min_days = var('min_days_for_ratios', 20) %}
with daily as (
    select
        exchange,
        phase,
        date,
        daily_return,
        equity / max(equity) over (
            partition by exchange, phase order by date rows unbounded preceding
        ) - 1 as phase_drawdown
    from {{ ref('fct_portfolio_daily') }}
    where daily_return > -1
)

select
    exchange,
    phase,
    count(*) as n_days,
    min(date) as start_date,
    max(date) as end_date,
    exp(sum(ln(1 + daily_return))) - 1 as total_return,
    case
        when count(*) >= {{ min_days }} then stddev_samp(daily_return) * sqrt(252)
    end as annualized_volatility,
    case
        when count(*) >= {{ min_days }} and stddev_samp(daily_return) > 0
            then avg(daily_return) / stddev_samp(daily_return) * sqrt(252)
    end as sharpe,
    min(phase_drawdown) as max_drawdown,
    case
        when count(*) >= {{ min_days }}
            then avg(case when daily_return > 0 then 1.0 else 0.0 end)
    end as win_rate
from daily
group by exchange, phase
