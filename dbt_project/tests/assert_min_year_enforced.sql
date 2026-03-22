-- Public forenames should have no rows before min_year (applied by apply_year_filter macro)
select *
from {{ ref('forenames') }}
where year < make_date({{ var('min_year') }}, 1, 1)
