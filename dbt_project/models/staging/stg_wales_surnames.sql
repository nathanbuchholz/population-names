with source as (
    select * from {{ source('raw', 'wales_surnames') }}
),

-- Strip wiki artifacts: parenthetical suffixes like "(name)", "(disambiguation)"
stripped as (
    select
        regexp_replace(trim(name), '\s*\([^)]*\)\s*$', '') as raw_name,
        nullif(cast(nullif(rank, '') as integer), 0) as rank,
        nullif(cast(nullif(count, '') as integer), 0) as count,
        trim(origin) as origin
    from source
    where name is not null
),

-- Apply standard name cleaning (initcap, Mc/Mac fixes)
cleaned as (
    select
        {{ clean_name('raw_name') }} as name,
        rank,
        count,
        origin
    from stripped
    where raw_name ~ '^[[:alpha:]'' -]+$'  -- reject names with digits or special chars
),

-- Deduplicate: same name may appear from both Wikipedia and Wiktionary.
-- Keep the best data: prefer the row with a count, merge origins.
deduped as (
    select
        name,
        max(rank) as rank,
        max(count) as count,
        string_agg(distinct origin, ',' order by origin) as origin
    from cleaned
    group by name
),

-- Conform to surname union schema
conformed as (
    select
        name,
        coalesce(count, 1) as count,  -- presence marker when no count available
        make_date(2002, 1, 1) as year,
        'GB' as iso_alpha2,
        'GB-WLS' as country_subdivision
    from deduped
)

select * from conformed
