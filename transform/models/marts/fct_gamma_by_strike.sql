-- How much stock a hedger would trade per 1% move, by strike: the one definition of option dollar
-- gamma that the positioning marts and the strike profile both read (ADR 0007).
--
-- Dollar gamma per 1% move = gamma x open interest x 100 shares x spot^2 x 0.01: the change in a
-- hedger's dollar delta when the price moves 1%. It is the exposure *if a dealer were on the other
-- side of every contract*. Calls and puts stay in separate columns and are never netted: who holds
-- which side is not public, and the usual assumption (dealers long calls, short puts) was
-- backwards for GameStop.
--
-- Only live contracts with a sane implied volatility count. Gamma grows without bound as time or
-- IV approaches zero, so a same-day contract or a junk near-zero IV would swamp the rest.
with live as (
    select
        snapshot_date,
        ticker,
        strike,
        option_type,
        underlying_close as spot,
        days_to_expiry,
        open_interest,
        gamma * open_interest * 100 * underlying_close * underlying_close * 0.01 as gamma_usd_1pct
    from (
        -- The model's universe and the research watchlist, captured in the same band.
        select
            snapshot_date, ticker, strike, option_type, underlying_close, days_to_expiry,
            open_interest, gamma, implied_volatility
        from {{ ref('stg_option_quotes') }}
        union all
        select
            snapshot_date, ticker, strike, option_type, underlying_close, days_to_expiry,
            open_interest, gamma, implied_volatility
        from {{ ref('stg_watchlist_option_quotes') }}
    ) as quotes
    where
        days_to_expiry >= 1
        and implied_volatility > 0.01
        and open_interest > 0
)

select
    snapshot_date,
    ticker,
    strike,
    max(spot) as spot,
    coalesce(sum(open_interest) filter (where option_type = 'call'), 0) as call_oi,
    coalesce(sum(open_interest) filter (where option_type = 'put'), 0) as put_oi,
    coalesce(sum(gamma_usd_1pct) filter (where option_type = 'call'), 0) as call_gamma_usd_1pct,
    coalesce(sum(gamma_usd_1pct) filter (where option_type = 'put'), 0) as put_gamma_usd_1pct,
    coalesce(
        sum(gamma_usd_1pct) filter (where option_type = 'call' and days_to_expiry <= 30), 0
    ) as call_gamma_usd_1pct_30d
from live
group by snapshot_date, ticker, strike
