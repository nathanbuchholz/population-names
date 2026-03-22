with source as (
    select * from {{ source('raw', 'england_surnames') }}
),

-- Source has mixed casing: ~214 ALL-CAPS names, ~776 initcap.
-- clean_name applies initcap() to normalize, then Mc/Mac fixes.
cleaned as (
    select
        {{ clean_name('name') }} as name,
        {{ clean_count('count') }} as count,
        make_date(cast(year as integer), 1, 1) as year,
        'GB' as iso_alpha2,
        'GB-ENG' as country_subdivision
    from source
    where name is not null
      and count is not null
      and year is not null
      and trim(name) ~ '^[[:alpha:]''. -]+$'
),

-- Guard against initcap creating duplicates from casing variants
-- (e.g. "SMITH" and "Smith" both become "Smith"). Sum counts if so.
deduped as (
    select
        name,
        sum(count) as count,
        year,
        iso_alpha2,
        country_subdivision
    from cleaned
    group by name, year, iso_alpha2, country_subdivision
)

select * from deduped
