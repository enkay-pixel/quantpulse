-- Per (ticker, snapshot): the option market's headline read on the name — ATM implied
-- volatility (nearest expiry, strike closest to spot) and the put/call ratio, a common
-- positioning/sentiment gauge (>1 = more put than call open interest).
-- ATM IV follows the ~30-day convention (as VIX does) rather than the nearest expiry:
-- same-day contracts are illiquid and the feed reports junk near-zero IV for them,
-- so require a week of life and a sane IV before calling anything "at the money".
with atm as (
    select distinct on (ticker, snapshot_date)
        ticker,
        snapshot_date,
        implied_volatility as atm_iv,
        days_to_expiry as atm_days
    from {{ ref('stg_option_quotes') }}
    where
        option_type = 'call'
        and days_to_expiry >= 7
        and implied_volatility > 0.01
    order by ticker, snapshot_date, abs(days_to_expiry - 30), abs(moneyness)
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
