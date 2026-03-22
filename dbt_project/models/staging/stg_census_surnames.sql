with source as (
    select * from {{ source('raw', 'census_surnames') }}
),

-- Reject names with digits or special characters,
-- and ensure count is a positive integer.
cleaned as (
    select
        {{ clean_name('name') }} as name,
        {{ clean_count('count') }} as count,
        make_date(cast(year as integer), 1, 1) as year,
        'US' as iso_alpha2,
        null as country_subdivision
    from source
    where name is not null
      and count is not null
      and year is not null
      and trim(name) ~ '^[[:alpha:]''. -]+$'
      and cast(count as integer) > 0
),

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
