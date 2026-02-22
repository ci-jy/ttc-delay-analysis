"""Data-quality checks on the loaded warehouse, written to a report."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import duckdb

FOREIGN_KEYS = [
    ("date_key", "dim_date"),
    ("station_key", "dim_station"),
    ("line_key", "dim_line"),
    ("cause_key", "dim_cause"),
]
EXTREME_DELAY_MINUTES = 600
MAX_UNMATCHED_SHARE = 0.01


@dataclass
class Check:
    name: str
    status: str  # pass | warn | fail
    detail: str
    data: list | dict = field(default_factory=list)


def _rows(con, sql: str, params=None) -> list[dict]:
    cur = con.execute(sql, params or [])
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def expected_period(file_name: str) -> tuple[int, int] | None:
    """Calendar years a source file should cover, read from its name."""
    years = [int(y) for y in re.findall(r"(20\d\d)", file_name)]
    if not years:
        return None
    if "since" in file_name.lower():
        return years[0], 9999
    return min(years), max(years)


def check_row_counts(con) -> Check:
    rows = _rows(
        con,
        """
        WITH src AS (SELECT source_year AS year, sum(source_rows) AS source_rows FROM etl_source_counts GROUP BY 1),
             rem AS (SELECT source_year AS year, sum(rows) AS removed_rows FROM etl_removed GROUP BY 1),
             fct AS (SELECT d.year, count(*) AS loaded_rows FROM fact_delay f JOIN dim_date d USING (date_key) GROUP BY 1)
        SELECT src.year, src.source_rows, coalesce(rem.removed_rows, 0) AS removed_rows,
               coalesce(fct.loaded_rows, 0) AS loaded_rows
        FROM src LEFT JOIN rem USING (year) LEFT JOIN fct USING (year)
        ORDER BY src.year NULLS LAST
        """,
    )
    bad = [r for r in rows if r["source_rows"] != r["loaded_rows"] + r["removed_rows"]]
    status = "fail" if bad else "pass"
    total_src = sum(r["source_rows"] for r in rows)
    total_loaded = sum(r["loaded_rows"] for r in rows)
    detail = (
        f"{total_src:,} source rows = {total_loaded:,} loaded + "
        f"{total_src - total_loaded:,} removed; {len(bad)} year(s) do not reconcile"
    )
    return Check("Row counts per year reconcile with the source files", status, detail, rows)


def check_datastore_counts(con, manifest_path: Path | None) -> Check | None:
    if not manifest_path or not manifest_path.exists():
        return None
    manifest = json.loads(manifest_path.read_text())
    counts = manifest.get("datastore_row_counts", {})
    results = []
    for file in manifest.get("files", []):
        if not file["file"].lower().endswith(".csv") or "delay" not in file["file"].lower():
            continue
        expected = counts.get(file["resource_name"].removesuffix(".csv"))
        if expected is None:
            continue
        read = con.execute(
            "SELECT coalesce(sum(source_rows), 0) FROM etl_source_counts WHERE source_file = ?", [file["file"]]
        ).fetchone()[0]
        results.append({"file": file["file"], "rows_read": int(read), "datastore_rows": int(expected)})
    if not results:
        return None
    bad = [r for r in results if r["rows_read"] != r["datastore_rows"]]
    detail = "; ".join(f"{r['file']}: read {r['rows_read']:,}, CKAN datastore reports {r['datastore_rows']:,}" for r in results)
    return Check("CSV rows match the CKAN datastore record count", "fail" if bad else "pass", detail, results)


def check_orphans(con) -> Check:
    data = {}
    for column, dim in FOREIGN_KEYS:
        data[column] = con.execute(
            f"SELECT count(*) FROM fact_delay f LEFT JOIN {dim} d USING ({column}) WHERE d.{column} IS NULL"
        ).fetchone()[0]
    total = sum(data.values())
    return Check("No orphan foreign keys in fact_delay", "fail" if total else "pass",
                 f"{total} fact rows with a key missing from its dimension", data)


def check_minutes(con) -> Check:
    bad = con.execute(
        "SELECT count(*) FROM fact_delay WHERE min_delay IS NULL OR min_gap IS NULL OR min_delay < 0 OR min_gap < 0"
    ).fetchone()[0]
    return Check("Delay and gap minutes are present and non-negative", "fail" if bad else "pass",
                 f"{bad} rows with null or negative minutes")


def check_duplicates(con) -> Check:
    remaining = con.execute(
        """
        SELECT coalesce(sum(n - 1), 0) FROM (
            SELECT count(*) AS n FROM fact_delay
            GROUP BY date_key, time_of_day, raw_station, cause_key, min_delay, min_gap, bound, raw_line, vehicle
            HAVING count(*) > 1)
        """
    ).fetchone()[0]
    removed = con.execute(
        "SELECT coalesce(sum(rows), 0) FROM etl_removed WHERE reason = 'exact duplicate'"
    ).fetchone()[0]
    return Check("Exact duplicates removed", "fail" if remaining else "pass",
                 f"{removed:,} exact duplicate rows removed; {remaining} remain",
                 {"removed": int(removed), "remaining": int(remaining)})


def check_file_periods(con) -> Check:
    rows = _rows(con, "SELECT source_file, source_year, source_rows FROM etl_source_counts ORDER BY 1, 2")
    outside = []
    for r in rows:
        period = expected_period(r["source_file"])
        if period and r["source_year"] is not None and not (period[0] <= r["source_year"] <= period[1]):
            outside.append(r)
    n = sum(r["source_rows"] for r in outside)
    return Check("Dates fall inside each file's stated period", "warn" if outside else "pass",
                 f"{n} rows dated outside their file's period", outside)


def check_station_matching(con) -> Check:
    rows = _rows(
        con,
        """
        SELECT s.location_type, count(*) AS rows
        FROM fact_delay f JOIN dim_station s USING (station_key)
        GROUP BY 1 ORDER BY 2 DESC
        """,
    )
    total = sum(r["rows"] for r in rows) or 1
    unmatched = sum(r["rows"] for r in rows if r["location_type"] == "unmatched")
    share = unmatched / total
    status = "warn" if share > MAX_UNMATCHED_SHARE else "pass"
    detail = f"{unmatched:,} rows ({share:.2%}) have a location that could not be matched; see station_unmatched.csv"
    return Check("Station names resolved", status, detail, rows)


def check_causes(con) -> Check:
    rows = _rows(
        con,
        """
        SELECT c.description_source, count(*) AS rows, count(DISTINCT c.cause_code) AS codes
        FROM fact_delay f JOIN dim_cause c USING (cause_key)
        GROUP BY 1 ORDER BY 2 DESC
        """,
    )
    total = sum(r["rows"] for r in rows) or 1
    undocumented = sum(r["rows"] for r in rows if r["description_source"] in ("undocumented", "not recorded"))
    return Check("Cause codes have a published description", "warn" if undocumented / total > 0.02 else "pass",
                 f"{undocumented:,} rows ({undocumented / total:.2%}) carry a code missing from both code lists", rows)


def check_extremes(con) -> Check:
    rows = _rows(
        con,
        f"""
        SELECT d.date, f.time_of_day, f.raw_station, c.cause_code, f.min_delay, f.min_gap
        FROM fact_delay f JOIN dim_date d USING (date_key) JOIN dim_cause c USING (cause_key)
        WHERE f.min_delay > {EXTREME_DELAY_MINUTES} ORDER BY f.min_delay DESC
        """,
    )
    for r in rows:
        r["date"] = str(r["date"])
    return Check(f"Delays over {EXTREME_DELAY_MINUTES} minutes (kept, listed for review)",
                 "warn" if rows else "pass", f"{len(rows)} incidents", rows)


def check_month_coverage(con) -> Check:
    rows = _rows(
        con,
        """
        SELECT m.month_start FROM (SELECT DISTINCT month_start FROM dim_date) m
        LEFT JOIN (SELECT DISTINCT d.month_start FROM fact_delay f JOIN dim_date d USING (date_key)) x USING (month_start)
        WHERE x.month_start IS NULL ORDER BY 1
        """,
    )
    months = [str(r["month_start"])[:7] for r in rows]
    return Check("Every month in the date range has incidents", "warn" if months else "pass",
                 f"{len(months)} month(s) without data" + (f": {', '.join(months)}" if months else ""), months)


def run_checks(con: duckdb.DuckDBPyConnection, manifest_path: Path | None = None) -> list[Check]:
    checks = [
        check_row_counts(con),
        check_datastore_counts(con, manifest_path),
        check_orphans(con),
        check_minutes(con),
        check_duplicates(con),
        check_file_periods(con),
        check_station_matching(con),
        check_causes(con),
        check_extremes(con),
        check_month_coverage(con),
    ]
    return [c for c in checks if c is not None]


def write_report(checks: list[Check], reports_dir: Path, con: duckdb.DuckDBPyConnection) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "data_quality.json").write_text(json.dumps([asdict(c) for c in checks], indent=2, default=str))
    first, last = con.execute("SELECT min(date), max(date) FROM dim_date").fetchone()
    lines = [
        "# Data-quality report",
        "",
        f"Coverage: {first} to {last}. Generated by `python3 -m ttc_delay run`.",
        "",
        "| Check | Status | Result |",
        "|---|---|---|",
    ]
    for c in checks:
        lines.append(f"| {c.name} | {c.status.upper()} | {c.detail} |")
    rec = next(c for c in checks if c.name.startswith("Row counts"))
    lines += ["", "## Row counts per year", "", "| Year | Source rows | Removed | Loaded |", "|---|---:|---:|---:|"]
    for r in rec.data:
        lines.append(f"| {r['year']} | {r['source_rows']:,} | {r['removed_rows']:,} | {r['loaded_rows']:,} |")
    st = next(c for c in checks if c.name.startswith("Station names"))
    lines += ["", "## Incident locations", "", "| Location type | Rows |", "|---|---:|"]
    lines += [f"| {r['location_type']} | {r['rows']:,} |" for r in st.data]
    ex = next(c for c in checks if c.name.startswith("Delays over"))
    if ex.data:
        lines += ["", f"## Delays over {EXTREME_DELAY_MINUTES} minutes", "",
                  "| Date | Time | Station (raw) | Code | Min delay | Min gap |", "|---|---|---|---|---:|---:|"]
        lines += [f"| {r['date']} | {r['time_of_day']} | {r['raw_station']} | {r['cause_code']} | {r['min_delay']} | {r['min_gap']} |"
                  for r in ex.data]
    path = reports_dir / "data_quality.md"
    path.write_text("\n".join(lines) + "\n")
    return path
