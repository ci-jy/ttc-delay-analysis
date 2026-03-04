"""Generate the Power BI project (PBIP) under powerbi/ from one spec.

The semantic model is written as TMDL and the report as PBIR JSON. The files
are committed; rerun this script after changing a table, measure or visual:

    python3 tools/build_pbip.py

``tools/check_pbip.py`` validates the generated files.
"""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PBIP_DIR = ROOT / "powerbi"
NAME = "TTCDelay"
MODEL_DIR = PBIP_DIR / f"{NAME}.SemanticModel"
REPORT_DIR = PBIP_DIR / f"{NAME}.Report"
NS = uuid.UUID("6c1b1b1e-7d55-4c2e-9a53-1f0de1a7c0de")
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric"
DEFAULT_DATA_FOLDER = r"C:\ttc-delay-analysis\data\export"


def tag(*parts: str) -> str:
    """Stable lineage tag so regenerated files do not churn."""
    return str(uuid.uuid5(NS, "/".join(parts)))


# ---------------------------------------------------------------------------
# Tables: (column, TMDL dataType, M type, options)
# ---------------------------------------------------------------------------
I, S, D, B, F = "int64", "string", "dateTime", "boolean", "double"
M_TYPE = {I: "Int64.Type", S: "type text", D: "type date", B: "type logical", F: "type number"}

TABLES: dict[str, dict] = {
    "fact_delay": {
        "description": "One row per logged subway delay incident (duplicates removed).",
        "columns": [
            ("delay_id", I, {"hidden": True}),
            ("date_key", I, {"hidden": True}),
            ("station_key", I, {"hidden": True}),
            ("line_key", I, {"hidden": True}),
            ("cause_key", I, {"hidden": True}),
            ("time_of_day", S, {}),
            ("hour", I, {}),
            ("min_delay", I, {"summarize": "sum", "format": "#,0"}),
            ("min_gap", I, {"summarize": "sum", "format": "#,0"}),
            ("bound", S, {}),
        ],
    },
    "dim_date": {
        "description": "Calendar from 1 January of the first year to the last date with data.",
        "date_table": True,
        "columns": [
            ("date_key", I, {"hidden": True}),
            ("date", D, {"key": True, "format": "yyyy-mm-dd"}),
            ("year", I, {"format": "0"}),
            ("quarter", I, {}),
            ("month", I, {"hidden": True}),
            ("month_name", S, {"sort_by": "month"}),
            ("month_start", D, {"format": "mmm yyyy"}),
            ("year_month", S, {}),
            ("day_of_week", I, {"hidden": True}),
            ("day_name", S, {"sort_by": "day_of_week"}),
            ("is_weekend", B, {}),
        ],
    },
    "dim_line": {
        "description": "Subway lines plus buckets for incidents logged against several lines or none.",
        "columns": [
            ("line_key", I, {"hidden": True}),
            ("line_code", S, {}),
            ("line_number", I, {}),
            ("line_name", S, {"sort_by": "sort_order"}),
            ("is_subway_line", B, {}),
            ("sort_order", I, {"hidden": True}),
        ],
    },
    "dim_station": {
        "description": "Canonical stations (one row per station and line) and non-station locations.",
        "columns": [
            ("station_key", I, {"hidden": True}),
            ("station_code", S, {}),
            ("station_name", S, {}),
            ("station_label", S, {}),
            ("line_code", S, {}),
            ("location_type", S, {}),
            ("is_station", B, {}),
            ("opened", D, {"format": "yyyy-mm-dd"}),
            ("closed", D, {"format": "yyyy-mm-dd"}),
        ],
    },
    "dim_cause": {
        "description": "Delay codes with published descriptions and a category from the code prefix.",
        "columns": [
            ("cause_key", I, {"hidden": True}),
            ("cause_code", S, {}),
            ("cause_description", S, {}),
            ("description_source", S, {}),
            ("cause_category", S, {}),
            ("cause_mode", S, {}),
            ("cause_label", S, {}),
        ],
    },
    "station_ranking": {
        "description": "Empirical-Bayes station ranking for three periods (see sql/ranking.sql).",
        "columns": [
            ("period", S, {"sort_by": "period_sort"}),
            ("period_sort", I, {"hidden": True}),
            ("period_start", D, {"format": "yyyy-mm-dd"}),
            ("period_end", D, {"format": "yyyy-mm-dd"}),
            ("station_key", I, {"hidden": True}),
            ("station_label", S, {}),
            ("line_code", S, {}),
            ("incidents", I, {"summarize": "sum", "format": "#,0"}),
            ("delay_minutes", F, {"summarize": "sum", "format": "#,0"}),
            ("naive_minutes_per_incident", F, {"format": "0.00"}),
            ("line_minutes_per_incident", F, {"format": "0.00"}),
            ("within_variance", F, {"format": "0.00"}),
            ("line_within_variance", F, {"format": "0.00"}),
            ("between_variance", F, {"format": "0.000"}),
            ("shrinkage_weight", F, {"format": "0%"}),
            ("shrunk_minutes_per_incident", F, {"format": "0.00"}),
            ("count_rank", I, {}),
            ("naive_rank", I, {}),
            ("shrunk_rank", I, {}),
            ("rank_change", I, {}),
            ("explanation", S, {}),
        ],
    },
}

