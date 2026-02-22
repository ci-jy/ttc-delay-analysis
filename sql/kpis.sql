-- KPI views over the star schema. Each view column that a Power BI measure
-- reproduces is named in that measure's SqlTwin annotation
-- (powerbi/TTCDelay.SemanticModel/definition/tables/*.tmdl).
--
-- Conventions
--   line_code 'ALL' = whole network (includes incidents logged against
--   several lines or none). Minutes are Min Delay unless named gap_*.

-- Monthly KPIs on a complete line x month grid, so that months with no
-- incidents count as zero and LAG/rolling windows step one month at a time.
CREATE OR REPLACE VIEW kpi_month AS
WITH months AS (
    SELECT DISTINCT month_start FROM dim_date
),
lines AS (
    SELECT line_code FROM dim_line WHERE is_subway_line
    UNION ALL SELECT 'ALL'
),
agg AS (
    SELECT
        coalesce(line_code, 'ALL')                 AS line_code,
        month_start,
        count(*)                                   AS incidents,
        count(*) FILTER (WHERE min_delay > 0)      AS delay_incidents,
        sum(min_delay)                             AS delay_minutes,
        sum(min_gap)                               AS gap_minutes
    FROM v_delay
    GROUP BY GROUPING SETS ((line_code, month_start), (month_start))
),
grid AS (
    SELECT
        l.line_code,
        m.month_start,
        coalesce(a.incidents, 0)        AS incidents,
        coalesce(a.delay_incidents, 0)  AS delay_incidents,
        coalesce(a.delay_minutes, 0)    AS delay_minutes,
        coalesce(a.gap_minutes, 0)      AS gap_minutes
    FROM lines l
    CROSS JOIN months m
    LEFT JOIN agg a ON a.line_code = l.line_code AND a.month_start = m.month_start
),
windowed AS (
    SELECT
        *,
        lag(delay_minutes, 1)  OVER w AS prev_month_minutes,
        lag(incidents, 1)      OVER w AS prev_month_incidents,
        lag(delay_minutes, 12) OVER w AS same_month_last_year_minutes,
        lag(incidents, 12)     OVER w AS same_month_last_year_incidents,
        sum(delay_minutes) OVER (w ROWS BETWEEN 11 PRECEDING AND CURRENT ROW) AS rolling_12m_minutes,
        sum(incidents)     OVER (w ROWS BETWEEN 11 PRECEDING AND CURRENT ROW) AS rolling_12m_incidents,
        count(*)           OVER (w ROWS BETWEEN 11 PRECEDING AND CURRENT ROW) AS rolling_window_months
    FROM grid
    WINDOW w AS (PARTITION BY line_code ORDER BY month_start)
)
SELECT
    line_code,
    month_start,
    strftime(month_start, '%Y-%m')                                        AS year_month,
    year(month_start)                                                     AS year,
    incidents,
    delay_incidents,
    delay_minutes,
    gap_minutes,
    delay_minutes / nullif(incidents, 0)                                  AS minutes_per_incident,
    prev_month_minutes,
    (delay_minutes - prev_month_minutes) / nullif(prev_month_minutes, 0)  AS mom_change_minutes,
    (incidents - prev_month_incidents) / nullif(prev_month_incidents, 0)  AS mom_change_incidents,
    same_month_last_year_minutes,
    (delay_minutes - same_month_last_year_minutes)
        / nullif(same_month_last_year_minutes, 0)                         AS yoy_change_minutes,
    (incidents - same_month_last_year_incidents)
        / nullif(same_month_last_year_incidents, 0)                       AS yoy_change_incidents,
    rolling_12m_minutes,
    rolling_12m_incidents,
    rolling_window_months
FROM windowed;

-- Yearly KPIs per line and network. The previous-year comparison covers the
-- same calendar span: when the last year is partial (data to 31 August), it is
-- compared with 1 January-31 August of the year before.
CREATE OR REPLACE VIEW kpi_year AS
WITH lines AS (
    SELECT line_code FROM dim_line WHERE is_subway_line
    UNION ALL SELECT 'ALL'
),
years AS (
    SELECT year, min(date) AS first_date, max(date) AS last_date
    FROM dim_date GROUP BY year
),
daily AS (
    SELECT coalesce(line_code, 'ALL') AS line_code, date,
           count(*) AS incidents,
           count(*) FILTER (WHERE min_delay > 0) AS delay_incidents,
           sum(min_delay) AS delay_minutes,
           sum(min_gap) AS gap_minutes
    FROM v_delay
    GROUP BY GROUPING SETS ((line_code, date), (date))
),
cur AS (
    SELECT l.line_code, y.year,
           coalesce(sum(d.incidents), 0)       AS incidents,
           coalesce(sum(d.delay_incidents), 0) AS delay_incidents,
           coalesce(sum(d.delay_minutes), 0)   AS delay_minutes,
           coalesce(sum(d.gap_minutes), 0)     AS gap_minutes
    FROM lines l CROSS JOIN years y
    LEFT JOIN daily d ON d.line_code = l.line_code AND d.date BETWEEN y.first_date AND y.last_date
    GROUP BY l.line_code, y.year
),
prev AS (
    SELECT l.line_code, y.year,
           sum(d.incidents)     AS prev_year_incidents,
           sum(d.delay_minutes) AS prev_year_minutes
    FROM lines l CROSS JOIN years y
    JOIN years p ON p.year = y.year - 1
    LEFT JOIN daily d
      ON d.line_code = l.line_code
     AND d.date BETWEEN p.first_date AND (y.last_date - INTERVAL 1 YEAR)
    GROUP BY l.line_code, y.year
)
SELECT
    c.line_code,
    c.year,
    c.incidents,
    c.delay_incidents,
    c.delay_minutes,
    c.gap_minutes,
    c.delay_minutes / nullif(c.incidents, 0)                                   AS minutes_per_incident,
    coalesce(p.prev_year_minutes, CASE WHEN p.year IS NOT NULL THEN 0 END)      AS prev_year_minutes,
    coalesce(p.prev_year_incidents, CASE WHEN p.year IS NOT NULL THEN 0 END)    AS prev_year_incidents,
    (c.delay_minutes - p.prev_year_minutes) / nullif(p.prev_year_minutes, 0)    AS yoy_change_minutes,
    (c.incidents - p.prev_year_incidents) / nullif(p.prev_year_incidents, 0)    AS yoy_change_incidents
FROM cur c
LEFT JOIN prev p USING (line_code, year);

-- Minutes by cause for every (line, year) scope, including 'ALL' lines and
-- 'ALL' years, with share, rank and cumulative share for the Pareto.
-- Ties in minutes are broken by cause code so the order is deterministic.
CREATE OR REPLACE VIEW kpi_cause AS
WITH scoped AS (
    SELECT
        coalesce(line_code, 'ALL')          AS line_scope,
        coalesce(CAST(year AS VARCHAR), 'ALL') AS year_scope,
        cause_code,
        count(*)        AS incidents,
        sum(min_delay)  AS delay_minutes
    FROM v_delay
    GROUP BY GROUPING SETS (
        (line_code, year, cause_code),
        (line_code, cause_code),
        (year, cause_code),
        (cause_code)
    )
),
ranked AS (
    SELECT
        s.*,
        sum(delay_minutes) OVER scope AS scope_minutes,
        row_number() OVER (PARTITION BY line_scope, year_scope
                           ORDER BY delay_minutes DESC, cause_code) AS minutes_rank
    FROM scoped s
    WINDOW scope AS (PARTITION BY line_scope, year_scope)
),
cumulated AS (
    SELECT
        r.*,
        sum(delay_minutes) OVER (PARTITION BY line_scope, year_scope ORDER BY minutes_rank
                                 ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_minutes
    FROM ranked r
)
SELECT
    c.line_scope,
    c.year_scope,
    c.cause_code,
    d.cause_description,
    d.cause_category,
    c.incidents,
    c.delay_minutes,
    c.delay_minutes / nullif(c.incidents, 0)           AS minutes_per_incident,
    c.delay_minutes / nullif(c.scope_minutes, 0)       AS share_of_minutes,
    c.minutes_rank,
    c.cumulative_minutes / nullif(c.scope_minutes, 0)  AS cumulative_share,
    -- A cause is in the "vital few" if the causes ranked above it have not yet
    -- reached 80% of the scope's minutes.
    c.delay_minutes > 0
        AND (c.cumulative_minutes - c.delay_minutes) / nullif(c.scope_minutes, 0) < 0.8 AS in_pareto_80
FROM cumulated c
JOIN dim_cause d USING (cause_code);

-- How few causes make up 80% of lost minutes, per (line, year) scope.
CREATE OR REPLACE VIEW kpi_pareto AS
SELECT
    line_scope,
    year_scope,
    sum(delay_minutes)                                  AS delay_minutes,
    count(*) FILTER (WHERE delay_minutes > 0)           AS causes_with_minutes,
    count(*) FILTER (WHERE in_pareto_80)                AS causes_to_80pct,
    count(*) FILTER (WHERE in_pareto_80)
        / nullif(count(*) FILTER (WHERE delay_minutes > 0), 0) AS share_of_causes_to_80pct,
    max(share_of_minutes)                               AS top_cause_share
FROM kpi_cause
GROUP BY line_scope, year_scope;

-- Minutes by cause category (Equipment, Plant, Security, ...), per line and year.
CREATE OR REPLACE VIEW kpi_category_year AS
SELECT
    line_code,
    year,
    cause_category,
    count(*)        AS incidents,
    sum(min_delay)  AS delay_minutes,
    sum(min_delay) / sum(sum(min_delay)) OVER (PARTITION BY line_code, year) AS share_of_minutes
FROM v_delay
GROUP BY line_code, year, cause_category;
