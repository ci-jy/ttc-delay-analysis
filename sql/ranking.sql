-- Fair station reliability ranking: empirical-Bayes shrinkage of each
-- station's minutes of delay per incident toward its line's rate.
--
-- Model (normal-normal, method of moments):
--   x_i      = mean minutes per incident at station i (n_i incidents)
--   mu_L     = line L's pooled mean = line minutes / line incidents
--   sigma2_L = pooled within-station variance of minutes on line L
--   v_i      = sigma2_L / n_i      (sampling noise of x_i)
--   tau2     = max(0, mean_i[(x_i - mu_L)^2 - v_i])   (true between-station spread)
--   B_i      = v_i / (v_i + tau2)  (shrinkage weight; 1 if tau2 = 0)
--   shrunk_i = (1 - B_i) * x_i + B_i * mu_L
-- Stations with few incidents have large v_i and are pulled most of the way
-- to their line's rate; stations with many incidents keep their own rate.
-- Rank 1 = most minutes lost per incident (least reliable).

CREATE OR REPLACE MACRO station_ranking_for(d_from, d_to) AS TABLE
WITH s AS (
    SELECT
        station_key,
        station_label,
        station_line_code                 AS line_code,
        count(*)                          AS incidents,
        sum(min_delay)                    AS delay_minutes,
        avg(min_delay)                    AS naive_minutes_per_incident,
        coalesce(var_samp(min_delay), 0)  AS within_variance
    FROM v_delay
    WHERE is_station AND date BETWEEN CAST(d_from AS DATE) AND CAST(d_to AS DATE)
    GROUP BY station_key, station_label, station_line_code
),
l AS (
    SELECT
        line_code,
        sum(delay_minutes) / sum(incidents)                                         AS line_minutes_per_incident,
        coalesce(sum((incidents - 1) * within_variance) / nullif(sum(incidents - 1), 0), 0) AS line_within_variance
    FROM s
    GROUP BY line_code
),
j AS (
    SELECT s.*, l.line_minutes_per_incident, l.line_within_variance,
           l.line_within_variance / s.incidents AS sampling_variance
    FROM s JOIN l USING (line_code)
),
t AS (
    SELECT greatest(avg(power(naive_minutes_per_incident - line_minutes_per_incident, 2) - sampling_variance), 0)
           AS between_variance
    FROM j
),
e AS (
    SELECT j.*, t.between_variance,
           CASE WHEN t.between_variance = 0 THEN 1.0
                ELSE sampling_variance / (sampling_variance + t.between_variance) END AS shrinkage_weight
    FROM j CROSS JOIN t
),
r AS (
    SELECT e.*,
           (1 - shrinkage_weight) * naive_minutes_per_incident
               + shrinkage_weight * line_minutes_per_incident AS shrunk_minutes_per_incident
    FROM e
)
SELECT
    station_key,
    station_label,
    line_code,
    incidents,
    delay_minutes,
    naive_minutes_per_incident,
    line_minutes_per_incident,
    within_variance,
    line_within_variance,
    between_variance,
    shrinkage_weight,
    shrunk_minutes_per_incident,
    row_number() OVER (ORDER BY incidents DESC, station_label)                    AS count_rank,
    row_number() OVER (ORDER BY naive_minutes_per_incident DESC, station_label)  AS naive_rank,
    row_number() OVER (ORDER BY shrunk_minutes_per_incident DESC, station_label) AS shrunk_rank,
    row_number() OVER (ORDER BY naive_minutes_per_incident DESC, station_label)
      - row_number() OVER (ORDER BY shrunk_minutes_per_incident DESC, station_label) AS rank_change
FROM r;

-- Whole period.
CREATE OR REPLACE VIEW station_ranking_all AS
SELECT * FROM station_ranking_for(
    (SELECT min(date) FROM dim_date),
    (SELECT max(date) FROM dim_date)
);

-- Most recent 36 months of data.
CREATE OR REPLACE VIEW station_ranking_recent AS
SELECT * FROM station_ranking_for(
    (SELECT max(month_start) - INTERVAL 35 MONTH FROM dim_date),
    (SELECT max(date) FROM dim_date)
);
