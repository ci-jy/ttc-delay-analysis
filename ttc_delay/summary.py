"""Write the headline KPI tables (``reports/kpi_summary.md``) used by FINDINGS.md."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd


def _md(df: pd.DataFrame, floatfmt: dict[str, str] | None = None) -> str:
    floatfmt = floatfmt or {}
    cols = list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for row in df.itertuples(index=False):
        cells = []
        for col, val in zip(cols, row):
            if val is None or (isinstance(val, float) and pd.isna(val)):
                cells.append("")
            elif col in floatfmt:
                cells.append(format(val, floatfmt[col]))
            elif col in ("year", "rank") or col.endswith("_rank"):
                cells.append(str(int(val)) if isinstance(val, (int, float)) else str(val))
            elif isinstance(val, float):
                cells.append(f"{val:,.0f}" if float(val).is_integer() else f"{val:,.2f}")
            elif isinstance(val, int):
                cells.append(f"{val:,}")
            else:
                cells.append(str(val))
        out.append("| " + " | ".join(cells) + " |")
    return "\n".join(out)


def collect(con: duckdb.DuckDBPyConnection) -> dict[str, pd.DataFrame]:
    q = lambda sql: con.execute(sql).df()  # noqa: E731
    last_date = con.execute("SELECT max(date) FROM dim_date").fetchone()[0]
    last_full_year = con.execute("SELECT max(year) FROM dim_date").fetchone()[0]
    if pd.Timestamp(last_date).strftime("%m-%d") != "12-31":
        last_full_year -= 1
    t = {}
    t["network_by_year"] = q(
        """SELECT year, incidents, delay_incidents, delay_minutes, minutes_per_incident,
                  yoy_change_minutes, yoy_change_incidents
           FROM kpi_year WHERE line_code = 'ALL' ORDER BY year"""
    )
    t["line_by_year"] = q(
        """SELECT line_code, year, incidents, delay_minutes, minutes_per_incident, yoy_change_minutes
           FROM kpi_year WHERE line_code <> 'ALL' AND incidents > 0 ORDER BY line_code, year"""
    )
    t["top_causes_all_years"] = q(
        """SELECT minutes_rank AS rank, cause_code, cause_description, cause_category, incidents,
                  delay_minutes, share_of_minutes, cumulative_share
           FROM kpi_cause WHERE line_scope = 'ALL' AND year_scope = 'ALL' AND minutes_rank <= 10
           ORDER BY minutes_rank"""
    )
    t["top_causes_last_full_year"] = q(
        f"""SELECT minutes_rank AS rank, cause_code, cause_description, incidents,
                   delay_minutes, share_of_minutes, cumulative_share
            FROM kpi_cause WHERE line_scope = 'ALL' AND year_scope = '{last_full_year}' AND minutes_rank <= 10
            ORDER BY minutes_rank"""
    )
    t["pareto_network_by_year"] = q(
        """SELECT year_scope AS year, delay_minutes, causes_with_minutes, causes_to_80pct,
                  share_of_causes_to_80pct, top_cause_share
           FROM kpi_pareto WHERE line_scope = 'ALL' ORDER BY year_scope"""
    )
    t["pareto_by_line_all_years"] = q(
        """SELECT line_scope AS line, delay_minutes, causes_with_minutes, causes_to_80pct,
                  share_of_causes_to_80pct, top_cause_share
           FROM kpi_pareto WHERE year_scope = 'ALL' AND line_scope IN ('ALL', 'YU', 'BD', 'SHP', 'SRT')
           ORDER BY delay_minutes DESC"""
    )
    t["category_share_by_year"] = q(
        """SELECT year, cause_category, sum(delay_minutes) AS delay_minutes,
                  sum(delay_minutes) / sum(sum(delay_minutes)) OVER (PARTITION BY year) AS share_of_minutes
           FROM kpi_category_year WHERE line_code = 'ALL' GROUP BY year, cause_category ORDER BY year, delay_minutes DESC"""
    )
    for period in ("All years", "Last 36 months", "Last 12 months"):
        key = period.lower().replace(" ", "_")
        t[f"ranking_{key}_top15"] = q(
            f"""SELECT shrunk_rank, naive_rank, count_rank, station_label, incidents,
                       naive_minutes_per_incident, line_minutes_per_incident, shrinkage_weight,
                       shrunk_minutes_per_incident, explanation
                FROM station_ranking WHERE period = '{period}' ORDER BY shrunk_rank LIMIT 15"""
        )
        t[f"ranking_{key}_movers"] = q(
            f"""SELECT station_label, incidents, naive_rank, shrunk_rank, rank_change, shrinkage_weight, explanation
                FROM station_ranking WHERE period = '{period}' AND abs(rank_change) >= 3
                ORDER BY abs(rank_change) DESC, station_label LIMIT 12"""
        )
    t["ranking_periods"] = q(
        """SELECT period, min(period_start) AS period_start, min(period_end) AS period_end,
                  count(*) AS stations, min(incidents) AS min_incidents, max(incidents) AS max_incidents,
                  max(between_variance) AS between_variance,
                  avg(abs(rank_change)) AS mean_abs_rank_change, max(abs(rank_change)) AS max_abs_rank_change,
                  corr(naive_rank, count_rank) AS corr_naive_vs_count_rank
           FROM station_ranking GROUP BY period, period_sort ORDER BY period_sort"""
    )
    t["meta"] = pd.DataFrame(
        [{"first_date": str(con.execute("SELECT min(date) FROM dim_date").fetchone()[0]),
          "last_date": str(last_date), "last_full_year": int(last_full_year),
          "incidents": con.execute("SELECT count(*) FROM fact_delay").fetchone()[0],
          "delay_minutes": con.execute("SELECT sum(min_delay) FROM fact_delay").fetchone()[0]}]
    )
    return t


PCT = {"share_of_minutes": ".1%", "cumulative_share": ".1%", "yoy_change_minutes": "+.1%",
       "yoy_change_incidents": "+.1%", "share_of_causes_to_80pct": ".1%", "top_cause_share": ".1%",
       "shrinkage_weight": ".0%", "minutes_per_incident": ".2f", "naive_minutes_per_incident": ".2f",
       "line_minutes_per_incident": ".2f", "shrunk_minutes_per_incident": ".2f",
       "between_variance": ".3f", "mean_abs_rank_change": ".1f", "corr_naive_vs_count_rank": ".2f"}


def write_summary(con: duckdb.DuckDBPyConnection, reports_dir: Path) -> Path:
    tables = collect(con)
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "kpi_summary.json").write_text(
        json.dumps({k: v.to_dict(orient="records") for k, v in tables.items()}, indent=1, default=str)
    )
    parts = ["# KPI summary", "", "Headline tables produced by the pipeline from the warehouse views.", ""]
    for name, df in tables.items():
        parts += [f"## {name.replace('_', ' ')}", "", _md(df, PCT), ""]
    path = reports_dir / "kpi_summary.md"
    path.write_text("\n".join(parts))
    return path
