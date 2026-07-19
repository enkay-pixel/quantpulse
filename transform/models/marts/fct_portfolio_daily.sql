-- Paper portfolio enriched with cumulative return, running drawdown, rolling
-- risk-adjusted performance, and the honest evidence boundary: dates before the
-- first champion promotion are an in-sample 'replay'; everything after is 'live'
-- out-of-sample track record.
with promotion as (
    select min(created_at)::date as first_live_date
    from {{ ref('stg_model_runs') }}
    where decision = 'promoted'
),

snapshots as (
    select
        date,
        equity,
        daily_return,
        gross_exposure,
        net_exposure,
        turnover,
        model_version
    from {{ ref('stg_portfolio_snapshots') }}
)

select
    s.date,
    s.equity,
    s.daily_return,
    s.gross_exposure,
    s.net_exposure,
    s.turnover,
    s.model_version,
    s.equity - 1 as cumulative_return,
    s.equity / max(s.equity) over (order by s.date rows unbounded preceding) - 1 as drawdown,
    case
        when p.first_live_date is not null and s.date >= p.first_live_date then 'live'
        else 'replay'
    end as phase,
    case
        when
            count(*) over w63 >= 21
            and stddev_samp(s.daily_return) over w63 > 0
            then
                avg(s.daily_return) over w63
                / stddev_samp(s.daily_return) over w63
                * sqrt(252)
    end as rolling_sharpe_63d
from snapshots as s
cross join promotion as p
window w63 as (order by s.date rows between 62 preceding and current row)
