-- Recreate materialized views (dbt's view swap drops them via CASCADE).
--
-- This cannot live in Alembic because the MVs depend on dbt views (vw_forenames,
-- vw_surnames) which don't exist at migration time. This script runs after dbt
-- at setup, and again after every pipeline ingestion via the refresh_views task.

-- Drop in reverse dependency order
DROP MATERIALIZED VIEW IF EXISTS public.mv_surname_rankings CASCADE;
DROP MATERIALIZED VIEW IF EXISTS public.mv_forename_rankings CASCADE;
DROP MATERIALIZED VIEW IF EXISTS public.surnames CASCADE;
DROP MATERIALIZED VIEW IF EXISTS public.forenames CASCADE;

-- Recreate from dbt views (forward dependency order)
CREATE MATERIALIZED VIEW public.forenames AS
SELECT
    name,
    gender_id,
    country_id,
    year,
    sum(count) AS count
FROM public.vw_forenames
GROUP BY name, gender_id, country_id, year;

CREATE UNIQUE INDEX uq_forenames_natural_key
    ON public.forenames (name, gender_id, country_id, year);
CREATE INDEX idx_forenames_country_gender_year
    ON public.forenames (country_id, gender_id, year);
CREATE INDEX idx_forenames_name_country_gender
    ON public.forenames (name, country_id, gender_id);


CREATE MATERIALIZED VIEW public.surnames AS
SELECT
    name,
    country_id,
    year,
    sum(count) AS count
FROM public.vw_surnames
GROUP BY name, country_id, year;

CREATE UNIQUE INDEX uq_surnames_natural_key
    ON public.surnames (name, country_id, year);
CREATE INDEX idx_surnames_country_year
    ON public.surnames (country_id, year);
CREATE INDEX idx_surnames_name_country
    ON public.surnames (name, country_id);


CREATE MATERIALIZED VIEW public.mv_forename_rankings AS
WITH year_totals AS (
    SELECT year, gender_id, country_id, sum(count) AS total
    FROM public.forenames
    GROUP BY year, gender_id, country_id
)
SELECT
    f.name,
    f.gender_id,
    f.country_id,
    f.year,
    f.count,
    rank() OVER (
        PARTITION BY f.year, f.gender_id, f.country_id
        ORDER BY f.count DESC
    )::integer AS rank,
    CASE WHEN yt.total > 0
        THEN round((f.count::numeric / yt.total) * 100, 4)
        ELSE NULL
    END AS pct_of_year_total
FROM public.forenames f
JOIN year_totals yt
    ON f.year = yt.year
    AND f.gender_id = yt.gender_id
    AND f.country_id = yt.country_id;

CREATE UNIQUE INDEX uq_mvfr_natural_key
    ON public.mv_forename_rankings (name, gender_id, country_id, year);
CREATE INDEX idx_mvfr_country_gender_year
    ON public.mv_forename_rankings (country_id, gender_id, year);


CREATE MATERIALIZED VIEW public.mv_surname_rankings AS
WITH year_totals AS (
    SELECT year, country_id, sum(count) AS total
    FROM public.surnames
    GROUP BY year, country_id
)
SELECT
    s.name,
    s.country_id,
    s.year,
    s.count,
    rank() OVER (
        PARTITION BY s.year, s.country_id
        ORDER BY s.count DESC
    )::integer AS rank,
    CASE WHEN yt.total > 0
        THEN round((s.count::numeric / yt.total) * 100, 4)
        ELSE NULL
    END AS pct_of_year_total
FROM public.surnames s
JOIN year_totals yt
    ON s.year = yt.year
    AND s.country_id = yt.country_id;

CREATE UNIQUE INDEX uq_mvsr_natural_key
    ON public.mv_surname_rankings (name, country_id, year);
CREATE INDEX idx_mvsr_country_year
    ON public.mv_surname_rankings (country_id, year);
