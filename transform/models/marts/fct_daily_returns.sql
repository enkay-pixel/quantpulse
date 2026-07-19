-- Per-(ticker, date) daily simple returns with rolling risk stats.
with returns as (
    select
        ticker,
        date,
        close,
        volume,
        close / nullif(lag(close) over (partition by ticker order by date), 0) - 1
            as daily_return
    from {{ ref('stg_prices') }}
)

select
    ticker,
    date,
    close,
    volume,
    daily_return,
    stddev_samp(daily_return) over (
        partition by ticker
        order by date
        rows between 20 preceding and current row
    ) as volatility_21d,
    avg(daily_return) over (
        partition by ticker
        order by date
        rows between 20 preceding and current row
    ) as avg_return_21d
from returns
