with source as (
    select * from {{ source('raw', 'cso_forenames_girls') }}
),

cleaned as (
    select
        {{ clean_name('name') }} as name,
        upper(trim(sex)) as gender_code,
        coalesce(nullif(cast(nullif(trim(count), '') as integer), 0), 1) as birth_count,
        make_date(cast(year as integer), 1, 1) as year,
        'cso' as source,
        'IE' as iso_alpha2,
        null as country_subdivision
    from source
    where name is not null
      and sex is not null
      and year is not null
      and trim(name) != ''
      and trim(year) != ''
      and trim(name) ~ '^[[:alpha:]''. -]+$'
      and upper(trim(sex)) in ('M', 'F')
      and year ~ '^\d{4}$'
      and (count is null or trim(count) = '' or trim(count) ~ '^\d+$')
),

deduped as (
    select
        name,
        gender_code,
        max(birth_count) as birth_count,
        year,
        source,
        iso_alpha2,
        country_subdivision
    from cleaned
    group by name, gender_code, year, source, iso_alpha2, country_subdivision
)

select * from deduped
