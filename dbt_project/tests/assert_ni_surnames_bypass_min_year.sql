-- NI surnames must be present in the public surnames model.
-- Source is Wikipedia (no frequency or date data); year is set to current year.
select 1
where not exists (
    select 1
    from {{ ref('surnames') }} s
    join {{ source('public', 'countries') }} c on c.country_id = s.country_id
    where c.subdivision_code = 'GB-NIR'
)
