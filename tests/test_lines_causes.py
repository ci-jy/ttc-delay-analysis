import pandas as pd
import pytest

from tests import mini_dataset
from ttc_delay.causes import build_dim_cause, load_code_lists, normalise_code, repair_text
from ttc_delay.lines import normalise_line


@pytest.mark.parametrize(
    "raw,code",
    [
        ("YU", "YU"), ("YUS", "YU"), ("LINE 1", "YU"), ("BD", "BD"), ("B/D", "BD"), ("BD LINE 2", "BD"),
        ("BLOOR - DANFORTH", "BD"), ("SHP", "SHP"), ("SHEP", "SHP"), ("SRT", "SRT"),
        ("YU/BD", "MULTI"), ("YU / BD", "MULTI"), ("BD/YUS", "MULTI"), ("YU & BD LINES", "MULTI"),
        ("YU/BD/SHP", "MULTI"), ("29 DUFFERIN", "OTHER"), ("504 KING", "OTHER"),
        (None, "UNKNOWN"), (float("nan"), "UNKNOWN"), ("999", "UNKNOWN"),
    ],
)
def test_normalise_line(raw, code):
    assert normalise_line(raw) == code


def test_repair_text_fixes_mojibake():
    assert repair_text("PRIORITY ONE â\u0080\u0093 TRAIN") == "PRIORITY ONE – TRAIN"
    assert repair_text("ALREADY FINE") == "ALREADY FINE"
    assert repair_text(None) == ""


def test_normalise_code():
    assert normalise_code(" sudp ") == "SUDP"
    assert normalise_code(None) == "UNKNOWN"


def test_dim_cause_marks_undocumented_and_categories(tmp_path):
    raw = mini_dataset.write_mini(tmp_path)
    lists = load_code_lists(raw)
    dim = build_dim_cause(pd.Series(["SUDP", "MUI", "XXXX", "TUSC"]), lists).set_index("cause_code")
    assert dim.at["SUDP", "cause_category"] == "Security & passenger behaviour"
    assert dim.at["MUI", "cause_description"].endswith("– TRANSPORTED")
    assert dim.at["XXXX", "description_source"] == "undocumented"
    assert dim.at["TUSC", "cause_category"] == "Transportation (operations & crew)"
    assert dim.at["UNKNOWN", "description_source"] == "not recorded"
    assert dim["cause_key"].is_unique


def test_legacy_code_list_fills_srt_codes():
    from ttc_delay.config import SAMPLE_DIR

    lists = load_code_lists(SAMPLE_DIR).set_index("code")
    assert lists.at["ERTC", "description_source"] == "legacy code list"
    assert lists.at["SUDP", "description_source"] == "current code list"
