{{
    config(
        materialized='view',
    )
}}

with ssa as (
    select name, gender_code, birth_count, year, source, iso_alpha2, country_subdivision
    from {{ ref('stg_ssa_forenames') }}
),

ons as (
    select name, gender_code, birth_count, year, source, iso_alpha2, country_subdivision
    from {{ ref('stg_ons_forenames') }}
),

nrs as (
    select name, gender_code, birth_count, year, source, iso_alpha2, country_subdivision
    from {{ ref('stg_nrs_forenames') }}
),

nisra as (
    select name, gender_code, birth_count, year, source, iso_alpha2, country_subdivision
    from {{ ref('stg_nisra_forenames') }}
),

wales as (
    select name, gender_code, birth_count, year, source, iso_alpha2, country_subdivision
    from {{ ref('stg_wales_forenames') }}
),

cso_boys as (
    select name, gender_code, birth_count, year, source, iso_alpha2, country_subdivision
    from {{ ref('stg_cso_forenames_boys') }}
),

cso_girls as (
    select name, gender_code, birth_count, year, source, iso_alpha2, country_subdivision
    from {{ ref('stg_cso_forenames_girls') }}
),

unioned as (
    select * from ssa
    union all
    select * from ons
    union all
    select * from nrs
    union all
    select * from nisra
    union all
    select * from wales
    union all
    select * from cso_boys
    union all
    select * from cso_girls
)

select * from unioned
