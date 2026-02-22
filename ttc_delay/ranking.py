"""Materialise the empirical-Bayes station ranking for several periods."""

from __future__ import annotations

import duckdb
import pandas as pd

PERIODS = {
    # period label -> months back from the last month with data (None = all)
    "All years": None,
    "Last 36 months": 36,
    "Last 12 months": 12,
}


def explain(row: pd.Series) -> str:
    """One plain-language sentence on why a station moved between rankings."""
    change = int(row["rank_change"])
    weight = float(row["shrinkage_weight"])
    n = int(row["incidents"])
    line_rate = float(row["line_minutes_per_incident"])
    shift = float(row["shrunk_minutes_per_incident"]) - float(row["naive_minutes_per_incident"])
    if abs(change) <= 2:
        return f"Stable: {n:,} incidents; estimate moved {weight:.0%} of the way to its line rate ({line_rate:.2f} min)."
    moved = f"Rose {change} places" if change > 0 else f"Dropped {-change} places"
    if weight >= 0.25:
        why = (f"only {n:,} incidents, so {weight:.0%} of its gap to the line rate ({line_rate:.2f} min) "
               f"is treated as noise")
    else:
        why = (f"well measured ({n:,} incidents, {weight:.0%} shrinkage), so it "
               f"{'overtook' if change > 0 else 'fell behind'} stations whose estimates moved more")
    return f"{moved}: shrinkage moved its rate {shift:+.2f} min; {why}."


def build_station_ranking(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    first, last, last_month = con.execute(
        "SELECT min(date), max(date), max(month_start) FROM dim_date"
    ).fetchone()
    frames = []
    for sort_order, (label, months) in enumerate(PERIODS.items(), start=1):
        start = first if months is None else (pd.Timestamp(last_month) - pd.DateOffset(months=months - 1)).date()
        start = max(pd.Timestamp(start).date(), pd.Timestamp(first).date())
        df = con.execute(
            "SELECT * FROM station_ranking_for(?, ?) ORDER BY shrunk_rank", [start, last]
        ).df()
        df.insert(0, "period", label)
        df.insert(1, "period_sort", sort_order)
        df.insert(2, "period_start", pd.Timestamp(start).date())
        df.insert(3, "period_end", pd.Timestamp(last).date())
        df["explanation"] = df.apply(explain, axis=1) if len(df) else []
        frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    con.register("ranking_staging", out)
    con.execute("CREATE OR REPLACE TABLE station_ranking AS SELECT * FROM ranking_staging")
    con.unregister("ranking_staging")
    return out
