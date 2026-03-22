-- Fails if any raw source table has 0 rows after ingestion.
{% set raw_tables = [
  'ssa_forenames',
  'ons_forenames',
  'nrs_forenames',
  'nisra_forenames',
  'wales_forenames',
  'cso_forenames_boys',
  'cso_forenames_girls',
  'census_surnames',
  'england_surnames',
  'nrs_surnames',
  'cso_surnames',
  'ni_surnames',
  'wales_surnames',
] %}

{% for table_name in raw_tables %}
select '{{ table_name }}' as table_name
from {{ source('raw', table_name) }}
having count(*) = 0
{% if not loop.last %}union all{% endif %}
{% endfor %}
