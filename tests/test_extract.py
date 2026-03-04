import datetime as dt

import pandas as pd

from tests import mini_dataset
from ttc_delay.extract import _parse_time, delay_files, read_all


def test_reads_all_formats(tmp_path):
    raw = mini_dataset.write_mini(tmp_path)
    assert [p.name for p in delay_files(raw)] == [
        "ttc-subway-delay-2023.xlsx",
        "ttc-subway-delay-2024.xlsx",
        "ttc-subway-delay-data-since-2025.csv",
    ]
    df = read_all(raw)
    assert len(df) == mini_dataset.MINI_SOURCE_ROWS
    assert set(df["source_sheet"]) == {"Jan 23", "Feb '23", "2024", ""}
    assert df["date"].dtype.kind == "M"
    assert df["date"].min() == pd.Timestamp("2023-01-05")
    assert df["date"].max() == pd.Timestamp("2025-02-12")
    assert "_id" not in df.columns
    assert df["min_delay"].sum() == 45 + 6 + 25 + 8  # includes the duplicate row
    assert df.loc[df["station"] == "GREENWOOD YARD", "bound"].isna().all()


def test_parse_time_variants():
    assert _parse_time("8:05") == "08:05"
    assert _parse_time(dt.time(23, 59)) == "23:59"
    assert _parse_time(pd.Timestamp("2020-01-01 07:30")) == "07:30"
    assert _parse_time("25:00") is None
    assert _parse_time(None) is None


def test_column_name_variants(tmp_path):
    df = pd.DataFrame(
        {"DATE": ["2024-05-01"], "TIME": ["10:00"], "DAY": ["Wednesday"], "STATION": ["BAY STATION"],
         "CODE": ["SUDP"], "Min_Delay": [3], "Min_Gap": [5], "BOUND": ["E"], "LINE": ["BD"], "VEHICLE": [5000]}
    )
    df.to_csv(tmp_path / "ttc-subway-delay-2024.csv", index=False)
    out = read_all(tmp_path)
    assert out.loc[0, "min_delay"] == 3 and out.loc[0, "station"] == "BAY STATION"
