{% set rejected_models = [
  'rej_ssa_forenames',
  'rej_ons_forenames',
  'rej_nrs_forenames',
  'rej_nisra_forenames',
  'rej_wales_forenames',
  'rej_cso_forenames_boys',
  'rej_cso_forenames_girls',
  'rej_census_surnames',
  'rej_england_surnames',
  'rej_nrs_surnames',
  'rej_cso_surnames',
  'rej_ni_surnames',
  'rej_wales_surnames',
] %}

{% for model_name in rejected_models %}
select
    source_table,
    rejection_reason,
    raw_name,
    file_log_id
from {{ ref(model_name) }}
{% if not loop.last %}union all{% endif %}
{% endfor %}
