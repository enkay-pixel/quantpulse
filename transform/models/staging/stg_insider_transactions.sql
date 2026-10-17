-- Insider trades from Form 4 filings on SEC EDGAR (research branch, ADR 0007), one row per trade.
select
    accession,
    seq,
    ticker,
    form,
    filed,
    owner,
    role,
    planned,
    transaction_date,
    code,
    shares,
    price,
    shares * price as value_usd,
    acquired,
    shares_after
from {{ source('market', 'insider_transactions') }}
