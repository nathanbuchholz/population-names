with source as (
    select * from {{ source('raw', 'nrs_forenames') }}
),

cleaned as (
    select
        {{ clean_name('name') }} as name,
        upper(trim(sex)) as gender_code,
        {{ clean_count('count') }} as birth_count,
        make_date(cast(year as integer), 1, 1) as year,
        'nrs' as source,
        'GB' as iso_alpha2,
        'GB-SCT' as country_subdivision
    from source
    where name is not null
      and sex is not null
      and count is not null
      and year is not null
      and trim(name) ~ '^[[:alpha:]''. -]+$'
      and upper(trim(sex)) in ('M', 'F')
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
