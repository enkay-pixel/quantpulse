-- Disclosures of stakes over 5% from structured Schedule 13D/13G filings (research branch, ADR 0007).
select
    accession,
    ticker,
    form,
    form like 'SCHEDULE 13D%' as is_13d,
    filed,
    event_date,
    filer,
    shares,
    percent
from {{ source('market', 'holder_filings') }}
