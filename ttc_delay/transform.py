"""Turn the extracted rows into the star schema's tables."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .causes import build_dim_cause, load_code_lists, normalise_code
from .config import REFERENCE_DIR
from .lines import normalise_line
from .stations import SUBWAY_LINES, StationMatcher

DUPLICATE_KEY = ["date", "time", "station", "code", "min_delay", "min_gap", "bound", "line", "vehicle"]

LOCATION_LABELS = {
    "segment": "Between stations",
    "facility": "Yard, carhouse or other facility",
    "line_wide": "Line-wide / system",
    "unmatched": "Unmatched location",
}


@dataclass
class StarSchema:
    fact_delay: pd.DataFrame
    dim_date: pd.DataFrame
    dim_line: pd.DataFrame
    dim_station: pd.DataFrame
    dim_cause: pd.DataFrame
    source_counts: pd.DataFrame  # rows read per source year
    removed: pd.DataFrame  # rows removed per year and reason
    station_matches: pd.DataFrame  # one row per distinct (raw station, line)
    notes: dict = field(default_factory=dict)


def build_dim_date(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Contiguous calendar from 1 January of the first year to the last data date.

    Ending at the last date with data (rather than 31 December) makes
    year-over-year for a partial year compare like-for-like periods, both in
    the SQL KPIs and in Power BI's SAMEPERIODLASTYEAR.
    """
    dates = pd.date_range(f"{start.year}-01-01", end, freq="D")
    return pd.DataFrame(
        {
            "date_key": dates.strftime("%Y%m%d").astype(int),
            "date": dates.date,
            "year": dates.year,
            "quarter": dates.quarter,
            "month": dates.month,
            "month_name": dates.strftime("%b"),
            "month_start": dates.to_period("M").start_time.date,
            "year_month": dates.strftime("%Y-%m"),
            "day_of_week": dates.dayofweek + 1,
            "day_name": dates.strftime("%A"),
            "is_weekend": dates.dayofweek >= 5,
        }
    )


def build_dim_line(reference_dir: Path = REFERENCE_DIR) -> pd.DataFrame:
    df = pd.read_csv(reference_dir / "lines.csv", dtype={"line_number": "Int64"})
    df["is_subway_line"] = df["is_subway_line"].astype(str).str.lower() == "true"
    df.insert(0, "line_key", range(1, len(df) + 1))
    return df


def _line_display(line_code: str, dim_line: pd.DataFrame) -> str:
    row = dim_line.loc[dim_line["line_code"] == line_code]
    if row.empty or pd.isna(row["line_number"].iloc[0]):
        return {"MULTI": "multiple lines", "OTHER": "non-subway", "UNKNOWN": "line not recorded"}.get(line_code, line_code)
    return f"Line {int(row['line_number'].iloc[0])}"


def build_dim_station(matcher: StationMatcher, other_locations: list[tuple[str, str]], dim_line: pd.DataFrame) -> pd.DataFrame:
    ref = pd.read_csv(REFERENCE_DIR / "stations.csv", dtype=str, keep_default_na=False)
    rows = []
    for r in ref.itertuples(index=False):
        rows.append(
            {
                "station_code": r.station_code,
                "station_name": r.station_name,
                "station_label": f"{r.station_name} ({_line_display(r.line_code, dim_line)})",
                "line_code": r.line_code,
                "location_type": "station",
                "is_station": True,
                "opened": r.opened or None,
                "closed": r.closed or None,
            }
        )
    for location_type, line_code in sorted(set(other_locations)):
        name = LOCATION_LABELS[location_type]
        rows.append(
            {
                "station_code": f"{location_type.upper()}_{line_code}",
                "station_name": name,
                "station_label": f"{name} ({_line_display(line_code, dim_line)})",
                "line_code": line_code,
                "location_type": location_type,
                "is_station": False,
                "opened": None,
                "closed": None,
            }
        )
    df = pd.DataFrame(rows)
    df.insert(0, "station_key", range(1, len(df) + 1))
    df["opened"] = pd.to_datetime(df["opened"]).dt.date
    df["closed"] = pd.to_datetime(df["closed"]).dt.date
    return df


def match_stations(raw: pd.DataFrame, matcher: StationMatcher) -> pd.DataFrame:
    """Resolve each distinct (raw station, normalised line) pair once."""
    pairs = (
        raw.groupby(["station", "line_code"], dropna=False)
        .size()
        .reset_index(name="rows")
    )
    out = []
    for station, line_code, rows in pairs.itertuples(index=False):
        m = matcher.match(station, line_code)
        out.append(
            {
                "raw_station": station,
                "line_code": line_code,
                "rows": rows,
                "cleaned_name": m.cleaned,
                "line_hint": m.line_hint,
                "location_type": m.location_type,
                "station_code": m.station_code,
                "method": m.method,
                "fuzzy_target": m.fuzzy_target,
                "fuzzy_score": m.score,
            }
        )
    return pd.DataFrame(out)


