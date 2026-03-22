with source as (
    select * from {{ source('raw', 'ni_surnames') }}
),

cleaned as (
    select
        {{ clean_name('name') }} as name
    from source
    where name is not null
      and trim(name) != ''
      and name ~ '^[[:alpha:]'' -]+$'
),

deduped as (
    select distinct name
    from cleaned
),

conformed as (
    select
        name,
        1 as count,  -- presence marker only; source has no frequency data
        make_date(extract(year from current_date)::int, 1, 1) as year,
        'GB' as iso_alpha2,
        'GB-NIR' as country_subdivision
    from deduped
)

select * from conformed
