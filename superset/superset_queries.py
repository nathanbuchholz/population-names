"""
SQL queries, dataset configs, and saved queries for Superset.

Centralises all data definitions so seed_superset.py stays focused on API calls.
Queries for name_diversity, cross_country_names, and biggest_movers reference
mv_forename_rankings (kept MV) for performance.
"""

QUERIES: dict[str, str] = {
    # -----------------------------------------------------------------------
    # Forename Trends
    # -----------------------------------------------------------------------
    "Forename Trends Analytics": """\
WITH agg AS (
    SELECT
        name, gender_id, country_id,
        min(year) AS first_year,
        max(year) AS last_year
    FROM public.forenames
    GROUP BY name, gender_id, country_id
),
peak AS (
    SELECT DISTINCT ON (name, gender_id, country_id)
        name, gender_id, country_id, year AS peak_year, count AS peak_count
    FROM public.forenames
    ORDER BY name, gender_id, country_id, count DESC, year DESC
),
recent AS (
    SELECT
        name, gender_id, country_id,
        sum(CASE WHEN year > (SELECT max(year) - interval '5 years' FROM public.forenames) THEN count ELSE 0 END) AS recent_sum,
        sum(CASE WHEN year <= (SELECT max(year) - interval '5 years' FROM public.forenames)
                  AND year > (SELECT max(year) - interval '10 years' FROM public.forenames) THEN count ELSE 0 END) AS prev_sum
    FROM public.forenames
    GROUP BY name, gender_id, country_id
)
SELECT
    a.name,
    g.label AS gender,
    c.name AS country, c.iso_alpha2 AS country_code,
    p.peak_year,
    p.peak_count,
    round((p.peak_count::numeric / c.population) * 1000000, 2) AS peak_count_per_m,
    a.first_year,
    a.last_year,
    CASE
        WHEN r.recent_sum > r.prev_sum * 1.1 THEN 'rising'
        WHEN r.recent_sum < r.prev_sum * 0.9 THEN 'falling'
        ELSE 'stable'
    END AS trend_direction
FROM agg a
JOIN peak p USING (name, gender_id, country_id)
JOIN recent r USING (name, gender_id, country_id)
JOIN countries c ON a.country_id = c.country_id
JOIN genders g ON a.gender_id = g.gender_id""",
    # -----------------------------------------------------------------------
    # Surname Trends
    # -----------------------------------------------------------------------
    "Surname Trends Analytics": """\
WITH agg AS (
    SELECT
        name, country_id,
        min(year) AS first_year,
        max(year) AS last_year
    FROM public.surnames
    GROUP BY name, country_id
),
peak AS (
    SELECT DISTINCT ON (name, country_id)
        name, country_id, year AS peak_year, count AS peak_count
    FROM public.surnames
    ORDER BY name, country_id, count DESC, year DESC
)
SELECT
    a.name,
    c.name AS country, c.iso_alpha2 AS country_code,
    p.peak_year,
    p.peak_count,
    round((p.peak_count::numeric / c.population) * 1000000, 2) AS peak_count_per_m,
    a.first_year,
    a.last_year,
    'stable'::text AS trend_direction
FROM agg a
JOIN peak p USING (name, country_id)
JOIN countries c ON a.country_id = c.country_id""",
    # -----------------------------------------------------------------------
    # Name Diversity  (references mv_forename_rankings)
    # -----------------------------------------------------------------------
    "Name Diversity": """\
WITH base AS (
    SELECT country_id, gender_id, year,
           count(DISTINCT name) AS unique_names,
           sum(count) AS total_births
    FROM public.forenames
    GROUP BY country_id, gender_id, year
),
top10 AS (
    SELECT country_id, gender_id, year,
           sum(count) AS top10_births
    FROM mv_forename_rankings
    WHERE rank <= 10
    GROUP BY country_id, gender_id, year
)
SELECT
    c.name AS country, c.iso_alpha2 AS country_code, g.label AS gender,
    b.year,
    b.unique_names::integer,
    round((b.unique_names::numeric / c.population) * 1000000, 2) AS unique_names_per_m,
    b.total_births,
    round((b.total_births::numeric / c.population) * 1000000, 2) AS total_births_per_m,
    CASE WHEN b.total_births > 0
        THEN round((t.top10_births::numeric / b.total_births) * 100, 2)
        ELSE NULL
    END AS top10_concentration_pct
FROM base b
LEFT JOIN top10 t
    ON b.country_id = t.country_id
    AND b.gender_id = t.gender_id
    AND b.year = t.year
JOIN countries c ON b.country_id = c.country_id
JOIN genders g ON b.gender_id = g.gender_id""",
    # -----------------------------------------------------------------------
    # Gender-Neutral Names
    # -----------------------------------------------------------------------
    "Gender-Neutral Names": """\
WITH latest AS (
    SELECT country_id, max(year) AS max_year
    FROM public.forenames
    GROUP BY country_id
),
by_gender AS (
    SELECT f.name, f.country_id,
           sum(CASE WHEN f.gender_id = (SELECT gender_id FROM genders WHERE code = 'M') THEN f.count ELSE 0 END) AS male_count,
           sum(CASE WHEN f.gender_id = (SELECT gender_id FROM genders WHERE code = 'F') THEN f.count ELSE 0 END) AS female_count
    FROM public.forenames f
    JOIN latest l ON f.country_id = l.country_id AND f.year = l.max_year
    GROUP BY f.name, f.country_id
),
year_totals AS (
    SELECT f.country_id, sum(f.count) AS total
    FROM public.forenames f
    JOIN latest l ON f.country_id = l.country_id AND f.year = l.max_year
    GROUP BY f.country_id
)
SELECT
    bg.name,
    c.name AS country, c.iso_alpha2 AS country_code,
    bg.male_count::integer,
    bg.female_count::integer,
    (bg.male_count + bg.female_count)::integer AS total_count,
    round(((bg.male_count + bg.female_count)::numeric / yt.total) * 100, 4) AS pct_of_births,
    round(
        (least(bg.male_count, bg.female_count)::numeric
         / greatest(bg.male_count, bg.female_count)) * 100, 2
    ) AS balance_pct
FROM by_gender bg
JOIN countries c ON bg.country_id = c.country_id
JOIN year_totals yt ON bg.country_id = yt.country_id
WHERE bg.male_count >= 10 AND bg.female_count >= 10
  AND round((least(bg.male_count, bg.female_count)::numeric
             / greatest(bg.male_count, bg.female_count)) * 100, 2) >= 20
ORDER BY pct_of_births DESC
LIMIT 100""",
    # -----------------------------------------------------------------------
    # Cross-Country Names  (references mv_forename_rankings)
    # -----------------------------------------------------------------------
    "Cross-Country Names": """\
SELECT
    r.name,
    g.label AS gender,
    round(avg(r.pct_of_year_total), 4) AS avg_pct_of_births
FROM mv_forename_rankings r
JOIN genders g ON r.gender_id = g.gender_id
GROUP BY r.name, r.gender_id, g.label
HAVING count(DISTINCT r.country_id) = (SELECT count(*) FROM countries)
ORDER BY avg_pct_of_births DESC
LIMIT 50""",
    # -----------------------------------------------------------------------
    # Country Signature Names
    # -----------------------------------------------------------------------
    "Country Signature Names": """\
WITH latest AS (
    SELECT country_id, gender_id, max(year) AS max_year
    FROM mv_forename_rankings
    GROUP BY country_id, gender_id
),
base AS (
    SELECT r.name, r.gender_id, r.country_id, r.pct_of_year_total AS local_pct
    FROM mv_forename_rankings r
    JOIN latest l
      ON r.country_id = l.country_id
     AND r.gender_id = l.gender_id
     AND r.year = l.max_year
),
global_avg AS (
    SELECT name, gender_id,
           avg(local_pct) AS avg_pct,
           count(DISTINCT country_id) AS num_countries
    FROM base
    GROUP BY name, gender_id
)
SELECT
    b.name,
    c.name AS country, c.iso_alpha2 AS country_code,
    g.label AS gender,
    round(b.local_pct, 4) AS local_pct,
    round(ga.avg_pct, 4) AS global_avg_pct,
    round(b.local_pct / nullif(ga.avg_pct, 0), 2) AS distinctiveness_ratio
FROM base b
JOIN global_avg ga USING (name, gender_id)
JOIN countries c ON b.country_id = c.country_id
JOIN genders g ON b.gender_id = g.gender_id
WHERE ga.num_countries >= 2
  AND b.local_pct >= 0.01
ORDER BY distinctiveness_ratio DESC""",
    # -----------------------------------------------------------------------
    # Biggest Movers  (references mv_forename_rankings)
    # -----------------------------------------------------------------------
    "Biggest Movers": """\
WITH lagged AS (
    SELECT
        name, gender_id, country_id, year, rank, count,
        lag(rank) OVER (
            PARTITION BY name, gender_id, country_id ORDER BY year
        ) AS prev_rank,
        lag(year) OVER (
            PARTITION BY name, gender_id, country_id ORDER BY year
        ) AS prev_year
    FROM mv_forename_rankings
)
SELECT
    l.name,
    c.name AS country, c.iso_alpha2 AS country_code, g.label AS gender,
    l.year,
    l.rank AS current_rank,
    l.prev_rank,
    (l.prev_rank - l.rank)::integer AS rank_change,
    abs(l.prev_rank - l.rank)::integer AS abs_rank_change,
    l.count,
    round((l.count::numeric / c.population) * 1000000, 2) AS count_per_m
FROM lagged l
JOIN countries c ON l.country_id = c.country_id
JOIN genders g ON l.gender_id = g.gender_id
WHERE l.prev_year = l.year - interval '1 year'
ORDER BY abs(l.prev_rank - l.rank) DESC
LIMIT 20""",
    # -----------------------------------------------------------------------
    # Letter Distribution (latest year per country, all genders)
    # -----------------------------------------------------------------------
    "Letter Distribution": """\
WITH latest AS (
    SELECT country_id, max(year) AS max_year
    FROM public.forenames
    GROUP BY country_id
),
letters AS (
    SELECT chr(n) AS first_letter
    FROM generate_series(65, 90) AS n
),
letter_counts AS (
    SELECT
        f.country_id,
        upper(left(unaccent(f.name), 1)) AS first_letter,
        sum(f.count) AS letter_count
    FROM public.forenames f
    JOIN latest l ON f.country_id = l.country_id AND f.year = l.max_year
    GROUP BY f.country_id, upper(left(unaccent(f.name), 1))
),
country_totals AS (
    SELECT country_id, sum(letter_count) AS total
    FROM letter_counts
    GROUP BY country_id
),
grid AS (
    SELECT c.country_id, lt.first_letter
    FROM (SELECT DISTINCT country_id FROM latest) c
    CROSS JOIN letters lt
)
SELECT
    c.name AS country, c.iso_alpha2 AS country_code,
    g.first_letter,
    coalesce(lc.letter_count, 0)::integer AS letter_count,
    CASE WHEN ct.total > 0
        THEN round((coalesce(lc.letter_count, 0)::numeric / ct.total) * 100, 2)
        ELSE 0
    END AS letter_pct
FROM grid g
LEFT JOIN letter_counts lc ON g.country_id = lc.country_id AND g.first_letter = lc.first_letter
JOIN country_totals ct ON g.country_id = ct.country_id
JOIN countries c ON g.country_id = c.country_id
ORDER BY g.first_letter, c.name""",
    # -----------------------------------------------------------------------
    # Source Quality
    # -----------------------------------------------------------------------
    "Source Quality Scorecard": """\
WITH raw_counts AS (
    SELECT 'ssa_forenames' AS source_id, count(*) AS row_count FROM raw.ssa_forenames
    UNION ALL SELECT 'ons_forenames', count(*) FROM raw.ons_forenames
    UNION ALL SELECT 'nrs_forenames', count(*) FROM raw.nrs_forenames
    UNION ALL SELECT 'nisra_forenames', count(*) FROM raw.nisra_forenames
    UNION ALL SELECT 'wales_forenames', count(*) FROM raw.wales_forenames
    UNION ALL SELECT 'cso_forenames_boys', count(*) FROM raw.cso_forenames_boys
    UNION ALL SELECT 'cso_forenames_girls', count(*) FROM raw.cso_forenames_girls
    UNION ALL SELECT 'census_surnames', count(*) FROM raw.census_surnames
    UNION ALL SELECT 'england_surnames', count(*) FROM raw.england_surnames
    UNION ALL SELECT 'nrs_surnames', count(*) FROM raw.nrs_surnames
    UNION ALL SELECT 'cso_surnames', count(*) FROM raw.cso_surnames
    UNION ALL SELECT 'ni_surnames', count(*) FROM raw.ni_surnames
    UNION ALL SELECT 'wales_surnames', count(*) FROM raw.wales_surnames
),
log_stats AS (
    SELECT
        source_id,
        count(*) FILTER (WHERE status = 'success') AS ingest_success_count,
        count(*) FILTER (WHERE status = 'failed') AS ingest_fail_count,
        max(started_at) AS last_run_at,
        (SELECT sum(fl2.row_count)
         FROM raw.file_log fl2
         WHERE fl2.source_id = fl.source_id
           AND fl2.status = 'success'
           AND fl2.started_at = (
               SELECT max(fl3.started_at) FROM raw.file_log fl3
               WHERE fl3.source_id = fl.source_id AND fl3.status = 'success'
           )
        ) AS last_success_rows
    FROM raw.file_log fl
    GROUP BY source_id
)
SELECT
    r.source_id,
    r.row_count::integer,
    coalesce(l.ingest_success_count, 0)::integer AS ingest_success_count,
    coalesce(l.ingest_fail_count, 0)::integer AS ingest_fail_count,
    l.last_run_at,
    coalesce(l.last_success_rows, 0)::integer AS last_success_rows
FROM raw_counts r
LEFT JOIN log_stats l ON r.source_id = l.source_id""",
    # -----------------------------------------------------------------------
    # Forename Rankings (latest year per country/gender from MV)
    # -----------------------------------------------------------------------
    "Forename Rankings": """\
SELECT r.name, r.year, r.count, r.rank, r.pct_of_year_total,
       round((r.count::numeric / c.population) * 1000000, 2) AS count_per_m,
       c.name AS country, c.iso_alpha2 AS country_code, g.label AS gender
FROM mv_forename_rankings r
JOIN countries c ON r.country_id = c.country_id
JOIN genders g ON r.gender_id = g.gender_id
JOIN (SELECT country_id, gender_id, MAX(year) AS max_year
      FROM mv_forename_rankings GROUP BY country_id, gender_id) latest
  ON r.country_id = latest.country_id
 AND r.gender_id = latest.gender_id
 AND r.year = latest.max_year""",
    # -----------------------------------------------------------------------
    # Surname Rankings (latest year per country from MV)
    # -----------------------------------------------------------------------
    "Surname Rankings": """\
SELECT r.name, r.year, r.count, r.rank, r.pct_of_year_total,
       round((r.count::numeric / c.population) * 1000000, 2) AS count_per_m,
       c.name AS country, c.iso_alpha2 AS country_code
FROM mv_surname_rankings r
JOIN countries c ON r.country_id = c.country_id
JOIN (SELECT country_id, MAX(year) AS max_year
      FROM mv_surname_rankings GROUP BY country_id) latest
  ON r.country_id = latest.country_id
 AND r.year = latest.max_year""",
    # -----------------------------------------------------------------------
    # Forename Trends (raw counts)
    # -----------------------------------------------------------------------
    "Forename Trends": """\
SELECT f.name, f.year, f.count,
       round((f.count::numeric / c.population) * 1000000, 2) AS count_per_m,
       c.name AS country, c.iso_alpha2 AS country_code, g.label AS gender
FROM forenames f
JOIN countries c ON f.country_id = c.country_id
JOIN genders g ON f.gender_id = g.gender_id""",
    # -----------------------------------------------------------------------
    # Surname Trends (raw counts)
    # -----------------------------------------------------------------------
    "Surname Trends": """\
SELECT s.name, s.year, s.count,
       round((s.count::numeric / c.population) * 1000000, 2) AS count_per_m,
       c.name AS country, c.iso_alpha2 AS country_code
FROM surnames s
JOIN countries c ON s.country_id = c.country_id""",
    # -----------------------------------------------------------------------
    # Forenames by Country (aggregated)
    # -----------------------------------------------------------------------
    "Forenames by Country": """\
SELECT c.name AS country, g.label AS gender,
       COUNT(*) AS row_count, COUNT(DISTINCT f.name) AS unique_names,
       SUM(f.count) AS total_births,
       round((SUM(f.count)::numeric / c.population) * 1000000, 2) AS total_births_per_m
FROM forenames f
JOIN countries c ON f.country_id = c.country_id
JOIN genders g ON f.gender_id = g.gender_id
GROUP BY c.name, g.label, c.population""",
    # -----------------------------------------------------------------------
    # Forename Year Coverage (multi-year countries only)
    # -----------------------------------------------------------------------
    "Forename Year Coverage": """\
WITH multi_year AS (
    SELECT country_id FROM forenames
    GROUP BY country_id HAVING COUNT(DISTINCT year) > 1
)
SELECT c.name AS country, EXTRACT(YEAR FROM f.year)::int::text AS year, COUNT(*) AS row_count
FROM forenames f
JOIN countries c ON f.country_id = c.country_id
JOIN multi_year m ON f.country_id = m.country_id
GROUP BY c.name, year""",
    # -----------------------------------------------------------------------
    # Surname Year Coverage (multi-year countries only)
    # -----------------------------------------------------------------------
    "Surname Year Coverage": """\
WITH multi_year AS (
    SELECT country_id FROM surnames
    GROUP BY country_id HAVING COUNT(DISTINCT year) > 1
)
SELECT c.name AS country, EXTRACT(YEAR FROM s.year)::int::text AS year, COUNT(*) AS row_count
FROM surnames s
JOIN countries c ON s.country_id = c.country_id
JOIN multi_year m ON s.country_id = m.country_id
GROUP BY c.name, year""",
    # -----------------------------------------------------------------------
    # Raw Source Counts
    # -----------------------------------------------------------------------
    "Raw Source Counts": """\
SELECT 'ssa_forenames' AS source, COUNT(*) AS row_count FROM raw.ssa_forenames
UNION ALL SELECT 'ons_forenames', COUNT(*) FROM raw.ons_forenames
UNION ALL SELECT 'nrs_forenames', COUNT(*) FROM raw.nrs_forenames
UNION ALL SELECT 'nisra_forenames', COUNT(*) FROM raw.nisra_forenames
UNION ALL SELECT 'wales_forenames', COUNT(*) FROM raw.wales_forenames
UNION ALL SELECT 'cso_forenames_boys', COUNT(*) FROM raw.cso_forenames_boys
UNION ALL SELECT 'cso_forenames_girls', COUNT(*) FROM raw.cso_forenames_girls
UNION ALL SELECT 'census_surnames', COUNT(*) FROM raw.census_surnames
UNION ALL SELECT 'england_surnames', COUNT(*) FROM raw.england_surnames
UNION ALL SELECT 'nrs_surnames', COUNT(*) FROM raw.nrs_surnames
UNION ALL SELECT 'cso_surnames', COUNT(*) FROM raw.cso_surnames
UNION ALL SELECT 'ni_surnames', COUNT(*) FROM raw.ni_surnames
UNION ALL SELECT 'wales_surnames', COUNT(*) FROM raw.wales_surnames""",
    # -----------------------------------------------------------------------
    # Empty Sources
    # -----------------------------------------------------------------------
    "Empty Sources": """\
SELECT source, row_count FROM (
    SELECT 'ssa_forenames' AS source, COUNT(*) AS row_count FROM raw.ssa_forenames
    UNION ALL SELECT 'ons_forenames', COUNT(*) FROM raw.ons_forenames
    UNION ALL SELECT 'nrs_forenames', COUNT(*) FROM raw.nrs_forenames
    UNION ALL SELECT 'nisra_forenames', COUNT(*) FROM raw.nisra_forenames
    UNION ALL SELECT 'wales_forenames', COUNT(*) FROM raw.wales_forenames
    UNION ALL SELECT 'cso_forenames_boys', COUNT(*) FROM raw.cso_forenames_boys
    UNION ALL SELECT 'cso_forenames_girls', COUNT(*) FROM raw.cso_forenames_girls
    UNION ALL SELECT 'census_surnames', COUNT(*) FROM raw.census_surnames
    UNION ALL SELECT 'england_surnames', COUNT(*) FROM raw.england_surnames
    UNION ALL SELECT 'nrs_surnames', COUNT(*) FROM raw.nrs_surnames
    UNION ALL SELECT 'cso_surnames', COUNT(*) FROM raw.cso_surnames
    UNION ALL SELECT 'ni_surnames', COUNT(*) FROM raw.ni_surnames
    UNION ALL SELECT 'wales_surnames', COUNT(*) FROM raw.wales_surnames
) counts ORDER BY source""",
    # -----------------------------------------------------------------------
    # Rejected Rows by Source
    # -----------------------------------------------------------------------
    "Rejected Rows": """\
SELECT
    r.source_table,
    coalesce(fl.filename, 'unknown') AS filename,
    r.rejection_reason,
    count(*) AS rejected_count
FROM rejected.rej_all r
LEFT JOIN raw.file_log fl ON r.file_log_id = fl.id
GROUP BY r.source_table, fl.filename, r.rejection_reason
ORDER BY r.source_table, rejected_count DESC""",
    # -----------------------------------------------------------------------
    # Forename Trends Multi-Year (multi-year countries only, % of births)
    # -----------------------------------------------------------------------
    "Forename Trends Multi-Year": """\
WITH multi_year AS (
    SELECT country_id FROM forenames
    GROUP BY country_id HAVING COUNT(DISTINCT year) > 1
),
year_totals AS (
    SELECT country_id, gender_id, year, sum(count) AS total
    FROM forenames
    GROUP BY country_id, gender_id, year
)
SELECT f.name, f.year, f.count,
       CASE WHEN yt.total > 0
           THEN round((f.count::numeric / yt.total) * 100, 4)
           ELSE NULL
       END AS pct_of_year_total,
       c.name AS country, c.iso_alpha2 AS country_code, g.label AS gender
FROM forenames f
JOIN countries c ON f.country_id = c.country_id
JOIN genders g ON f.gender_id = g.gender_id
JOIN multi_year m ON f.country_id = m.country_id
JOIN year_totals yt
  ON f.country_id = yt.country_id
 AND f.gender_id = yt.gender_id
 AND f.year = yt.year""",
    # -----------------------------------------------------------------------
    # Top Name Share (rank=1 names over time)
    # -----------------------------------------------------------------------
    "Top Name Share": """\
WITH multi_year AS (
    SELECT country_id FROM forenames
    GROUP BY country_id HAVING COUNT(DISTINCT year) > 1
)
SELECT r.name AS top_name, r.year, r.pct_of_year_total AS top_name_pct,
       c.name AS country, c.iso_alpha2 AS country_code, g.label AS gender
FROM mv_forename_rankings r
JOIN countries c ON r.country_id = c.country_id
JOIN genders g ON r.gender_id = g.gender_id
JOIN multi_year m ON r.country_id = m.country_id
WHERE r.rank = 1""",
}


