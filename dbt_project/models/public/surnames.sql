{{
    config(
        materialized='view',
        alias='vw_surnames',
    )
}}

with surname_data as (
    select
        s.name,
        s.count,
        s.year,
        s.iso_alpha2,
        s.country_subdivision
    from {{ ref('stg_surnames_unioned') }} s
    where s.count > 0
      {{ apply_year_filter('s.year') }}
),

joined as (
    select
        s.name,
        c.country_id,
        s.year,
        s.count
    from surname_data s
    inner join {{ source('public', 'countries') }} c
        on (s.country_subdivision is null and c.subdivision_code is null and c.iso_alpha2 = s.iso_alpha2)
        or (s.country_subdivision = c.subdivision_code)
)

select
    name,
    country_id,
    year,
    count
from joined
