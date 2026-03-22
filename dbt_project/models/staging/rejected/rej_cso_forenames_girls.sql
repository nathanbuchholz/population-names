with source as (
    select * from {{ source('raw', 'cso_forenames_girls') }}
)

select *,
  'cso_forenames_girls' as source_table,
  name as raw_name,
  case
    when name is null then 'name_null'
    when sex is null then 'sex_null'
    when year is null then 'year_null'
    when trim(name) = '' then 'name_empty'
    when trim(year) = '' then 'year_empty'
    when not (trim(name) ~ '^[[:alpha:]''. -]+$') then 'name_invalid_chars'
    when upper(trim(sex)) not in ('M', 'F') then 'sex_invalid'
    when not (year ~ '^\d{4}$') then 'year_invalid_format'
    when not (count is null or trim(count) = '' or trim(count) ~ '^\d+$') then 'count_invalid_format'
    else 'unknown'
  end as rejection_reason
from source
where not (
  name is not null
  and sex is not null
  and year is not null
  and trim(name) != ''
  and trim(year) != ''
  and trim(name) ~ '^[[:alpha:]''. -]+$'
  and upper(trim(sex)) in ('M', 'F')
  and year ~ '^\d{4}$'
  and (count is null or trim(count) = '' or trim(count) ~ '^\d+$')
)
