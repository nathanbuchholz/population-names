{% macro apply_year_filter(column='year') %}
  {% if config.get('year_filter', true) %}
    and {{ column }} >= make_date({{ var('min_year') }}, 1, 1)
  {% endif %}
{% endmacro %}
