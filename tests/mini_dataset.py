"""Tiny hand-checkable datasets written in the real source-file formats.

``MINI`` drives the KPI tests: 17 source rows over 2023-2025 in three formats
(multi-sheet XLSX, single-sheet XLSX, datastore CSV), including one exact
duplicate, a misspelt station, a yard, a line-wide entry logged against two
lines, an unmatched location and an undocumented code.

``RANKING`` drives the shrinkage tests: five stations on two lines.

Expected values are worked out by hand in ``tests/hand_values.py``.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

COLUMNS = ["Date", "Time", "Day", "Station", "Code", "Min Delay", "Min Gap", "Bound", "Line", "Vehicle"]

# fmt: off
MINI_2023_JAN = [
    ("2023-01-05", "08:00", "KENNEDY BD STATION",    "SUDP",  10, 15, "E", "BD", 5001),  # 1
    ("2023-01-05", "09:00", "KENNEDY BD STATION",    "MUI",    0,  0, "W", "BD", 5002),  # 2
    ("2023-01-10", "17:30", "FINCH STATION",         "SUDP",   6, 10, "S", "YU", 5003),  # 3
    ("2023-01-20", "12:00", "ST GEORGE YUS STATION", "EUDO",   4,  8, "N", "YU", 5004),  # 4
    ("2023-01-10", "17:30", "FINCH STATION",         "SUDP",   6, 10, "S", "YU", 5003),  # 5 = exact duplicate of 3
]
MINI_2023_FEB = [
    ("2023-02-02", "07:15", "FINCH STATION",         "PUOPO", 20, 25, "S", "YU", 5005),  # 6
    ("2023-02-14", "18:00", "KENNEDY BD STATION",    "SUDP",   2,  5, "W", "BD", 5006),  # 7
    ("2023-02-20", "10:00", "YONGE BD STATION",      "MUI",    3,  6, "E", "BD", 5007),  # 8 Bloor-Yonge, Line 2
]
MINI_2024 = [
    ("2024-01-03", "08:00", "KENNEDY BD STATION",    "SUDP",   5,  9, "E", "BD", 5008),     # 9
    ("2024-01-15", "16:00", "FINCH STATION",         "MUI",   12, 16, "S", "YU", 5009),     # 10
    ("2024-01-20", "02:00", "YONGE UNIVERSITY LINE", "MUGD",   0,  0, None, "YU/BD", 0),    # 11 line-wide, two lines
    ("2024-02-01", "09:00", "FINCH STATION",         "SUDP",   0,  0, "N", "YU", 5010),     # 12
    ("2024-02-09", "22:00", "KENEDY BD STATION",     "EUDO",   8, 12, "W", "BD", 5011),     # 13 misspelt
    ("2024-03-10", "01:00", "GREENWOOD YARD",        "MUO",    0,  0, None, "BD", 0),       # 14 yard
]
MINI_2025 = [
    ("2025-01-07", "08:00", "FINCH STATION",         "SUDP",   7, 11, "S", "YU", 5012),  # 15
    ("2025-02-11", "08:00", "KENNEDY BD STATION",    "MUI",    1,  4, "E", "BD", 5013),  # 16
    ("2025-02-12", "08:00", "ZZZ NOWHERE",           "XXXX",   0,  0, None, "YU", 0),    # 17 unmatched, undocumented
]

RANKING_2025 = [
    ("2025-01-01", "08:00", "FINCH STATION",   "SUDP",  8, 12, "S", "YU", 1),
    ("2025-01-02", "08:00", "FINCH STATION",   "SUDP", 12, 16, "S", "YU", 2),
    ("2025-01-03", "08:00", "UNION STATION",   "SUDP",  0,  0, "S", "YU", 3),
    ("2025-01-04", "08:00", "UNION STATION",   "SUDP",  4,  8, "S", "YU", 4),
    ("2025-01-05", "08:00", "MUSEUM STATION",  "SUDP",  9, 13, "S", "YU", 5),
    ("2025-01-06", "08:00", "KIPLING STATION", "SUDP",  1,  5, "E", "BD", 6),
    ("2025-01-07", "08:00", "KIPLING STATION", "SUDP",  3,  7, "E", "BD", 7),
    ("2025-01-08", "08:00", "BAY STATION",     "SUDP",  3,  7, "E", "BD", 8),
    ("2025-01-09", "08:00", "BAY STATION",     "SUDP",  5,  9, "E", "BD", 9),
]
# fmt: on

CODE_LIST = [
    ("SUDP", "DISORDERLY PATRON"),
    ("MUI", "INJURED/ILL CUSTOMER ON TRAIN â\u0080\u0093 TRANSPORTED"),  # mojibake as published
    ("EUDO", "DOOR PROBLEMS RE:FAULTY EQUIPMENT"),
    ("PUOPO", "OPTO (COMMUNICATIONS) TRAIN DOOR MONITORING"),
    ("MUO", "MISCELLANEOUS OTHER"),
    ("MUGD", "MISCELLANEOUS GENERAL SUBWAY LINE DELAYS"),
]

MINI_SOURCE_ROWS = len(MINI_2023_JAN) + len(MINI_2023_FEB) + len(MINI_2024) + len(MINI_2025)


def _frame(rows, excel: bool) -> pd.DataFrame:
    records = []
    for date, time, station, code, delay, gap, bound, line, vehicle in rows:
        d = dt.datetime.fromisoformat(date)
        records.append(
            (d if excel else date, time, d.strftime("%A"), station, code, delay, gap, bound, line, vehicle)
        )
    return pd.DataFrame(records, columns=COLUMNS)


def _write_codes(raw_dir: Path) -> None:
    pd.DataFrame(
        [(i + 1, c, d) for i, (c, d) in enumerate(CODE_LIST)], columns=["_id", "CODE", "DESCRIPTION"]
    ).to_csv(raw_dir / "code-descriptions.csv", index=False, encoding="utf-8")


def _write_csv(rows, path: Path) -> None:
    df = _frame(rows, excel=False)
    df.insert(0, "_id", range(1, len(df) + 1))
    df.to_csv(path, index=False)


def write_mini(raw_dir: Path) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(raw_dir / "ttc-subway-delay-2023.xlsx", engine="openpyxl") as w:
        _frame(MINI_2023_JAN, True).to_excel(w, sheet_name="Jan 23", index=False)
        _frame(MINI_2023_FEB, True).to_excel(w, sheet_name="Feb '23", index=False)
    with pd.ExcelWriter(raw_dir / "ttc-subway-delay-2024.xlsx", engine="openpyxl") as w:
        _frame(MINI_2024, True).to_excel(w, sheet_name="2024", index=False)
    _write_csv(MINI_2025, raw_dir / "ttc-subway-delay-data-since-2025.csv")
    _write_codes(raw_dir)
    return raw_dir


def write_ranking(raw_dir: Path) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(RANKING_2025, raw_dir / "ttc-subway-delay-data-since-2025.csv")
    _write_codes(raw_dir)
    return raw_dir