# ---------------------------------------------------------------------------
# Dataset list and column/metric config
# ---------------------------------------------------------------------------

DATASETS = {
    name: QUERIES[name]
    for name in [
        "Forename Rankings",
        "Surname Rankings",
        "Forename Trends",
        "Surname Trends",
        "Forenames by Country",
        "Forename Year Coverage",
        "Surname Year Coverage",
        "Raw Source Counts",
        "Empty Sources",
        "Name Diversity",
        "Gender-Neutral Names",
        "Cross-Country Names",
        "Country Signature Names",
        "Biggest Movers",
        "Letter Distribution",
        "Source Quality Scorecard",
        "Rejected Rows",
        "Forename Trends Multi-Year",
        "Top Name Share",
    ]
}


DATASET_CONFIG = {
    "Forename Rankings": {
        "dimensions": ["name", "country", "country_code", "gender", "year"],
        "temporal": "year",
        "metrics": [
            {"metric_name": "Total Births", "expression": "SUM(count)", "d3format": ",d"},
            {"metric_name": "Avg Rank", "expression": "AVG(rank)", "d3format": ",.1f"},
            {
                "metric_name": "Avg % of Year",
                "expression": "AVG(pct_of_year_total)",
                "d3format": ",.2f",
            },
        ],
    },
    "Surname Rankings": {
        "dimensions": ["name", "country", "country_code", "year"],
        "temporal": "year",
        "metrics": [
            {"metric_name": "Total Count", "expression": "SUM(count)", "d3format": ",d"},
            {"metric_name": "Avg Rank", "expression": "AVG(rank)", "d3format": ",.1f"},
            {
                "metric_name": "Avg % of Year",
                "expression": "AVG(pct_of_year_total)",
                "d3format": ",.2f",
            },
        ],
    },
    "Forename Trends": {
        "dimensions": ["name", "country", "country_code", "gender", "year"],
        "temporal": "year",
        "metrics": [
            {"metric_name": "Total Births", "expression": "SUM(count)", "d3format": ",d"},
            {
                "metric_name": "Unique Names",
                "expression": "COUNT(DISTINCT name)",
                "d3format": ",d",
            },
        ],
    },
    "Surname Trends": {
        "dimensions": ["name", "country", "country_code", "year"],
        "temporal": "year",
        "metrics": [
            {"metric_name": "Total Count", "expression": "SUM(count)", "d3format": ",d"},
            {
                "metric_name": "Unique Names",
                "expression": "COUNT(DISTINCT name)",
                "d3format": ",d",
            },
        ],
    },
    "Forenames by Country": {
        "dimensions": ["country", "gender"],
        "metrics": [
            {"metric_name": "Rows", "expression": "SUM(row_count)", "d3format": ",d"},
            {"metric_name": "Unique Names", "expression": "SUM(unique_names)", "d3format": ",d"},
            {"metric_name": "Total Births", "expression": "SUM(total_births)", "d3format": ",d"},
        ],
    },
    "Forename Year Coverage": {
        "dimensions": ["country", "year"],
        "temporal": "year",
        "metrics": [
            {"metric_name": "Rows", "expression": "SUM(row_count)", "d3format": ",d"},
        ],
    },
    "Surname Year Coverage": {
        "dimensions": ["country", "year"],
        "temporal": "year",
        "metrics": [
            {"metric_name": "Rows", "expression": "SUM(row_count)", "d3format": ",d"},
        ],
    },
    "Raw Source Counts": {
        "dimensions": ["source"],
        "metrics": [
            {"metric_name": "Row Count", "expression": "MAX(row_count)", "d3format": ",d"},
        ],
    },
    "Empty Sources": {
        "dimensions": ["source"],
        "metrics": [
            {"metric_name": "Row Count", "expression": "MAX(row_count)", "d3format": ",d"},
        ],
    },
    "Name Diversity": {
        "dimensions": ["country", "country_code", "gender", "year"],
        "temporal": "year",
        "metrics": [
            {"metric_name": "Unique Names", "expression": "MAX(unique_names)", "d3format": ",d"},
            {
                "metric_name": "Unique Names per 1M",
                "expression": "MAX(unique_names_per_m)",
                "d3format": ",.1f",
            },
            {"metric_name": "Total Births", "expression": "SUM(total_births)", "d3format": ",d"},
            {
                "metric_name": "Top-10 Concentration %",
                "expression": "AVG(top10_concentration_pct)",
                "d3format": ",.1f",
            },
        ],
    },
    "Gender-Neutral Names": {
        "dimensions": ["name", "country", "country_code"],
        "metrics": [
            {"metric_name": "Male Count", "expression": "SUM(male_count)", "d3format": ",d"},
            {"metric_name": "Female Count", "expression": "SUM(female_count)", "d3format": ",d"},
            {"metric_name": "Total Count", "expression": "SUM(total_count)", "d3format": ",d"},
            {"metric_name": "% of Births", "expression": "AVG(pct_of_births)", "d3format": ",.2f"},
            {"metric_name": "Balance %", "expression": "AVG(balance_pct)", "d3format": ",.1f"},
        ],
    },
    "Cross-Country Names": {
        "dimensions": ["name", "gender"],
        "metrics": [
            {
                "metric_name": "Avg % of Births",
                "expression": "MAX(avg_pct_of_births)",
                "d3format": ",.2f",
            },
        ],
    },
    "Country Signature Names": {
        "dimensions": ["name", "country", "country_code", "gender"],
        "metrics": [
            {"metric_name": "Local %", "expression": "MAX(local_pct)", "d3format": ",.2f"},
            {
                "metric_name": "Global Avg %",
                "expression": "MAX(global_avg_pct)",
                "d3format": ",.2f",
            },
            {
                "metric_name": "Distinctiveness",
                "expression": "MAX(distinctiveness_ratio)",
                "d3format": ",.1f",
            },
        ],
    },
    "Biggest Movers": {
        "dimensions": ["name", "country", "country_code", "gender", "year"],
        "temporal": "year",
        "metrics": [
            {
                "metric_name": "Max Rank Change",
                "expression": "MAX(abs_rank_change)",
                "d3format": ",d",
            },
            {
                "metric_name": "Avg Rank Change",
                "expression": "AVG(rank_change)",
                "d3format": ",.1f",
            },
            {"metric_name": "Total Births", "expression": "SUM(count)", "d3format": ",d"},
        ],
    },
    "Letter Distribution": {
        "dimensions": ["country", "country_code", "first_letter"],
        "metrics": [
            {"metric_name": "Letter Count", "expression": "SUM(letter_count)", "d3format": ",d"},
            {"metric_name": "Avg Letter %", "expression": "AVG(letter_pct)", "d3format": ",.2f"},
        ],
    },
    "Source Quality Scorecard": {
        "dimensions": ["source_id"],
        "temporal": "last_run_at",
        "metrics": [
            {"metric_name": "Row Count", "expression": "MAX(row_count)", "d3format": ",d"},
            {
                "metric_name": "Successes",
                "expression": "SUM(ingest_success_count)",
                "d3format": ",d",
            },
            {"metric_name": "Failures", "expression": "SUM(ingest_fail_count)", "d3format": ",d"},
            {
                "metric_name": "Last Success Rows",
                "expression": "MAX(last_success_rows)",
                "d3format": ",d",
            },
        ],
    },
    "Rejected Rows": {
        "dimensions": ["source_table", "filename", "rejection_reason"],
        "metrics": [
            {
                "metric_name": "Rejected Count",
                "expression": "SUM(rejected_count)",
                "d3format": ",d",
            },
        ],
    },
    "Forename Trends Multi-Year": {
        "dimensions": ["name", "country", "country_code", "gender", "year"],
        "temporal": "year",
        "metrics": [
            {"metric_name": "Total Births", "expression": "SUM(count)", "d3format": ",d"},
            {
                "metric_name": "% of Births",
                "expression": "AVG(pct_of_year_total)",
                "d3format": ",.2f",
            },
        ],
    },
    "Top Name Share": {
        "dimensions": ["top_name", "country", "country_code", "gender", "year"],
        "temporal": "year",
        "metrics": [
            {"metric_name": "Top Name %", "expression": "AVG(top_name_pct)", "d3format": ",.2f"},
        ],
    },
}


