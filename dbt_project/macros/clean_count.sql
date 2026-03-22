{% macro clean_count(column) %}
    nullif(cast({{ column }} as integer), 0)
{% endmacro %}
