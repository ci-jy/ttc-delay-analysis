"""Load the star schema into DuckDB and create the KPI and ranking views."""

from __future__ import annotations

from pathlib import Path

import duckdb

from .config import SQL_DIR
from .transform import StarSchema

SQL_FILES = ["schema.sql", "kpis.sql", "ranking.sql"]


def run_sql_file(con: duckdb.DuckDBPyConnection, path: Path) -> None:
    con.execute(path.read_text())


def load(schema: StarSchema, db_path: Path | str) -> duckdb.DuckDBPyConnection:
    """Create (or replace) the warehouse at ``db_path`` and return a connection."""
    if str(db_path) != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        if Path(db_path).exists():
            Path(db_path).unlink()
    con = duckdb.connect(str(db_path))
    run_sql_file(con, SQL_DIR / "schema.sql")
    for name in ("dim_date", "dim_line", "dim_station", "dim_cause", "fact_delay"):
        df = getattr(schema, name)
        con.register("staging", df)
        cols = ", ".join(df.columns)
        con.execute(f"INSERT INTO {name} ({cols}) SELECT {cols} FROM staging")
        con.unregister("staging")
    for name in ("source_counts", "removed", "station_matches"):
        df = getattr(schema, name)
        con.register("staging", df)
        con.execute(f"CREATE OR REPLACE TABLE etl_{name} AS SELECT * FROM staging")
        con.unregister("staging")
    for sql_file in SQL_FILES[1:]:
        run_sql_file(con, SQL_DIR / sql_file)
    return con
