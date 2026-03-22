with source as (
    select * from {{ source('raw', 'ssa_forenames') }}
)

select *,
  'ssa_forenames' as source_table,
  name as raw_name,
  case
    when name is null then 'name_null'
    when sex is null then 'sex_null'
    when count is null then 'count_null'
    when year is null then 'year_null'
    when not (trim(name) ~ '^[[:alpha:]''. -]+$') then 'name_invalid_chars'
    when upper(trim(sex)) not in ('M', 'F') then 'sex_invalid'
    else 'unknown'
  end as rejection_reason
from source
where not (
  name is not null
  and sex is not null
  and count is not null
  and year is not null
  and trim(name) ~ '^[[:alpha:]''. -]+$'
  and upper(trim(sex)) in ('M', 'F')
)
