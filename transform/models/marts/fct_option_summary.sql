-- Per (ticker, snapshot): the option market's headline read on the name — ATM implied
-- volatility (nearest expiry, strike closest to spot) and the put/call ratio, a common
-- positioning/sentiment gauge (>1 = more put than call open interest).
with atm as (
    select distinct on (ticker, snapshot_date)
        ticker,
        snapshot_date,
        implied_volatility as atm_iv,
        days_to_expiry as atm_days
    from {{ ref('stg_option_quotes') }}
    where option_type = 'call'
    order by ticker, snapshot_date, days_to_expiry, abs(moneyness)
),

oi as (
    select
        ticker,
        snapshot_date,
        sum(open_interest) filter (where option_type = 'call') as call_oi,
        sum(open_interest) filter (where option_type = 'put') as put_oi,
        sum(volume) filter (where option_type = 'call') as call_volume,
        sum(volume) filter (where option_type = 'put') as put_volume,
        count(*) as n_contracts
    from {{ ref('stg_option_quotes') }}
    group by ticker, snapshot_date
)

select
    oi.ticker,
    oi.snapshot_date,
    atm.atm_iv,
    atm.atm_days,
    oi.call_oi,
    oi.put_oi,
    oi.call_volume,
    oi.put_volume,
    oi.n_contracts,
    oi.put_oi::float / nullif(oi.call_oi, 0) as put_call_ratio
from oi
inner join atm on oi.ticker = atm.ticker and oi.snapshot_date = atm.snapshot_date
