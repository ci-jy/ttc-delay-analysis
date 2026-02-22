"""Command line: ``python3 -m ttc_delay {download,run,all}``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import EXPORT_DIR, RAW_DIR, REPORTS_DIR, SAMPLE_DIR, WAREHOUSE_PATH


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
                       help=f"use the committed sample in {SAMPLE_DIR.relative_to(SAMPLE_DIR.parents[1])}")
        p.add_argument("--db", type=Path, default=WAREHOUSE_PATH)
        p.add_argument("--reports-dir", type=Path, default=REPORTS_DIR)
        p.add_argument("--export-dir", type=Path, default=EXPORT_DIR)
    args = parser.parse_args(argv)

    from . import download, pipeline

    if args.command in ("download", "all"):
        path = download.download_all(args.raw_dir, force=getattr(args, "force", False))
        print(f"downloaded files listed in {path}")
        if args.command == "download":
            return 0
    raw_dir = SAMPLE_DIR if args.sample else args.raw_dir
    result = pipeline.run(raw_dir, args.db, args.reports_dir, args.export_dir)
    for check in result.checks:
        print(f"[{check.status.upper():4}] {check.name}: {check.detail}")
    print(f"warehouse: {args.db}\nreports:   {args.reports_dir}\nexports:   {args.export_dir}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
