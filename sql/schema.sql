-- Star schema for TTC subway delays.
-- Grain of fact_delay: one logged delay incident (one row of the source files
-- after exact duplicates are removed).

DROP VIEW IF EXISTS v_delay;
DROP TABLE IF EXISTS fact_delay;
DROP TABLE IF EXISTS dim_date;
DROP TABLE IF EXISTS dim_station;
DROP TABLE IF EXISTS dim_line;
DROP TABLE IF EXISTS dim_cause;

CREATE TABLE dim_date (
    date_key      INTEGER PRIMARY KEY,      -- yyyymmdd
    date          DATE NOT NULL UNIQUE,
    year          INTEGER NOT NULL,
    quarter       INTEGER NOT NULL,
    month         INTEGER NOT NULL,
    month_name    VARCHAR NOT NULL,
    month_start   DATE NOT NULL,
    year_month    VARCHAR NOT NULL,         -- 'YYYY-MM'
    day_of_week   INTEGER NOT NULL,         -- 1 = Monday
    day_name      VARCHAR NOT NULL,
    is_weekend    BOOLEAN NOT NULL
);

CREATE TABLE dim_line (
    line_key       INTEGER PRIMARY KEY,
    line_code      VARCHAR NOT NULL UNIQUE,
    line_number    INTEGER,
    line_name      VARCHAR NOT NULL,
    is_subway_line BOOLEAN NOT NULL,
    sort_order     INTEGER NOT NULL
);

CREATE TABLE dim_station (
    station_key    INTEGER PRIMARY KEY,
    station_code   VARCHAR NOT NULL UNIQUE,
    station_name   VARCHAR NOT NULL,
    station_label  VARCHAR NOT NULL,        -- name plus line, unique
    line_code      VARCHAR NOT NULL,
    location_type  VARCHAR NOT NULL,        -- station | segment | facility | line_wide | unmatched
    is_station     BOOLEAN NOT NULL,
    opened         DATE,
    closed         DATE
);

CREATE TABLE dim_cause (
    cause_key          INTEGER PRIMARY KEY,
    cause_code         VARCHAR NOT NULL UNIQUE,
    cause_description  VARCHAR NOT NULL,
    description_source VARCHAR NOT NULL,
    cause_category     VARCHAR NOT NULL,
    cause_mode         VARCHAR NOT NULL,
    cause_label        VARCHAR NOT NULL
);

CREATE TABLE fact_delay (
    delay_id      BIGINT PRIMARY KEY,
    date_key      INTEGER NOT NULL REFERENCES dim_date (date_key),
    station_key   INTEGER NOT NULL REFERENCES dim_station (station_key),
    line_key      INTEGER NOT NULL REFERENCES dim_line (line_key),
    cause_key     INTEGER NOT NULL REFERENCES dim_cause (cause_key),
    time_of_day   VARCHAR,                  -- 'HH:MM'
    hour          INTEGER,
    min_delay     INTEGER NOT NULL,
    min_gap       INTEGER NOT NULL,
    bound         VARCHAR,
    vehicle       INTEGER,
    raw_station   VARCHAR,
    raw_line      VARCHAR,
    source_file   VARCHAR NOT NULL,
    source_sheet  VARCHAR,
    source_row    INTEGER NOT NULL
);

-- Convenience view used by the KPI and ranking SQL.
CREATE VIEW v_delay AS
SELECT
    f.delay_id,
    d.date, d.year, d.month, d.month_start, d.year_month,
    l.line_code, l.is_subway_line,
    s.station_key, s.station_code, s.station_name, s.station_label,
    s.line_code AS station_line_code, s.location_type, s.is_station,
    c.cause_code, c.cause_description, c.cause_category, c.cause_label,
    f.hour, f.min_delay, f.min_gap
FROM fact_delay f
JOIN dim_date d USING (date_key)
JOIN dim_line l USING (line_key)
JOIN dim_station s USING (station_key)
JOIN dim_cause c USING (cause_key);