RELATIONSHIPS = [
    ("fact_delay", "date_key", "dim_date", "date_key"),
    ("fact_delay", "station_key", "dim_station", "station_key"),
    ("fact_delay", "line_key", "dim_line", "line_key"),
    ("fact_delay", "cause_key", "dim_cause", "cause_key"),
    ("station_ranking", "station_key", "dim_station", "station_key"),
]

# ---------------------------------------------------------------------------
# Measures: (table, name, DAX, format, folder, SQL twins, description)
# ---------------------------------------------------------------------------
MEASURES = [
    ("fact_delay", "Incidents", "COUNTROWS ( fact_delay )", "#,0", "Volume",
     ["kpi_year.incidents", "kpi_month.incidents"], "Logged delay incidents."),
    ("fact_delay", "Delay Incidents", "CALCULATE ( COUNTROWS ( fact_delay ), fact_delay[min_delay] > 0 )", "#,0", "Volume",
     ["kpi_year.delay_incidents"], "Incidents that delayed a train by at least one minute."),
    ("fact_delay", "Delay Minutes", "SUM ( fact_delay[min_delay] )", "#,0", "Volume",
     ["kpi_year.delay_minutes", "kpi_month.delay_minutes"], "Minutes of delay to the train (Min Delay)."),
    ("fact_delay", "Gap Minutes", "SUM ( fact_delay[min_gap] )", "#,0", "Volume",
     ["kpi_year.gap_minutes"], "Minutes of gap to the following train (Min Gap)."),
    ("fact_delay", "Minutes per Incident", "DIVIDE ( [Delay Minutes], [Incidents] )", "0.00", "Volume",
     ["kpi_year.minutes_per_incident"], "Average delay minutes per logged incident."),
    ("fact_delay", "Delay Minutes PM",
     "CALCULATE ( [Delay Minutes], DATEADD ( dim_date[date], -1, MONTH ) )", "#,0", "Time comparison",
     ["kpi_month.prev_month_minutes"], "Delay minutes in the previous month."),
    ("fact_delay", "Delay Minutes MoM %",
     "VAR prev = [Delay Minutes PM]\nRETURN\n    DIVIDE ( [Delay Minutes] - prev, prev )", "+0.0%;-0.0%;0.0%", "Time comparison",
     ["kpi_month.mom_change_minutes"], "Month-over-month change in delay minutes."),
    ("fact_delay", "Incidents MoM %",
     "VAR prev = CALCULATE ( [Incidents], DATEADD ( dim_date[date], -1, MONTH ) )\nRETURN\n    DIVIDE ( [Incidents] - prev, prev )",
     "+0.0%;-0.0%;0.0%", "Time comparison", ["kpi_month.mom_change_incidents"], "Month-over-month change in incidents."),
    ("fact_delay", "Delay Minutes PY",
     "CALCULATE ( [Delay Minutes], SAMEPERIODLASTYEAR ( dim_date[date] ) )", "#,0", "Time comparison",
     ["kpi_year.prev_year_minutes"], "Delay minutes in the same period one year earlier."),
    ("fact_delay", "Delay Minutes YoY %",
     "VAR py = [Delay Minutes PY]\nRETURN\n    DIVIDE ( [Delay Minutes] - py, py )", "+0.0%;-0.0%;0.0%", "Time comparison",
     ["kpi_year.yoy_change_minutes", "kpi_month.yoy_change_minutes"], "Year-over-year change in delay minutes."),
    ("fact_delay", "Incidents PY",
     "CALCULATE ( [Incidents], SAMEPERIODLASTYEAR ( dim_date[date] ) )", "#,0", "Time comparison",
     ["kpi_year.prev_year_incidents"], "Incidents in the same period one year earlier."),
    ("fact_delay", "Incidents YoY %",
     "VAR py = [Incidents PY]\nRETURN\n    DIVIDE ( [Incidents] - py, py )", "+0.0%;-0.0%;0.0%", "Time comparison",
     ["kpi_year.yoy_change_incidents"], "Year-over-year change in incidents."),
    ("fact_delay", "Delay Minutes R12M",
     "CALCULATE (\n    [Delay Minutes],\n    DATESINPERIOD ( dim_date[date], MAX ( dim_date[date] ), -12, MONTH )\n)",
     "#,0", "Time comparison", ["kpi_month.rolling_12m_minutes"], "Delay minutes in the 12 months ending with the current period."),
    ("fact_delay", "Incidents R12M",
     "CALCULATE (\n    [Incidents],\n    DATESINPERIOD ( dim_date[date], MAX ( dim_date[date] ), -12, MONTH )\n)",
     "#,0", "Time comparison", ["kpi_month.rolling_12m_incidents"], "Incidents in the 12 months ending with the current period."),
    ("fact_delay", "Share of Minutes",
     "DIVIDE ( [Delay Minutes], CALCULATE ( [Delay Minutes], ALL ( dim_cause ) ) )", "0.0%", "Causes",
     ["kpi_cause.share_of_minutes"], "Share of the delay minutes in the current line/year scope."),
    ("fact_delay", "Cause Rank",
     "VAR c = SELECTEDVALUE ( dim_cause[cause_code] )\n"
     "VAR m = [Delay Minutes]\n"
     "VAR causes =\n"
     "    FILTER (\n"
     "        ADDCOLUMNS ( ALLSELECTED ( dim_cause ), \"@m\", [Delay Minutes], \"@n\", [Incidents] ),\n"
     "        NOT ISBLANK ( [@n] )\n"
     "    )\n"
     "RETURN\n"
     "    IF (\n"
     "        NOT ISBLANK ( c ) && NOT ISBLANK ( [Incidents] ),\n"
     "        COUNTROWS ( FILTER ( causes, [@m] > m || ( [@m] = m && dim_cause[cause_code] < c ) ) ) + 1\n"
     "    )",
     "0", "Causes", ["kpi_cause.minutes_rank"], "Rank of the cause by delay minutes (ties broken by code)."),
    ("fact_delay", "Cumulative Cause Share",
     "VAR c = SELECTEDVALUE ( dim_cause[cause_code] )\n"
     "VAR m = [Delay Minutes]\n"
     "VAR causes = ADDCOLUMNS ( ALLSELECTED ( dim_cause ), \"@m\", [Delay Minutes] )\n"
     "VAR total = SUMX ( causes, [@m] )\n"
     "VAR cumulative =\n"
     "    SUMX ( FILTER ( causes, [@m] > m || ( [@m] = m && dim_cause[cause_code] <= c ) ), [@m] )\n"
     "RETURN\n"
     "    IF ( NOT ISBLANK ( c ), DIVIDE ( cumulative, total ) )",
     "0.0%", "Causes", ["kpi_cause.cumulative_share"], "Pareto line: share of minutes from this cause and all causes ranked above it."),
    ("fact_delay", "Causes to 80%",
     "VAR causes =\n"
     "    FILTER ( ADDCOLUMNS ( VALUES ( dim_cause[cause_code] ), \"@m\", [Delay Minutes] ), [@m] > 0 )\n"
     "VAR total = SUMX ( causes, [@m] )\n"
     "RETURN\n"
     "    COUNTROWS (\n"
     "        FILTER (\n"
     "            causes,\n"
     "            VAR m = [@m]\n"
     "            VAR c = dim_cause[cause_code]\n"
     "            VAR above =\n"
     "                SUMX ( FILTER ( causes, [@m] > m || ( [@m] = m && dim_cause[cause_code] < c ) ), [@m] )\n"
     "            RETURN\n"
     "                DIVIDE ( above, total ) < 0.8\n"
     "        )\n"
     "    )",
     "0", "Causes", ["kpi_pareto.causes_to_80pct"], "How many causes it takes to reach 80% of delay minutes."),
    ("fact_delay", "Causes with Minutes",
     "COUNTROWS ( FILTER ( VALUES ( dim_cause[cause_code] ), [Delay Minutes] > 0 ) )", "0", "Causes",
     ["kpi_pareto.causes_with_minutes"], "Causes with at least one minute of delay."),
    ("fact_delay", "Share of Causes to 80%",
     "DIVIDE ( [Causes to 80%], [Causes with Minutes] )", "0.0%", "Causes",
     ["kpi_pareto.share_of_causes_to_80pct"], "Causes reaching 80% of minutes as a share of all causes with minutes."),
    ("station_ranking", "Station Incidents", "SUM ( station_ranking[incidents] )", "#,0", "Ranking",
     ["station_ranking_all.incidents"], "Incidents at the station in the selected ranking period."),
    ("station_ranking", "Naive Minutes per Incident",
     "AVERAGE ( station_ranking[naive_minutes_per_incident] )", "0.00", "Ranking",
     ["station_ranking_all.naive_minutes_per_incident"], "The station's own minutes per incident."),
    ("station_ranking", "Line Minutes per Incident",
     "AVERAGE ( station_ranking[line_minutes_per_incident] )", "0.00", "Ranking",
     ["station_ranking_all.line_minutes_per_incident"], "Minutes per incident across the station's line."),
    ("station_ranking", "Shrinkage Weight",
     "AVERAGE ( station_ranking[shrinkage_weight] )", "0%", "Ranking",
     ["station_ranking_all.shrinkage_weight"], "How far the estimate moved toward the line rate (0% = not at all)."),
    ("station_ranking", "Shrunk Minutes per Incident",
     "AVERAGE ( station_ranking[shrunk_minutes_per_incident] )", "0.00", "Ranking",
     ["station_ranking_all.shrunk_minutes_per_incident"], "Empirical-Bayes estimate of minutes per incident."),
    ("station_ranking", "Naive Rank", "MIN ( station_ranking[naive_rank] )", "0", "Ranking",
     ["station_ranking_all.naive_rank"], "Rank by the station's own rate (1 = most minutes per incident)."),
    ("station_ranking", "Shrunk Rank", "MIN ( station_ranking[shrunk_rank] )", "0", "Ranking",
     ["station_ranking_all.shrunk_rank"], "Rank by the shrunk rate (1 = least reliable)."),
    ("station_ranking", "Rank Change", "SUM ( station_ranking[rank_change] )", "+0;-0;0", "Ranking",
     ["station_ranking_all.rank_change"], "Naive rank minus shrunk rank (positive = looks worse after shrinkage)."),
]


