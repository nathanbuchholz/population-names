with source as (
    select * from {{ source('raw', 'cso_surnames') }}
),

cleaned as (
    select
        {{ clean_name('name') }} as name,
        -- PxStat format: VALUE = rank, count not available.
        -- Use rank as count (presence indicator) for downstream compatibility.
        coalesce(
            nullif(cast(nullif(trim(rank), '') as integer), 0),
            1
        ) as count,
        make_date(cast(year as integer), 1, 1) as year,
        'IE' as iso_alpha2,
        null as country_subdivision
    from source
    where name is not null
      and year is not null
      and trim(name) != ''
      and trim(year) != ''
      and trim(name) ~ '^[[:alpha:]''. -]+$'
      and year ~ '^\d{4}$'
),

-- Deduplicate across files that may contain overlapping rows
deduped as (
    select
        name,
        max(count) as count,
        year,
        iso_alpha2,
        country_subdivision
    from cleaned
    group by name, year, iso_alpha2, country_subdivision
)

select * from deduped
