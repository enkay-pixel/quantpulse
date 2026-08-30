-- Per (ticker, snapshot): what the option market charged for volatility against what the
-- underlying actually delivered. The spread is the variance risk premium — positive means
-- options were priced above realised movement, which is the usual state and is what selling
-- volatility earns.
--
-- Backward-looking on purpose. Comparing implied volatility to *subsequent* realised
-- volatility is the sharper question, but it needs the realisation window to close, and only
-- the earliest snapshots qualify while this table has a month of history. Trailing realised
-- vol is available for every ticker-day, which turns 27 snapshots into 1,268 comparisons.
--
-- Read it as description, not signal. One month of snapshots says what the premium has been,
-- not what it predicts; see docs/measurement.md before drawing the second conclusion from it.
select
    s.ticker,
    u.exchange,
    s.snapshot_date,
    s.atm_iv,
    s.atm_days,
    -- fct_daily_returns.volatility_21d is a *daily* standard deviation, not annualised.
    -- atm_iv arrives annualised from the vendor, so the two must be put in the same units
    -- before they are subtracted. Skipping this produced a premium of 0.3047 at t 80 with
    -- 100% of ticker-days positive — a unit error wearing the clothes of a strong finding.
    r.volatility_21d * sqrt(252) as realized_vol_21d,
    s.atm_iv - r.volatility_21d * sqrt(252) as variance_premium,
    case
        when r.volatility_21d > 0 then s.atm_iv / (r.volatility_21d * sqrt(252))
    end as iv_to_realized_ratio
from {{ ref('fct_option_summary') }} as s
-- Inner join on the same date: a snapshot with no bar that day has nothing to compare
-- against, and carrying it forward would invent a comparison the data does not support.
inner join {{ ref('fct_daily_returns') }} as r
    on r.ticker = s.ticker and r.date = s.snapshot_date
inner join {{ ref('dim_universe') }} as u
    on u.ticker = s.ticker
where r.volatility_21d is not null
