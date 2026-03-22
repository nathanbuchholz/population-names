-- Ensure all forename years are within a reasonable range
select *
from {{ ref('stg_forenames_unioned') }}
where year < make_date(1800, 1, 1) or year > make_date(extract(year from current_date)::int + 1, 1, 1)
