-- Open-market trades by company insiders, from Form 4 (ADR 0007): the one definition the ownership
-- summary and the per-stock list both read. Code P is a purchase and S a sale; grants, option
-- exercises and shares withheld for tax are pay mechanics rather than decisions, so they are left
-- out, as is a trade reported without a price.
select
    accession,
    seq,
    ticker,
    filed,
    owner,
    role,
    planned,
    transaction_date,
    case code when 'P' then 'bought' else 'sold' end as trade,
    shares as shares_traded,
    price as trade_price,
    value_usd
from {{ ref('stg_insider_transactions') }}
where code in ('P', 'S') and price > 0
