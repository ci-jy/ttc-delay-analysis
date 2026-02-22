"""Export the star schema for the Power BI semantic model (CSV, UTF-8)."""

from __future__ import annotations

from pathlib import Path

import duckdb

EXPORTS = {
    "fact_delay": "SELECT delay_id, date_key, station_key, line_key, cause_key, time_of_day, hour, "
                  "min_delay, min_gap, bound FROM fact_delay ORDER BY delay_id",
    "dim_date": "SELECT * FROM dim_date ORDER BY date_key",
    "dim_line": "SELECT * FROM dim_line ORDER BY line_key",
    "dim_station": "SELECT * FROM dim_station ORDER BY station_key",
    "dim_cause": "SELECT * FROM dim_cause ORDER BY cause_key",
    "station_ranking": "SELECT * FROM station_ranking ORDER BY period_sort, shrunk_rank",
}


def export_tables(con: duckdb.DuckDBPyConnection, export_dir: Path) -> list[Path]:
    export_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, query in EXPORTS.items():
        path = export_dir / f"{name}.csv"
        con.execute(f"COPY ({query}) TO '{path.as_posix()}' (HEADER, DELIMITER ',')")
        paths.append(path)
    return paths
