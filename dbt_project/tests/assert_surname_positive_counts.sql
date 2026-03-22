-- Ensure no surname records have negative counts
select *
from {{ ref('stg_surnames_unioned') }}
where count < 0
