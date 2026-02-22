"""End-to-end pipeline: raw files -> star schema -> checks -> KPIs -> exports."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb

from . import extract, quality, ranking, summary
from .config import EXPORT_DIR, RAW_DIR, REPORTS_DIR, WAREHOUSE_PATH
from .export import export_tables
from .transform import transform, write_station_reports
from .warehouse import load


@dataclass
class PipelineResult:
    con: duckdb.DuckDBPyConnection
    checks: list[quality.Check]

    @property
    def ok(self) -> bool:
        return all(c.status != "fail" for c in self.checks)


def run(
    raw_dir: Path = RAW_DIR,
    db_path: Path | str = WAREHOUSE_PATH,
    reports_dir: Path | None = REPORTS_DIR,
    export_dir: Path | None = EXPORT_DIR,
) -> PipelineResult:
    raw = extract.read_all(raw_dir)
    schema = transform(raw, raw_dir)
    con = load(schema, db_path)
    ranking.build_station_ranking(con)
    checks = quality.run_checks(con, raw_dir / "manifest.json")
    if reports_dir is not None:
        write_station_reports(schema, reports_dir)
        quality.write_report(checks, reports_dir, con)
        summary.write_summary(con, reports_dir)
    if export_dir is not None:
        export_tables(con, export_dir)
    return PipelineResult(con, checks)
