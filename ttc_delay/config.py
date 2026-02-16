"""Paths and source locations shared by the pipeline."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REFERENCE_DIR = ROOT / "reference"
SQL_DIR = ROOT / "sql"
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
SAMPLE_DIR = DATA_DIR / "sample"
WAREHOUSE_PATH = DATA_DIR / "warehouse" / "ttc_delay.duckdb"
EXPORT_DIR = DATA_DIR / "export"
REPORTS_DIR = ROOT / "reports"

CKAN_BASE = "https://ckan0.cf.opendata.inter.prod-toronto.ca"
CKAN_PACKAGE = "ttc-subway-delay-data"
