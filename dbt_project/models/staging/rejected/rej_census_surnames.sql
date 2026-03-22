with source as (
    select * from {{ source('raw', 'census_surnames') }}
)

select *,
  'census_surnames' as source_table,
  name as raw_name,
  case
    when name is null then 'name_null'
    when count is null then 'count_null'
    when year is null then 'year_null'
    when not (trim(name) ~ '^[[:alpha:]''. -]+$') then 'name_invalid_chars'
    when cast(count as integer) <= 0 then 'count_not_positive'
    else 'unknown'
  end as rejection_reason
from source
where not (
  name is not null
  and count is not null
  and year is not null
  and trim(name) ~ '^[[:alpha:]''. -]+$'
  and cast(count as integer) > 0
)