def transform(raw: pd.DataFrame, raw_dir: Path, reference_dir: Path = REFERENCE_DIR) -> StarSchema:
    raw = raw.copy()
    raw["source_year"] = raw["date"].dt.year
    source_counts = (
        raw.assign(source_year=raw["source_year"].astype("Int64"))
        .groupby(["source_year"], dropna=False)
        .size()
        .reset_index(name="source_rows")
    )

    removed = []
    # 1. Rows that cannot be loaded: no date, or missing/negative minutes.
    invalid = raw["date"].isna() | raw["min_delay"].isna() | raw["min_gap"].isna()
    invalid |= (raw["min_delay"] < 0) | (raw["min_gap"] < 0)
    if invalid.any():
        removed.append(raw.loc[invalid].assign(reason="invalid date or minutes"))
    raw = raw.loc[~invalid]
    # 2. Exact duplicates (same incident pasted twice, often across sheets).
    dup = raw.duplicated(subset=DUPLICATE_KEY, keep="first")
    if dup.any():
        removed.append(raw.loc[dup].assign(reason="exact duplicate"))
    raw = raw.loc[~dup].reset_index(drop=True)
    removed_df = (
        pd.concat(removed).groupby(["source_year", "reason"], dropna=False).size().reset_index(name="rows")
        if removed
        else pd.DataFrame(columns=["source_year", "reason", "rows"])
    )

    raw["line_code"] = raw["line"].map(normalise_line)
    raw["cause_code"] = raw["code"].map(normalise_code)

    matcher = StationMatcher(reference_dir)
    matches = match_stations(raw, matcher)
    raw = raw.merge(
        matches[["raw_station", "line_code", "location_type", "station_code"]],
        left_on=["station", "line_code"],
        right_on=["raw_station", "line_code"],
        how="left",
    )
    station_line = {s.station_code: s.line_code for s in matcher.stations}
    # A missing or non-subway line label is filled from the matched station.
    fill = ~raw["line_code"].isin(SUBWAY_LINES + ("MULTI",)) & raw["station_code"].notna()
    raw.loc[fill, "line_code"] = raw.loc[fill, "station_code"].map(station_line)
    other = raw["location_type"] != "station"
    raw.loc[other, "station_code"] = raw.loc[other, "location_type"].str.upper() + "_" + raw.loc[other, "line_code"]

    dim_line = build_dim_line(reference_dir)
    dim_station = build_dim_station(
        matcher, list(zip(raw.loc[other, "location_type"], raw.loc[other, "line_code"])), dim_line
    )
    dim_cause = build_dim_cause(raw["cause_code"], load_code_lists(raw_dir))
    dim_date = build_dim_date(raw["date"].min(), raw["date"].max())

    raw = raw.sort_values(["date", "time", "source_file", "source_sheet", "source_row"], kind="stable").reset_index(drop=True)
    fact = pd.DataFrame(
        {
            "delay_id": range(1, len(raw) + 1),
            "date_key": raw["date"].dt.strftime("%Y%m%d").astype(int),
            "station_key": raw["station_code"].map(dim_station.set_index("station_code")["station_key"]),
            "line_key": raw["line_code"].map(dim_line.set_index("line_code")["line_key"]),
            "cause_key": raw["cause_code"].map(dim_cause.set_index("cause_code")["cause_key"]),
            "time_of_day": raw["time"],
            "hour": raw["time"].str.slice(0, 2).astype("Int64"),
            "min_delay": raw["min_delay"].astype(int),
            "min_gap": raw["min_gap"].astype(int),
            "bound": raw["bound"],
            "vehicle": raw["vehicle"].astype("Int64"),
            "raw_station": raw["station"],
            "raw_line": raw["line"],
            "source_file": raw["source_file"],
            "source_sheet": raw["source_sheet"],
            "source_row": raw["source_row"],
        }
    )
    return StarSchema(
        fact_delay=fact,
        dim_date=dim_date,
        dim_line=dim_line,
        dim_station=dim_station,
        dim_cause=dim_cause,
        source_counts=source_counts,
        removed=removed_df,
        station_matches=matches,
    )


def write_station_reports(schema: StarSchema, reports_dir: Path) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    m = schema.station_matches.sort_values(["rows", "raw_station"], ascending=[False, True])
    m.to_csv(reports_dir / "station_matching.csv", index=False, quoting=csv.QUOTE_MINIMAL)
    unmatched = (
        m.loc[m["location_type"] == "unmatched"]
        .groupby("cleaned_name", dropna=False)
        .agg(rows=("rows", "sum"), raw_examples=("raw_station", lambda s: " | ".join(sorted(set(map(str, s)))[:5])))
        .reset_index()
        .sort_values(["rows", "cleaned_name"], ascending=[False, True])
    )
    unmatched.to_csv(reports_dir / "station_unmatched.csv", index=False)
