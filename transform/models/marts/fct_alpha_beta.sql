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
-- which is arithmetic, not evidence. That floor is necessary and not sufficient — a window
-- can clear it and still resolve nothing — so alpha carries its own standard error and
-- t-statistic, and a consumer that quotes the alpha without them is quoting noise.
--
-- Note alpha and `information_ratio` answer different questions and can disagree in sign:
-- alpha is beta-adjusted (what is left once market exposure is removed) while the
-- information ratio is benchmark-relative (raw active return over tracking error). For a
-- deliberately market-neutral book in a rising market, a positive alpha beside a negative
-- information ratio is the expected result, not a contradiction.
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
    -- Standard error of the intercept, so alpha can be read against its own uncertainty
    -- rather than as a measured quantity. A short window produces a large one: over the
    -- first few weeks live the error exceeds the estimate, which is the difference between
    -- "earned this" and "cannot tell yet". `min_days` alone never catches that, because it
    -- gates on how many days exist and not on whether they resolve anything.
    --   SE(a) = sqrt( SSE/(n-2) * (1/n + avgx^2/Sxx) ),  SSE = Syy - Sxy^2/Sxx
    case
        when count(*) >= {{ min_days }} and count(*) > 2 and regr_sxx(rp, rb) > 0
            then sqrt(
                (regr_syy(rp, rb) - regr_sxy(rp, rb) * regr_sxy(rp, rb) / regr_sxx(rp, rb))
                / (count(*) - 2)
                * (1.0 / count(*) + regr_avgx(rp, rb) * regr_avgx(rp, rb) / regr_sxx(rp, rb))
            ) * 252
    end as alpha_std_error_annualized,
    -- Intercept over its standard error. Above ~2 in absolute value the alpha is
    -- distinguishable from zero at roughly two sigma; below it, the window has not
    -- separated the signal from noise whatever the headline number says.
    case
        when count(*) >= {{ min_days }} and count(*) > 2 and regr_sxx(rp, rb) > 0
            and (regr_syy(rp, rb) - regr_sxy(rp, rb) * regr_sxy(rp, rb) / regr_sxx(rp, rb)) > 0
            then regr_intercept(rp, rb) / sqrt(
                (regr_syy(rp, rb) - regr_sxy(rp, rb) * regr_sxy(rp, rb) / regr_sxx(rp, rb))
                / (count(*) - 2)
                * (1.0 / count(*) + regr_avgx(rp, rb) * regr_avgx(rp, rb) / regr_sxx(rp, rb))
            )
    end as alpha_t_stat,
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
