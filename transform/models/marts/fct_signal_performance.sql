-- Does the model's ranking work? Signals are bucketed into quintiles per (date, market)
-- (1 = strongest buy signal) and paired with the NEXT day's realized return.
-- If the model has skill, quintile 1 should out-earn quintile 5 on average.
--
-- The ntile partitions by exchange for the same reason the features do: ranking a JSE
-- name against a US one compares different currencies, sessions and macro drivers, and
-- the resulting quintiles would be meaningless without anything failing.
with signals as (
    select
        p.ticker,
        u.exchange,
        p.date,
        p.score,
        ntile(5) over (
            partition by p.date, u.exchange order by p.score desc
        ) as signal_quintile
    from {{ ref('stg_predictions') }} as p
    inner join {{ ref('stg_universe') }} as u on p.ticker = u.ticker
),

realized as (
    select
        ticker,
        date,
        lead(daily_return) over (partition by ticker order by date) as next_day_return
    from {{ ref('fct_daily_returns') }}
)

select
    s.date,
    s.exchange,
    s.signal_quintile,
    count(*) as n_tickers,
    avg(s.score) as avg_score,
    avg(r.next_day_return) as avg_next_day_return,
    min(r.next_day_return) as worst_next_day_return,
    max(r.next_day_return) as best_next_day_return
from signals as s
inner join realized as r
    on s.ticker = r.ticker and s.date = r.date
where r.next_day_return is not null
group by s.date, s.exchange, s.signal_quintile
