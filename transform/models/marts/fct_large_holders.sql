-- Holders over 5% of each stock (ADR 0007): each filer's latest structured 13D or 13G in the two years
-- before the newest filing stored, kept when it still reports 5% or more. An amendment under 5% is an
-- exit, so the filer drops out. The one definition the ownership summary and the per-stock list read.
with anchor as (
    select max(filed) as as_of from {{ ref('stg_holder_filings') }}
),

latest as (
    select distinct on (h.ticker, h.filer)
        h.ticker,
        h.filer,
        h.form,
        h.is_13d,
        h.filed,
        h.shares as shares_held,
        h.percent,
        h.share_class
    from {{ ref('stg_holder_filings') }} as h
    cross join anchor as a
    where h.filed > a.as_of - 730
    order by h.ticker, h.filer, h.filed desc, h.accession desc
)

select * from latest
where percent >= 5
