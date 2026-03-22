with source as (
    select * from {{ source('raw', 'england_surnames') }}
)

select *,
  'england_surnames' as source_table,
  name as raw_name,
  case
    when name is null then 'name_null'
    when count is null then 'count_null'
    when year is null then 'year_null'
    when not (trim(name) ~ '^[[:alpha:]''. -]+$') then 'name_invalid_chars'
    else 'unknown'
  end as rejection_reason
from source
where not (
  name is not null
  and count is not null
  and year is not null
  and trim(name) ~ '^[[:alpha:]''. -]+$'
)
