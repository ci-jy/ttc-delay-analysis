"""Hand-computed values for every SQL twin of a Power BI measure.

Keys are ``view.column`` exactly as written in each measure's ``SqlTwin``
annotation. Each case gives the dataset (``mini`` or ``ranking`` from
``tests/mini_dataset.py``), the row filter and the value worked out by hand.
``tools/check_pbip.py`` fails if a measure's twin has no case here.

Working for the mini dataset (16 rows after removing the duplicate):

    2023: Jan rows 1-4 -> minutes 10+0+6+4 = 20 (4 incidents)
          Feb rows 6-8 -> minutes 20+2+3   = 25 (3 incidents)
          year: 45 minutes, 7 incidents, 6 with minutes > 0, gap 69
          Line 1 (YU): 6+4+20 = 30; Line 2 (BD): 10+0+2+3 = 15
    2024: Jan 5+12+0 = 17 (3 incidents), Feb 0+8 = 8, Mar 0 -> 25 minutes, 6 incidents
          BD: Jan 5, Feb 8
    2025: (to 12 Feb, the last date) 7+1+0 = 8 minutes, 3 incidents
          like-for-like 2024 (1 Jan-12 Feb): 25 minutes, 5 incidents (yard row is in March)

    Causes, all years: SUDP 10+6+2+5+0+7 = 30, PUOPO 20, MUI 0+3+12+1 = 16, EUDO 4+8 = 12
          total 78; cumulative 30, 50, 66, 78 -> 38.5%, 64.1%, 84.6%, 100%
          causes before EUDO already hold 84.6% >= 80% -> 3 causes reach 80%
    Causes, 2023: PUOPO 20, SUDP 18, EUDO 4, MUI 3 (total 45) -> 2 causes reach 80%

Working for the ranking dataset (normal-normal empirical Bayes):

    Line 1: Finch [8, 12] mean 10 var 8; Union [0, 4] mean 2 var 8; Museum [9]
            line mean 33/5 = 6.6; pooled within variance (8+8)/2 = 8
    Line 2: Kipling [1, 3] mean 2 var 2; Bay [3, 5] mean 4 var 2
            line mean 12/4 = 3; pooled within variance (2+2)/2 = 2
    sampling variance v = sigma2/n: Finch 4, Union 4, Museum 8, Kipling 1, Bay 1
    (x - mu)^2 - v: 11.56-4, 21.16-4, 5.76-8, 1-1, 1-1 = 7.56, 17.16, -2.24, 0, 0
    tau2 = 22.48 / 5 = 4.496
    B = v / (v + tau2): Finch, Union 4/8.496 = 0.470810; Museum 8/12.496 = 0.640205;
                        Kipling, Bay 1/5.496 = 0.181951
    shrunk: Finch 10 - 0.470810*3.4 = 8.399247; Union 2 + 0.470810*4.6 = 4.165725;
            Museum 9 - 0.640205*2.4 = 7.463508; Kipling 2.181951; Bay 3.818049
    naive order: Finch 10, Museum 9, Bay 4, Kipling 2, Union 2 (tie -> label order)
    shrunk order: Finch, Museum, Union, Bay, Kipling -> Union rises 5 -> 3
"""

