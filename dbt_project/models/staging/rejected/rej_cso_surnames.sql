with source as (
    select * from {{ source('raw', 'cso_surnames') }}
)

select *,
  'cso_surnames' as source_table,
  name as raw_name,
  case
    when name is null then 'name_null'
    when year is null then 'year_null'
    when trim(name) = '' then 'name_empty'
    when trim(year) = '' then 'year_empty'
    when not (trim(name) ~ '^[[:alpha:]''. -]+$') then 'name_invalid_chars'
    when not (year ~ '^\d{4}$') then 'year_invalid_format'
    else 'unknown'
  end as rejection_reason
from source
where not (
  name is not null
  and year is not null
  and trim(name) != ''
  and trim(year) != ''
  and trim(name) ~ '^[[:alpha:]''. -]+$'
  and year ~ '^\d{4}$'
)
