"""Command line: ``python3 -m ttc_delay {download,run,all}``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import DATA_DIR, EXPORT_DIR, RAW_DIR, REPORTS_DIR, ROOT, SAMPLE_DIR, WAREHOUSE_PATH

# Sample runs write next to each other so they never overwrite real-data outputs.
SAMPLE_BUILD = DATA_DIR / "sample_build"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ttc_delay", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    dl = sub.add_parser("download", help="download the source files from Toronto Open Data")
    dl.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    dl.add_argument("--force", action="store_true", help="re-download files that already exist")
    for name, help_text in (("run", "build the warehouse, checks, KPIs and exports"),
                            ("all", "download, then run")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--raw-dir", type=Path, default=RAW_DIR)
        p.add_argument("--sample", action="store_true",
                       help=f"use the committed sample in {SAMPLE_DIR.relative_to(ROOT)}; "
                            f"outputs go to {SAMPLE_BUILD.relative_to(ROOT)}")
        p.add_argument("--db", type=Path, help=f"DuckDB file (default {WAREHOUSE_PATH.relative_to(ROOT)})")
        p.add_argument("--reports-dir", type=Path, help=f"default {REPORTS_DIR.relative_to(ROOT)}")
        p.add_argument("--export-dir", type=Path, help=f"Power BI CSV exports (default {EXPORT_DIR.relative_to(ROOT)})")
    args = parser.parse_args(argv)

    from . import download, pipeline

    if args.command in ("download", "all"):
        path = download.download_all(args.raw_dir, force=getattr(args, "force", False))
        print(f"downloaded files listed in {path}")
        if args.command == "download":
            return 0
    if args.sample:
        raw_dir = SAMPLE_DIR
        args.db = args.db or SAMPLE_BUILD / "ttc_delay.duckdb"
        args.reports_dir = args.reports_dir or SAMPLE_BUILD / "reports"
        args.export_dir = args.export_dir or SAMPLE_BUILD / "export"
    else:
        raw_dir = args.raw_dir
        args.db = args.db or WAREHOUSE_PATH
        args.reports_dir = args.reports_dir or REPORTS_DIR
        args.export_dir = args.export_dir or EXPORT_DIR
    result = pipeline.run(raw_dir, args.db, args.reports_dir, args.export_dir)
    for check in result.checks:
        print(f"[{check.status.upper():4}] {check.name}: {check.detail}")
    print(f"warehouse: {args.db}\nreports:   {args.reports_dir}\nexports:   {args.export_dir}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
