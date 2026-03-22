{% macro clean_name(column) %}
    {#- Apply initcap(trim(...)) then fix known Mc/Mac prefix edge cases.
        Postgres initcap handles apostrophes and hyphens (O'Leary, Smith-Jones)
        but lowercases the letter after Mc/Mac. Add new entries as discovered. -#}
    {%- set replacements = [
        ("Mcdonald", "McDonald"),
        ("Mcgregor", "McGregor"),
        ("Mckenzie", "McKenzie"),
        ("Mckenna", "McKenna"),
        ("Mccarthy", "McCarthy"),
        ("Mcmahon", "McMahon"),
        ("Mcnamara", "McNamara"),
        ("Mcneil", "McNeil"),
        ("Mclean", "McLean"),
        ("Mclaughlin", "McLaughlin"),
        ("Mcintyre", "McIntyre"),
        ("Mcmillan", "McMillan"),
        ("Mcbride", "McBride"),
        ("Mccann", "McCann"),
        ("Mccormack", "McCormack"),
        ("Mcdermott", "McDermott"),
        ("Mcdonagh", "McDonagh"),
        ("Mcdonnell", "McDonnell"),
        ("Mcfadden", "McFadden"),
        ("Mcgee", "McGee"),
        ("Mcgill", "McGill"),
        ("Mcgovern", "McGovern"),
        ("Mcgrath", "McGrath"),
        ("Mcguire", "McGuire"),
        ("Mcintosh", "McIntosh"),
        ("Mckay", "McKay"),
        ("Mckinley", "McKinley"),
        ("Mcloughlin", "McLoughlin"),
        ("Mcnally", "McNally"),
        ("Mcnulty", "McNulty"),
        ("Mcsweeney", "McSweeney"),
        ("Macgregor", "MacGregor"),
        ("Macdonald", "MacDonald"),
        ("Mackenzie", "MacKenzie"),
        ("Mackay", "MacKay"),
        ("Macleod", "MacLeod"),
        ("Maclean", "MacLean"),
    ] -%}
    {%- set trimmed = "case when trim(" ~ column ~ ") ~ '^[A-Za-z]( [A-Za-z])+$' then replace(trim(" ~ column ~ "), ' ', '.') || '.' else trim(" ~ column ~ ") end" -%}
    {%- set result = "initcap((" ~ trimmed ~ "))" -%}
    {%- for old, new in replacements -%}
        {%- set result = "replace(" ~ result ~ ", '" ~ old ~ "', '" ~ new ~ "')" -%}
    {%- endfor -%}
    {{ result }}
{% endmacro %}
