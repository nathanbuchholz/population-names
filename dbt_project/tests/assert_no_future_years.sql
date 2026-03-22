-- Ensure no records have a year in the future
select year
from {{ ref('stg_forenames_unioned') }}
where year > make_date(extract(year from current_date)::int, 1, 1)