# ---------------------------------------------------------------------------
# TMDL writers
# ---------------------------------------------------------------------------
def q(name: str) -> str:
    """Quote a TMDL object name when needed."""
    return name if name.replace("_", "").isalnum() else "'" + name.replace("'", "''") + "'"


def partition_source(table: str, columns: list) -> list[str]:
    types = ", ".join(f'{{"{c}", {M_TYPE[t]}}}' for c, t, _ in columns)
    return [
        "let",
        f'    Source = Csv.Document(File.Contents(DataFolder & "\\{table}.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),',
        "    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),",
        '    Blanks = Table.TransformColumns(Promoted, {}, each if _ = "" then null else _),',
        f'    Typed = Table.TransformColumnTypes(Blanks, {{{types}}}, "en-US")',
        "in",
        "    Typed",
    ]


def table_tmdl(name: str, spec: dict) -> str:
    out = [f"table {q(name)}", f"\tlineageTag: {tag(name)}"]
    if spec.get("date_table"):
        out.append("\tdataCategory: Time")
    out.append("")
    for t, mname, dax, fmt, folder, twins, desc in [m for m in MEASURES if m[0] == name]:
        out.append(f"\t/// {desc}")
        lines = dax.split("\n")
        if len(lines) == 1:
            out.append(f"\tmeasure {q(mname)} = {dax}")
        else:
            out.append(f"\tmeasure {q(mname)} =")
            out += [f"\t\t\t{line}" for line in lines]
        out.append(f"\t\tformatString: {fmt}")
        out.append(f"\t\tdisplayFolder: {folder}")
        out.append(f"\t\tlineageTag: {tag(name, 'measure', mname)}")
        out.append("")
        out.append(f"\t\tannotation SqlTwin = {', '.join(twins)}")
        out.append("")
    for col, dtype, opts in spec["columns"]:
        out.append(f"\tcolumn {q(col)}")
        out.append(f"\t\tdataType: {dtype}")
        if opts.get("key"):
            out.append("\t\tisKey")
        if opts.get("hidden"):
            out.append("\t\tisHidden")
        if opts.get("format"):
            out.append(f"\t\tformatString: {opts['format']}")
        elif dtype == I:
            out.append("\t\tformatString: 0")
        out.append(f"\t\tlineageTag: {tag(name, col)}")
        out.append(f"\t\tsummarizeBy: {opts.get('summarize', 'none')}")
        out.append(f"\t\tsourceColumn: {col}")
        if opts.get("sort_by"):
            out.append(f"\t\tsortByColumn: {opts['sort_by']}")
        out.append("")
        out.append("\t\tannotation SummarizationSetBy = User")
        out.append("")
    out.append(f"\tpartition {q(name)} = m")
    out.append("\t\tmode: import")
    out.append("\t\tsource =")
    out += [f"\t\t\t\t{line}" for line in partition_source(name, spec["columns"])]
    out.append("")
    out.append("\tannotation PBI_ResultType = Table")
    out.append("")
    return "\n".join(out)


