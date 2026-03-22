{{
    config(
        materialized='view',
    )
}}

with census as (
    select name, count, year, iso_alpha2, country_subdivision
    from {{ ref('stg_census_surnames') }}
),

england as (
    select name, count, year, iso_alpha2, country_subdivision
    from {{ ref('stg_england_surnames') }}
),

nrs as (
    select name, count, year, iso_alpha2, country_subdivision
    from {{ ref('stg_nrs_surnames') }}
),

cso as (
    select name, count, year, iso_alpha2, country_subdivision
    from {{ ref('stg_cso_surnames') }}
),

ni as (
    select name, count, year, iso_alpha2, country_subdivision
    from {{ ref('stg_ni_surnames') }}
),

wales as (
    select name, count, year, iso_alpha2, country_subdivision
    from {{ ref('stg_wales_surnames') }}
),

unioned as (
    select * from census
    union all
    select * from england
    union all
    select * from nrs
    union all
    select * from cso
    union all
    select * from ni
    union all
    select * from wales
)

select * from unioned
