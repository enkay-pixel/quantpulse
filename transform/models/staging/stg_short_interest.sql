-- Short interest per (ticker, settlement), with the US market date it first became known.
-- Readers key history by `known_from`, not by settlement: a figure reaches the vendor a week or
-- two after it settles, so keyed by settlement a past day would show a number not yet public.
select
    ticker,
    settlement_date,
    shares_short,
    shares_short_prior,
    prior_settlement_date,
    short_pct_float,
    days_to_cover,
    float_shares,
    shares_outstanding,
    (ingested_at at time zone 'America/New_York')::date as known_from
from {{ source('market', 'short_interest') }}