def write_model() -> None:
    definition = MODEL_DIR / "definition"
    if definition.exists():
        shutil.rmtree(definition)
    (definition / "tables").mkdir(parents=True)
    (MODEL_DIR / "definition.pbism").write_text(json.dumps({
        "$schema": f"{SCHEMA}/item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "4.2",
        "settings": {},
    }, indent=2) + "\n")
    (definition / "database.tmdl").write_text(f"database {NAME}\n\tcompatibilityLevel: 1600\n\n")
    model = [
        "model Model",
        "\tculture: en-US",
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
        "\tdiscourageImplicitMeasures",
        "\tsourceQueryCulture: en-US",
        "\tdataAccessOptions",
        "\t\tlegacyRedirects",
        "\t\treturnErrorValuesAsNull",
        "",
        "annotation PBI_QueryOrder = " + json.dumps(["DataFolder", *TABLES]),
        "",
        "annotation __PBI_TimeIntelligenceEnabled = 0",
        "",
    ]
    model += [f"ref table {q(t)}" for t in TABLES]
    model.append("")
    (definition / "model.tmdl").write_text("\n".join(model))
    (definition / "expressions.tmdl").write_text(
        f'/// Folder holding the CSV exports written by `python3 -m ttc_delay run` (data/export).\n'
        f'expression DataFolder = "{DEFAULT_DATA_FOLDER}" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]\n'
        f"\tlineageTag: {tag('DataFolder')}\n\n"
        "\tannotation PBI_ResultType = Text\n\n"
    )
    rel = []
    for ft, fc, tt, tc in RELATIONSHIPS:
        rel += [f"relationship {tag('rel', ft, fc, tt, tc)}", f"\tfromColumn: {ft}.{fc}", f"\ttoColumn: {tt}.{tc}", ""]
    (definition / "relationships.tmdl").write_text("\n".join(rel))
    for name, spec in TABLES.items():
        (definition / "tables" / f"{name}.tmdl").write_text(table_tmdl(name, spec))


