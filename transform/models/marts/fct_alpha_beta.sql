-- CAPM decomposition of the strategy against its market's benchmark, per evidence phase.
--
-- Comparing a market-neutral long/short book to the index's raw return is apples to
-- oranges: the strategy deliberately gives up market beta, so it "should" trail the index
-- in a bull run. What actually matters is how much market exposure it carries (beta,
-- ideally ~0) and what it earns independently of the market (alpha), plus how reliably it
-- does so (information ratio). Postgres' built-in regression aggregates do the fit:
-- regr_slope(Y, X) with Y = strategy excess return, X = benchmark excess return.
--
-- Every output here is a regression statistic, so all of them are nulled below
-- `min_days_for_ratios`: a three-day window produced beta -0.07 and alpha -103%/yr,
-- which is arithmetic, not evidence.
{% set rf = var('risk_free_rate', 0.04) %}
{% set min_days = var('min_days_for_ratios', 20) %}

with joined as (
    select
        b.date,
        b.exchange,
        b.phase,
        p.daily_return as portfolio_return,
        b.benchmark_daily_return as benchmark_return
    from {{ ref('fct_portfolio_vs_benchmark') }} as b
    -- Joining on date alone would pair every market's return with every other's.
    inner join {{ ref('fct_portfolio_daily') }} as p
        on b.date = p.date and b.exchange = p.exchange
    where b.benchmark_daily_return is not null
),

excess as (
    select
        exchange,
        phase,
        portfolio_return - {{ rf }} / 252 as rp,
        benchmark_return - {{ rf }} / 252 as rb,
        portfolio_return - benchmark_return as active_return
    from joined
)

select
    exchange,
    phase,
    count(*) as n_days,
    case when count(*) >= {{ min_days }} then regr_slope(rp, rb) end as beta,
    case when count(*) >= {{ min_days }} then regr_intercept(rp, rb) end as alpha_daily,
    case when count(*) >= {{ min_days }} then regr_intercept(rp, rb) * 252 end
        as alpha_annualized,
    case when count(*) >= {{ min_days }} then regr_r2(rp, rb) end as r_squared,
    case when count(*) >= {{ min_days }} then corr(rp, rb) end as correlation,
    case when count(*) >= {{ min_days }} then stddev_samp(active_return) * sqrt(252) end
        as tracking_error,
    case
        when count(*) >= {{ min_days }} and stddev_samp(active_return) > 0
            then avg(active_return) / stddev_samp(active_return) * sqrt(252)
    end as information_ratio
from excess
group by exchange, phase
