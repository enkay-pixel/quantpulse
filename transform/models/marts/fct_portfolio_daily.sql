-- Paper portfolio enriched with cumulative return and running drawdown.
select
    date,
    equity,
    daily_return,
    gross_exposure,
    net_exposure,
    turnover,
    model_version,
    equity - 1 as cumulative_return,
    equity / max(equity) over (order by date rows unbounded preceding) - 1 as drawdown
from {{ ref('stg_portfolio_snapshots') }}