# ---------------------------------------------------------------------------
# Report (PBIR)
# ---------------------------------------------------------------------------
def measure(table: str, name: str) -> dict:
    return {"Measure": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}}


def column(table: str, name: str) -> dict:
    return {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": name}}


def proj(field: dict) -> dict:
    kind = "Measure" if "Measure" in field else "Column"
    entity = field[kind]["Expression"]["SourceRef"]["Entity"]
    prop = field[kind]["Property"]
    return {"field": field, "queryRef": f"{entity}.{prop}", "nativeQueryRef": prop}


def visual(name, vtype, x, y, w, h, roles, title=None, sort=None, z=0):
    query = {"queryState": {role: {"projections": [proj(f) for f in fields]} for role, fields in roles.items()}}
    if sort:
        field, direction = sort
        query["sortDefinition"] = {"sort": [{"field": field, "direction": direction}], "isDefaultSort": False}
    v = {"visualType": vtype, "query": query, "drillFilterOtherVisuals": True}
    if title:
        v["visualContainerObjects"] = {
            "title": [{"properties": {
                "show": {"expr": {"Literal": {"Value": "true"}}},
                "text": {"expr": {"Literal": {"Value": "'" + title.replace("'", "''") + "'"}}},
            }}]
        }
    return {
        "$schema": f"{SCHEMA}/item/report/definition/visualContainer/2.4.0/schema.json",
        "name": name,
        "position": {"x": x, "y": y, "z": z, "height": h, "width": w, "tabOrder": z},
        "visual": v,
    }


def textbox(name, x, y, w, h, text):
    return {
        "$schema": f"{SCHEMA}/item/report/definition/visualContainer/2.4.0/schema.json",
        "name": name,
        "position": {"x": x, "y": y, "z": 0, "height": h, "width": w, "tabOrder": 0},
        "visual": {
            "visualType": "textbox",
            "objects": {"general": [{"properties": {"paragraphs": [{"textRuns": [
                {"value": text, "textStyle": {"fontSize": "14pt", "fontWeight": "bold"}}]}]}}]},
        },
    }


FD, DD, DL, DS, DC, SR = "fact_delay", "dim_date", "dim_line", "dim_station", "dim_cause", "station_ranking"


def pages() -> list[tuple[str, str, list[dict]]]:
    year_slicer = lambda n, x: visual(n, "slicer", x, 60, 200, 60, {"Values": [column(DD, "year")]}, "Year")  # noqa: E731
    line_slicer = lambda n, x: visual(n, "slicer", x, 60, 260, 60, {"Values": [column(DL, "line_name")]}, "Line")  # noqa: E731
    overview = [
        textbox("ov_title", 20, 10, 800, 44, "TTC subway delays - overview"),
        year_slicer("ov_year", 860), line_slicer("ov_line", 1000),
        visual("ov_incidents", "card", 20, 130, 290, 110, {"Values": [measure(FD, "Incidents")]}),
        visual("ov_minutes", "card", 330, 130, 290, 110, {"Values": [measure(FD, "Delay Minutes")]}),
        visual("ov_mpi", "card", 640, 130, 290, 110, {"Values": [measure(FD, "Minutes per Incident")]}),
        visual("ov_yoy", "card", 950, 130, 310, 110, {"Values": [measure(FD, "Delay Minutes YoY %")]}),
        visual("ov_by_month", "lineChart", 20, 260, 820, 440,
               {"Category": [column(DD, "month_start")], "Y": [measure(FD, "Delay Minutes")]},
               "Delay minutes by month"),
        visual("ov_by_line", "clusteredBarChart", 860, 260, 400, 440,
               {"Category": [column(DL, "line_name")], "Y": [measure(FD, "Delay Minutes")]},
               "Delay minutes by line", sort=(measure(FD, "Delay Minutes"), "Descending")),
    ]
    pareto = [
        textbox("pa_title", 20, 10, 800, 44, "Root causes - Pareto of lost minutes"),
        year_slicer("pa_year", 860), line_slicer("pa_line", 1000),
        visual("pa_to80", "card", 20, 130, 240, 110, {"Values": [measure(FD, "Causes to 80%")]}),
        visual("pa_share80", "card", 20, 260, 240, 110, {"Values": [measure(FD, "Share of Causes to 80%")]}),
        visual("pa_with_minutes", "card", 20, 390, 240, 110, {"Values": [measure(FD, "Causes with Minutes")]}),
        visual("pa_chart", "lineClusteredColumnComboChart", 280, 130, 980, 330,
               {"Category": [column(DC, "cause_code")], "Y": [measure(FD, "Delay Minutes")],
                "Y2": [measure(FD, "Cumulative Cause Share")]},
               "Delay minutes by cause, with cumulative share",
               sort=(measure(FD, "Delay Minutes"), "Descending")),
        visual("pa_table", "tableEx", 280, 480, 980, 230,
               {"Values": [measure(FD, "Cause Rank"), column(DC, "cause_label"), column(DC, "cause_category"),
                           measure(FD, "Incidents"), measure(FD, "Delay Minutes"), measure(FD, "Share of Minutes"),
                           measure(FD, "Cumulative Cause Share")]},
               "Causes ranked by minutes", sort=(measure(FD, "Delay Minutes"), "Descending")),
    ]
    ranking = [
        textbox("rk_title", 20, 10, 800, 44, "Station reliability - naive vs. shrunk ranking"),
        visual("rk_period", "slicer", 860, 60, 400, 60, {"Values": [column(SR, "period")]}, "Ranking period"),
        visual("rk_table", "tableEx", 20, 130, 1240, 380,
               {"Values": [column(DS, "station_label"), measure(SR, "Station Incidents"),
                           measure(SR, "Naive Minutes per Incident"), measure(SR, "Line Minutes per Incident"),
                           measure(SR, "Shrinkage Weight"), measure(SR, "Shrunk Minutes per Incident"),
                           measure(SR, "Naive Rank"), measure(SR, "Shrunk Rank"), measure(SR, "Rank Change"),
                           column(SR, "explanation")]},
               "Stations ranked by shrunk minutes per incident (1 = least reliable)",
               sort=(measure(SR, "Shrunk Rank"), "Ascending")),
        visual("rk_scatter", "scatterChart", 20, 530, 620, 180,
               {"Category": [column(DS, "station_label")], "X": [measure(SR, "Naive Minutes per Incident")],
                "Y": [measure(SR, "Shrunk Minutes per Incident")], "Size": [measure(SR, "Station Incidents")]},
               "Naive vs. shrunk rate (bubble size = incidents)"),
        visual("rk_movers", "clusteredBarChart", 660, 530, 600, 180,
               {"Category": [column(DS, "station_label")], "Y": [measure(SR, "Rank Change")]},
               "Rank change after shrinkage", sort=(measure(SR, "Rank Change"), "Descending")),
    ]
    trend = [
        textbox("tr_title", 20, 10, 800, 44, "Trend - rolling 12 months and year over year"),
        line_slicer("tr_line", 1000),
        visual("tr_r12", "lineChart", 20, 130, 820, 290,
               {"Category": [column(DD, "month_start")], "Y": [measure(FD, "Delay Minutes R12M")],
                "Series": [column(DL, "line_name")]},
               "Delay minutes, rolling 12 months, by line"),
        visual("tr_mom", "card", 860, 130, 400, 135, {"Values": [measure(FD, "Delay Minutes MoM %")]}),
        visual("tr_inc_r12", "card", 860, 285, 400, 135, {"Values": [measure(FD, "Incidents R12M")]}),
        visual("tr_years", "tableEx", 20, 440, 620, 270,
               {"Values": [column(DD, "year"), measure(FD, "Incidents"), measure(FD, "Incidents YoY %"),
                           measure(FD, "Delay Minutes"), measure(FD, "Delay Minutes PY"),
                           measure(FD, "Delay Minutes YoY %"), measure(FD, "Minutes per Incident")]},
               "Year over year (partial years compare like-for-like dates)"),
        visual("tr_category", "pivotTable", 660, 440, 600, 270,
               {"Rows": [column(DC, "cause_category")], "Columns": [column(DD, "year")],
                "Values": [measure(FD, "Share of Minutes")]},
               "Share of minutes by cause category"),
    ]
    return [
        ("overview", "Overview", overview),
        ("cause_pareto", "Cause Pareto", pareto),
        ("station_ranking", "Station Ranking", ranking),
        ("trend", "Trend", trend),
    ]


def write_report() -> None:
    if REPORT_DIR.exists():
        shutil.rmtree(REPORT_DIR)
    definition = REPORT_DIR / "definition"
    (definition / "pages").mkdir(parents=True)
    (REPORT_DIR / "definition.pbir").write_text(json.dumps({
        "$schema": f"{SCHEMA}/item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0",
        "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}},
    }, indent=2) + "\n")
    (definition / "version.json").write_text(json.dumps({
        "$schema": f"{SCHEMA}/item/report/definition/versionMetadata/1.0.0/schema.json",
        "version": "2.0.0",
    }, indent=2) + "\n")
    theme = "CY24SU10"
    (definition / "report.json").write_text(json.dumps({
        "$schema": f"{SCHEMA}/item/report/definition/report/3.0.0/schema.json",
        "themeCollection": {"baseTheme": {
            "name": theme,
            "reportVersionAtImport": {"visual": "1.8.95", "report": "2.0.95", "page": "1.3.95"},
            "type": "SharedResources",
        }},
        "resourcePackages": [{
            "name": "SharedResources", "type": "SharedResources",
            "items": [{"name": theme, "path": f"BaseThemes/{theme}.json", "type": "BaseTheme"}],
        }],
        "settings": {"useStylableVisualContainerHeader": True, "defaultDrillFilterOtherVisuals": True},
    }, indent=2) + "\n")
    theme_dir = REPORT_DIR / "StaticResources" / "SharedResources" / "BaseThemes"
    theme_dir.mkdir(parents=True)
    (theme_dir / f"{theme}.json").write_text(json.dumps({
        "name": theme,
        "dataColors": ["#118DFF", "#12239E", "#E66C37", "#6B007B", "#E044A7", "#744EC2", "#D9B300", "#D64550"],
        "foreground": "#252423", "background": "#FFFFFF", "tableAccent": "#118DFF",
    }, indent=2) + "\n")
    order = []
    for page_name, display, visuals in pages():
        order.append(page_name)
        pdir = definition / "pages" / page_name
        (pdir / "visuals").mkdir(parents=True)
        (pdir / "page.json").write_text(json.dumps({
            "$schema": f"{SCHEMA}/item/report/definition/page/2.0.0/schema.json",
            "name": page_name, "displayName": display, "displayOption": "FitToPage",
            "height": 720, "width": 1280,
        }, indent=2) + "\n")
        for v in visuals:
            vdir = pdir / "visuals" / v["name"]
            vdir.mkdir()
            (vdir / "visual.json").write_text(json.dumps(v, indent=2) + "\n")
    (definition / "pages" / "pages.json").write_text(json.dumps({
        "$schema": f"{SCHEMA}/item/report/definition/pagesMetadata/1.0.0/schema.json",
        "pageOrder": order, "activePageName": order[0],
    }, indent=2) + "\n")


def write_project() -> None:
    PBIP_DIR.mkdir(exist_ok=True)
    (PBIP_DIR / f"{NAME}.pbip").write_text(json.dumps({
        "$schema": f"{SCHEMA}/pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0",
        "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
        "settings": {"enableAutoRecovery": True},
    }, indent=2) + "\n")
    (PBIP_DIR / ".gitignore").write_text("**/.pbi/localSettings.json\n**/.pbi/cache.abf\n")


if __name__ == "__main__":
    write_project()
    write_model()
    write_report()
    print(f"wrote {PBIP_DIR}")