# ---------------------------------------------------------------------------
# Saved queries (example queries shown in Superset's SQL Lab)
# ---------------------------------------------------------------------------

SAVED_QUERIES = [
    {
        "label": "Top forenames by country",
        "description": "Top 10 forenames for US (most recent year), with gender and rank",
        "sql": (
            "SELECT r.name, g.label AS gender, r.year, r.count, r.rank, r.pct_of_year_total\n"
            "FROM mv_forename_rankings r\n"
            "JOIN countries c ON r.country_id = c.country_id\n"
            "JOIN genders g ON r.gender_id = g.gender_id\n"
            "WHERE c.iso_alpha2 = 'US'\n"
            "  AND r.year = (SELECT MAX(year) FROM mv_forename_rankings r2\n"
            "                JOIN countries c2 ON r2.country_id = c2.country_id\n"
            "                WHERE c2.iso_alpha2 = 'US')\n"
            "ORDER BY r.rank\n"
            "LIMIT 10;"
        ),
    },
    {
        "label": "Name popularity over time",
        "description": "Track the name 'Emma' across all years in the US",
        "sql": (
            "SELECT f.year, g.label AS gender, f.count\n"
            "FROM forenames f\n"
            "JOIN countries c ON f.country_id = c.country_id\n"
            "JOIN genders g ON f.gender_id = g.gender_id\n"
            "WHERE f.name = 'Emma' AND c.iso_alpha2 = 'US'\n"
            "ORDER BY f.year;"
        ),
    },
    {
        "label": "Top surnames by country",
        "description": "Top 10 surnames across all countries",
        "sql": (
            "SELECT r.name, c.name AS country, r.year, r.count, r.rank\n"
            "FROM mv_surname_rankings r\n"
            "JOIN countries c ON r.country_id = c.country_id\n"
            "WHERE r.rank <= 10\n"
            "ORDER BY c.name, r.rank\n"
            "LIMIT 50;"
        ),
    },
]
