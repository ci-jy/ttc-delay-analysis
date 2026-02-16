"""Read every yearly delay file into one uniform table.

Formats handled:

* 2014-2016 and Jan-Apr 2017: one workbook, one sheet (``Incidents``).
* May 2017-2021: one workbook per period with one sheet per month, and sheet
  names that change style every year ("Jan18", "March '20", "June20", ...).
* 2022-2024: one workbook per year, one sheet.
* 2025 onward: a CSV export of the open-data datastore with an extra ``_id``
  column and ISO date strings.

Dates arrive as Excel datetimes or strings, times as "HH:MM" strings or
``datetime.time``; all are normalised here. Every source row is kept with its
file, sheet and row number so that row counts can be reconciled later.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pandas as pd

COLUMNS = ["date", "time", "day", "station", "code", "min_delay", "min_gap", "bound", "line", "vehicle"]

_COLUMN_ALIASES = {
    "date": "date",
    "time": "time",
    "day": "day",
    "station": "station",
    "code": "code",
    "mindelay": "min_delay",
    "delay": "min_delay",
    "mingap": "min_gap",
    "gap": "min_gap",
    "bound": "bound",
    "line": "line",
    "vehicle": "vehicle",
}


def is_delay_file(path: Path) -> bool:
    name = path.name.lower()
    if "readme" in name or "code" in name:
        return False
    return path.suffix.lower() in (".xlsx", ".csv") and "delay" in name


def delay_files(raw_dir: Path) -> list[Path]:
    return sorted(p for p in raw_dir.iterdir() if is_delay_file(p))


def _standardise_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename = {}
    for col in df.columns:
        key = re.sub(r"[^a-z]", "", str(col).lower())
        if key in _COLUMN_ALIASES:
            rename[col] = _COLUMN_ALIASES[key]
    df = df.rename(columns=rename)
    missing = [c for c in COLUMNS if c not in df.columns]
    for col in missing:
        df[col] = pd.NA
    return df[COLUMNS]


def _parse_time(value: object) -> str | None:
    if value is None or (isinstance(value, float) and value != value) or value is pd.NaT:
        return None
    if isinstance(value, (dt.time, dt.datetime, pd.Timestamp)):
        return f"{value.hour:02d}:{value.minute:02d}"
    m = re.match(r"^\s*(\d{1,2}):(\d{2})", str(value))
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2))
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


def read_file(path: Path) -> pd.DataFrame:
    """Read one source file (all sheets) into the uniform column layout."""
    if path.suffix.lower() == ".csv":
        sheets = {"": pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""], encoding="utf-8-sig")}
    else:
        sheets = pd.read_excel(path, sheet_name=None, dtype=object)
    frames = []
    for sheet, raw in sheets.items():
        raw = raw.dropna(how="all")
        df = _standardise_columns(raw)
        df = df.assign(source_file=path.name, source_sheet=str(sheet), source_row=range(1, len(df) + 1))
        frames.append(df)
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.normalize()
    out["time"] = out["time"].map(_parse_time)
    for col in ("min_delay", "min_gap", "vehicle"):
        out[col] = pd.to_numeric(out[col], errors="coerce")
    for col in ("day", "station", "code", "bound", "line"):
        out[col] = out[col].map(lambda v: None if v is None or (isinstance(v, float) and v != v) else str(v).strip() or None)
    return out


def read_all(raw_dir: Path) -> pd.DataFrame:
    files = delay_files(raw_dir)
    if not files:
        raise FileNotFoundError(f"no delay files found in {raw_dir}")
    return pd.concat([read_file(p) for p in files], ignore_index=True)
