-- Ensure all gender codes in the unioned staging model are valid
select gender_code
from {{ ref('stg_forenames_unioned') }}
where gender_code not in ('M', 'F')