TWIN_CASES: dict[str, list[tuple[str, dict, float]]] = {
    # yearly KPIs
    "kpi_year.incidents": [
        ("mini", {"line_code": "ALL", "year": 2023}, 7),
        ("mini", {"line_code": "YU", "year": 2023}, 3),
        ("mini", {"line_code": "BD", "year": 2024}, 3),
    ],
    "kpi_year.delay_incidents": [("mini", {"line_code": "ALL", "year": 2023}, 6)],
    "kpi_year.delay_minutes": [
        ("mini", {"line_code": "ALL", "year": 2023}, 45),
        ("mini", {"line_code": "YU", "year": 2023}, 30),
        ("mini", {"line_code": "BD", "year": 2023}, 15),
        ("mini", {"line_code": "ALL", "year": 2024}, 25),
    ],
    "kpi_year.gap_minutes": [("mini", {"line_code": "ALL", "year": 2023}, 69)],
    "kpi_year.minutes_per_incident": [("mini", {"line_code": "ALL", "year": 2023}, 45 / 7)],
    "kpi_month.minutes_per_incident": [("mini", {"line_code": "ALL", "year_month": "2023-01"}, 20 / 4)],
    "kpi_year.prev_year_minutes": [
        ("mini", {"line_code": "ALL", "year": 2024}, 45),
        ("mini", {"line_code": "ALL", "year": 2025}, 25),
    ],
    "kpi_year.yoy_change_minutes": [
        ("mini", {"line_code": "ALL", "year": 2024}, (25 - 45) / 45),
        ("mini", {"line_code": "ALL", "year": 2025}, (8 - 25) / 25),
    ],
    "kpi_year.prev_year_incidents": [
        ("mini", {"line_code": "ALL", "year": 2024}, 7),
        ("mini", {"line_code": "ALL", "year": 2025}, 5),
    ],
    "kpi_year.yoy_change_incidents": [
        ("mini", {"line_code": "ALL", "year": 2024}, (6 - 7) / 7),
        ("mini", {"line_code": "ALL", "year": 2025}, (3 - 5) / 5),
    ],
    # monthly KPIs
    "kpi_month.incidents": [("mini", {"line_code": "ALL", "year_month": "2023-01"}, 4)],
    "kpi_month.delay_minutes": [("mini", {"line_code": "ALL", "year_month": "2023-02"}, 25)],
    "kpi_month.prev_month_minutes": [("mini", {"line_code": "ALL", "year_month": "2023-02"}, 20)],
    "kpi_month.mom_change_minutes": [
        ("mini", {"line_code": "ALL", "year_month": "2023-02"}, 0.25),
        ("mini", {"line_code": "BD", "year_month": "2024-02"}, 0.6),
    ],
    "kpi_month.mom_change_incidents": [("mini", {"line_code": "ALL", "year_month": "2023-02"}, -0.25)],
    "kpi_month.yoy_change_minutes": [("mini", {"line_code": "ALL", "year_month": "2024-01"}, -0.15)],
    "kpi_month.rolling_12m_minutes": [
        ("mini", {"line_code": "ALL", "year_month": "2024-01"}, 42),
        ("mini", {"line_code": "ALL", "year_month": "2024-02"}, 25),
    ],
    "kpi_month.rolling_12m_incidents": [("mini", {"line_code": "ALL", "year_month": "2024-01"}, 6)],
    # causes and Pareto
    "kpi_cause.share_of_minutes": [
        ("mini", {"line_scope": "ALL", "year_scope": "ALL", "cause_code": "SUDP"}, 30 / 78),
        ("mini", {"line_scope": "ALL", "year_scope": "2023", "cause_code": "PUOPO"}, 20 / 45),
    ],
    # Line 2, 2023: SUDP rows 1 and 7 give 10 + 2 = 12 of the line's 15 minutes
    "kpi_category_year.share_of_minutes": [
        ("mini", {"line_code": "BD", "year": 2023, "cause_category": "Security & passenger behaviour"}, 12 / 15),
    ],
    "kpi_cause.minutes_rank": [
        ("mini", {"line_scope": "ALL", "year_scope": "ALL", "cause_code": "PUOPO"}, 2),
        ("mini", {"line_scope": "ALL", "year_scope": "2023", "cause_code": "PUOPO"}, 1),
    ],
    "kpi_cause.cumulative_share": [
        ("mini", {"line_scope": "ALL", "year_scope": "ALL", "cause_code": "MUI"}, 66 / 78),
    ],
    "kpi_pareto.causes_to_80pct": [
        ("mini", {"line_scope": "ALL", "year_scope": "ALL"}, 3),
        ("mini", {"line_scope": "ALL", "year_scope": "2023"}, 2),
    ],
    "kpi_pareto.causes_with_minutes": [("mini", {"line_scope": "ALL", "year_scope": "ALL"}, 4)],
    "kpi_pareto.share_of_causes_to_80pct": [("mini", {"line_scope": "ALL", "year_scope": "ALL"}, 0.75)],
    # station ranking
    "station_ranking_all.shrunk_minutes_per_incident": [
        ("ranking", {"station_label": "Finch (Line 1)"}, 8.399247),
        ("ranking", {"station_label": "Union (Line 1)"}, 4.165725),
        ("ranking", {"station_label": "Museum (Line 1)"}, 7.463508),
        ("ranking", {"station_label": "Kipling (Line 2)"}, 2.181951),
        ("ranking", {"station_label": "Bay (Line 2)"}, 3.818049),
    ],
    "station_ranking_all.naive_minutes_per_incident": [("ranking", {"station_label": "Museum (Line 1)"}, 9)],
    "station_ranking_all.line_minutes_per_incident": [
        ("ranking", {"station_label": "Finch (Line 1)"}, 6.6),
        ("ranking", {"station_label": "Kipling (Line 2)"}, 3),
    ],
    "station_ranking_all.shrinkage_weight": [
        ("ranking", {"station_label": "Museum (Line 1)"}, 0.640205),
        ("ranking", {"station_label": "Kipling (Line 2)"}, 0.181951),
    ],
    "station_ranking_all.incidents": [("ranking", {"station_label": "Museum (Line 1)"}, 1)],
    "station_ranking_all.shrunk_rank": [("ranking", {"station_label": "Union (Line 1)"}, 3)],
    "station_ranking_all.naive_rank": [("ranking", {"station_label": "Union (Line 1)"}, 5)],
    "station_ranking_all.rank_change": [
        ("ranking", {"station_label": "Union (Line 1)"}, 2),
        ("ranking", {"station_label": "Kipling (Line 2)"}, -1),
    ],
}
