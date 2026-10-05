# ETL, warehouse and KPIs

## Download

`ttc_delay/download.py` queries the CKAN `package_show` endpoint for the package `ttc-subway-delay-data`. It keeps the yearly XLSX files, the CSV for 2025 onward and both cause-code lists, and records each datastore table's record count in `data/raw/manifest.json`.

## Reading the files

The reader handles workbooks with one sheet per month (sheet names change style every year), single-sheet workbooks and the datastore CSV (which adds an `_id` column and uses ISO dates). Dates arrive as Excel datetimes or strings, times as text or `datetime.time`. Every row keeps its source file, sheet and row number.

## Lines

`ttc_delay/lines.py` maps more than 100 raw spellings ("YU", "YUS", "B/D", "BD LINE 2", "YU / BD", "29 DUFFERIN", ...) to YU, BD, SRT, SHP, MULTI (logged against several lines), OTHER (a bus or streetcar route) or UNKNOWN. If the line is missing or not a subway line, it is taken from the matched station.

## Stations

`ttc_delay/stations.py` resolves a location in this order:

1. Cleaning: upper-case; remove punctuation, the word STATION and anything after it, truncations ("STATIO") and misspellings ("STATON", "STN"). A trailing line hint (BD/YUS/SHP/SRT) is kept to pick the platform at interchange stations.
2. Curated aliases: `reference/station_aliases.csv`, e.g. BLOOR to Bloor-Yonge (Line 1), YONGE BD to Bloor-Yonge (Line 2), DOWNSVIEW to Sheppard West, DUNDAS to TMU, EGLINTON WEST to Cedarvale.
3. Non-station locations: line-wide entries, segments between stations ("UNION STATION TO KING") and yards or carhouses.
4. Fuzzy matching: `difflib` with a ratio of at least 0.85, checked against `reference/station_fuzzy_review.csv`. Accepted matches are marked reviewed, rejected ones stay unmatched, and new suggestions are flagged unreviewed in the matching report.

`reference/stations.csv` has one row per station and line, so Kennedy (Line 2) and Kennedy (Line 3) are separate. On the real data, 93.2% of rows resolve to a station, 6.7% to a known non-station location and 0.10% (267 rows) are unmatched; those are listed in `reports/station_unmatched.csv`.

## Causes

`ttc_delay/causes.py`: the current code list wins and the legacy workbook (subway and SRT columns) fills retired codes. Codes in neither list are kept as "Undocumented code". Double-encoded text ("â€“") is repaired. The category comes from the code's first letter (E equipment, M miscellaneous and customer, P plant, S security, T transportation). This is an analytical grouping, not an official TTC one.

## Cleaning rules

- Rows without a valid date or with negative minutes would be removed; none were found in the real data.
- Exact duplicates on all source fields are removed (269 rows).
- Removed counts are kept by file, year and reason, so row counts reconcile with the source.

## Star schema (`sql/schema.sql`)

- `fact_delay`: one row per logged incident.
- `dim_date`: date, year, month, month start, ...; runs from 1 January 2014 to the last date with data.
- `dim_station`: a station or a location type (segment, yard, line-wide).
- `dim_line`: YU, BD, SRT, SHP, MULTI, OTHER, UNKNOWN.
- `dim_cause`: code, description, category, source of the description.
- `station_ranking`: period x station, exported for Power BI.

Foreign keys are declared, and the quality checks test for orphans independently. Because `dim_date` ends at the last date with data, year-over-year for a partial year compares the same calendar span, in SQL and in DAX (`SAMEPERIODLASTYEAR`).

## Data-quality checks

`ttc_delay/quality.py` writes `reports/data_quality.md`:

- row counts reconcile per year (source rows = loaded + removed)
- the 2025+ CSV matches the CKAN datastore record count
- no orphaned foreign keys
- minutes present and non-negative
- no duplicates remain
- dates fall inside each file's stated period
- at least 99% of rows have a resolved location
- cause codes have published descriptions
- delays over 600 minutes are listed for review (kept, not removed)
- every month has data

## KPI views (`sql/kpis.sql`)

- `kpi_month` (line x month, complete grid plus network `ALL`): incidents, delay incidents, delay and gap minutes, minutes per incident, MoM, same month last year and YoY, rolling 12 months.
- `kpi_year` (line x year): the same, with a like-for-like previous year.
- `kpi_cause` (line scope x year scope x cause, scopes include `ALL`): minutes, share, rank, cumulative share, `in_pareto_80`.
- `kpi_pareto` (line scope x year scope): causes with minutes, causes needed to reach 80%, their share of all causes.
- `kpi_category_year` (line x year x category): minutes and share.

Pareto rule: causes are ranked by minutes, ties broken by code. A cause counts toward the 80% if the causes ranked above it hold less than 80% of the minutes.

## SQL twins of the DAX measures

Each DAX measure carries an annotation such as `annotation SqlTwin = kpi_year.yoy_change_minutes, kpi_month.yoy_change_minutes`. The tests check each named column against hand-computed values, which keeps the SQL and DAX definitions in step. The measures include YoY (`SAMEPERIODLASTYEAR`), MoM (`DATEADD`), rolling 12 months (`DATESINPERIOD`) and a Pareto rank, cumulative share and "causes to 80%" using the same tie-break as the SQL.
