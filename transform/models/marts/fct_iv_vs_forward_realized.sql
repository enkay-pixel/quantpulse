-- Per (ticker, snapshot): implied volatility beside the volatility that then arrived over the
-- next 21 sessions. The forward variance risk premium — positive means options were priced
-- above the movement that followed, which is the comparison an option's price is actually
-- making. fct_iv_vs_realized compares against the trailing 21 days instead, which every
-- snapshot has; this one needs each realization window to close, so the newest month of
-- snapshots has no row yet.
--
-- Forward realized volatility is fct_daily_returns.volatility_21d moved forward: the sample
-- standard deviation of the next 21 daily simple returns, annualized by sqrt(252) to match
-- atm_iv, which the vendor supplies annualized. A window with fewer than 21 returns has not
-- closed, and is dropped rather than read as a shorter one.
with forward as (
    select
        ticker,
        date,
        stddev_samp(daily_return) over next_21 as forward_vol_daily,
        count(daily_return) over next_21 as forward_returns
    from {{ ref('fct_daily_returns') }}
    window next_21 as (
        partition by ticker
        order by date
        rows between 1 following and 21 following
    )
)

select
    s.ticker,
    u.exchange,
    s.snapshot_date,
    s.atm_iv,
    s.atm_days,
    f.forward_vol_daily * sqrt(252) as forward_realized_vol_21d,
    r.volatility_21d * sqrt(252) as trailing_realized_vol_21d,
    s.atm_iv - f.forward_vol_daily * sqrt(252) as forward_premium,
    s.atm_iv - r.volatility_21d * sqrt(252) as trailing_premium
from {{ ref('fct_option_summary') }} as s
inner join forward as f
    on f.ticker = s.ticker and f.date = s.snapshot_date
inner join {{ ref('fct_daily_returns') }} as r
    on r.ticker = s.ticker and r.date = s.snapshot_date
inner join {{ ref('dim_universe') }} as u
    on u.ticker = s.ticker
where f.forward_returns = 21
  and r.volatility_21d is not null
