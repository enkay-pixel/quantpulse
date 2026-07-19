-- Does the model's ranking work? Signals are bucketed into quintiles per date
-- (1 = strongest buy signal) and paired with the NEXT day's realized return.
-- If the model has skill, quintile 1 should out-earn quintile 5 on average.
with signals as (
    select
        ticker,
        date,
        score,
        ntile(5) over (partition by date order by score desc) as signal_quintile
    from {{ ref('stg_predictions') }}
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
group by s.date, s.signal_quintile
