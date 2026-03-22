-- Ensure no forename records have negative birth counts
select *
from {{ ref('stg_forenames_unioned') }}
where birth_count < 0
