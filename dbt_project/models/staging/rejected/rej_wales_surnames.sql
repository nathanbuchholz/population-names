with source as (
    select * from {{ source('raw', 'wales_surnames') }}
),

-- Rows rejected at first stage: null name
null_names as (
    select *,
      'wales_surnames' as source_table,
      name as raw_name,
      'name_null' as rejection_reason
    from source
    where name is null
),

-- Rows rejected at second stage: name fails regex after stripping wiki artifacts
bad_names as (
    select *,
      'wales_surnames' as source_table,
      name as raw_name,
      'name_invalid_chars' as rejection_reason
    from source
    where name is not null
      and not (regexp_replace(trim(name), '\s*\([^)]*\)\s*$', '') ~ '^[[:alpha:]'' -]+$')
)

select * from null_names
union all
select * from bad_names
