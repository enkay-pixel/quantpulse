-- Strategy equity next to that market's buy-and-hold benchmark, indexed to 1.0 at the
-- portfolio's first date. A long/short model that can't beat "just hold the index"
-- should have to say so on its own dashboard.
--
-- The benchmark is per market (SPY for NYSE, the Top 40 tracker for the JSE) — comparing
-- a JSE book to SPY would measure the rand and the S&P, not the strategy.
with portfolio as (
    select
        date,
        exchange,
        equity as portfolio_equity,
        phase
    from {{ ref('fct_portfolio_daily') }}
),

benchmarks as (
    {{ benchmark_map() }}
),

benchmark_prices as (
    select
        p.date,
        p.exchange,
        p.close
    from {{ ref('stg_prices') }} as p
    inner join benchmarks as b
        on p.exchange = b.exchange and p.ticker = b.benchmark_ticker
),

joined as (
    select
        p.date,
        p.exchange,
        p.phase,
        p.portfolio_equity,
        s.close,
        first_value(s.close) over (
            partition by p.exchange order by p.date
        ) as first_close,
        s.close / nullif(
            lag(s.close) over (partition by p.exchange order by p.date), 0
        ) - 1 as benchmark_daily_return
    from portfolio as p
    inner join benchmark_prices as s on p.date = s.date and p.exchange = s.exchange
)

select
    date,
    exchange,
    phase,
    portfolio_equity,
    close / first_close as benchmark_equity,
    benchmark_daily_return
from joined
