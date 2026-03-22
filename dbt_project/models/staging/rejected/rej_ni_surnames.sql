with source as (
    select * from {{ source('raw', 'ni_surnames') }}
)

select *,
  'ni_surnames' as source_table,
  name as raw_name,
  case
    when name is null then 'name_null'
    when trim(name) = '' then 'name_empty'
    when not (trim(name) ~ '^[[:alpha:]'' -]+$') then 'name_invalid_chars'
    else 'unknown'
  end as rejection_reason
from source
where not (
  name is not null
  and trim(name) != ''
  and trim(name) ~ '^[[:alpha:]'' -]+$'
)
