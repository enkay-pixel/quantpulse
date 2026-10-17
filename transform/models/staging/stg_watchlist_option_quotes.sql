-- The watchlist's option chains, in the same shape as stg_option_quotes, for its current names.
select
    q.snapshot_date,
    q.ticker,
    q.expiry,
    q.strike,
    q.option_type,
    q.underlying_close,
    q.bid,
    q.ask,
    q.last_price,
    q.volume,
    q.open_interest,
    q.implied_volatility,
    q.in_the_money,
    q.theo_value,
    q.delta,
    q.gamma,
    q.theta,
    q.vega,
    q.strike / nullif(q.underlying_close, 0) - 1 as moneyness,
    q.expiry - q.snapshot_date as days_to_expiry
from {{ source('market', 'watchlist_option_quotes') }} as q
inner join {{ source('market', 'watchlist') }} as w on q.ticker = w.ticker
