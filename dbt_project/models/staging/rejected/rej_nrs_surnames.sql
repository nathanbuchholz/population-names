with source as (
    select * from {{ source('raw', 'nrs_surnames') }}
)

select *,
  'nrs_surnames' as source_table,
  name as raw_name,
  case
    when name is null then 'name_null'
    when count is null then 'count_null'
    when year is null then 'year_null'
    else 'unknown'
  end as rejection_reason
from source
where not (
  name is not null
  and count is not null
  and year is not null
)
