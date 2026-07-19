-- Strategy equity next to a SPY buy-and-hold benchmark indexed to 1.0 at the
-- portfolio's first date. A long/short model that can't beat "just hold SPY"
-- should have to say so on its own dashboard.
with portfolio as (
    select
        date,
        equity as portfolio_equity,
        phase
    from {{ ref('fct_portfolio_daily') }}
),

spy as (
    select
        date,
        close
    from {{ ref('stg_prices') }}
    where ticker = 'SPY'
),

joined as (
    select
        p.date,
        p.phase,
        p.portfolio_equity,
        s.close,
        first_value(s.close) over (order by p.date) as first_close,
        s.close / nullif(lag(s.close) over (order by p.date), 0) - 1
            as benchmark_daily_return
    from portfolio as p
    inner join spy as s on p.date = s.date
)

select
    date,
    phase,
    portfolio_equity,
    close / first_close as benchmark_equity,
    benchmark_daily_return
from joined
