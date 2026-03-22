{{
    config(
        materialized='view',
        alias='vw_forenames',
    )
}}

with forename_data as (
    select
        f.name,
        f.gender_code,
        f.birth_count,
        f.year,
        f.iso_alpha2,
        f.country_subdivision
    from {{ ref('stg_forenames_unioned') }} f
    where f.birth_count > 0
      {{ apply_year_filter('f.year') }}
),

joined as (
    select
        f.name,
        g.gender_id,
        c.country_id,
        f.year,
        f.birth_count as count
    from forename_data f
    inner join {{ source('public', 'countries') }} c
        on (f.country_subdivision is null and c.subdivision_code is null and c.iso_alpha2 = f.iso_alpha2)
        or (f.country_subdivision = c.subdivision_code)
    inner join {{ source('public', 'genders') }} g
        on f.gender_code = g.code
)

select
    name,
    gender_id,
    country_id,
    year,
    count
from joined
