-- The implied-volatility surface: mean IV by (ticker, snapshot, expiry, moneyness bucket).
-- Reading across strikes at one expiry gives the volatility smile/skew; across expiries
-- gives the term structure.
select
    ticker,
    snapshot_date,
    expiry,
    option_type,
    days_to_expiry,
    width_bucket(moneyness, -0.2, 0.2, 8) as moneyness_bucket,
    round(avg(moneyness)::numeric, 4) as avg_moneyness,
    avg(implied_volatility) as avg_iv,
    avg(delta) as avg_delta,
    sum(open_interest) as open_interest,
    count(*) as n_contracts
from {{ ref('stg_option_quotes') }}
group by ticker, snapshot_date, expiry, option_type, days_to_expiry, moneyness_bucket
