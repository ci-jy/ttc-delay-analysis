import pandas as pd
import pytest

from ttc_delay.ranking import PERIODS, explain


def test_between_variance_and_line_rates(ranking_con):
    rows = ranking_con.execute(
        "SELECT DISTINCT line_code, line_minutes_per_incident, line_within_variance, between_variance "
        "FROM station_ranking_all ORDER BY line_code"
    ).fetchall()
    assert rows[0][0] == "BD" and rows[0][1:] == pytest.approx((3.0, 2.0, 4.496))
    assert rows[1][0] == "YU" and rows[1][1:] == pytest.approx((6.6, 8.0, 4.496))


def test_shrinkage_moves_estimates_toward_line_rate(ranking_con):
    df = ranking_con.execute("SELECT * FROM station_ranking_all").df()
    gap_before = (df["naive_minutes_per_incident"] - df["line_minutes_per_incident"]).abs()
    gap_after = (df["shrunk_minutes_per_incident"] - df["line_minutes_per_incident"]).abs()
    assert (gap_after <= gap_before + 1e-12).all()
    # the single-incident station is shrunk the most
    assert df.loc[df["shrinkage_weight"].idxmax(), "station_label"] == "Museum (Line 1)"


def test_full_pooling_when_no_between_station_spread(tmp_path):
    from tests.mini_dataset import _write_codes, _write_csv
    from ttc_delay import pipeline

    rows = [("2025-01-0%d" % (i + 1), "08:00", st, "SUDP", m, m, "S", "YU", i)
            for i, (st, m) in enumerate([("FINCH STATION", 0), ("FINCH STATION", 10),
                                         ("UNION STATION", 0), ("UNION STATION", 10)])]
    raw = tmp_path / "raw"
    raw.mkdir()
    _write_csv(rows, raw / "ttc-subway-delay-data-since-2025.csv")
    _write_codes(raw)
    con = pipeline.run(raw, ":memory:", None, None).con
    df = con.execute("SELECT * FROM station_ranking_all").df()
    assert (df["between_variance"] == 0).all()
    assert (df["shrinkage_weight"] == 1).all()
    assert df["shrunk_minutes_per_incident"].tolist() == pytest.approx([5.0, 5.0])


def test_materialised_periods(ranking_con):
    df = ranking_con.execute("SELECT period, count(*) AS n FROM station_ranking GROUP BY period").df()
    assert set(df["period"]) == set(PERIODS)
    assert (df["n"] == 5).all()  # all data falls in the last 12 months
    union = ranking_con.execute(
        "SELECT explanation FROM station_ranking WHERE period = 'All years' AND station_label = 'Union (Line 1)'"
    ).fetchone()[0]
    assert union.startswith("Stable")  # moved 2 places


def test_ranking_excludes_non_station_locations(mini):
    labels = {r[0] for r in mini.execute("SELECT station_label FROM station_ranking_all").fetchall()}
    assert labels == {"Kennedy (Line 2)", "Finch (Line 1)", "St George (Line 1)", "Bloor-Yonge (Line 2)"}


@pytest.mark.parametrize(
    "change,weight,start",
    [(0, 0.5, "Stable"), (5, 0.6, "Rose 5 places"), (-4, 0.1, "Dropped 4 places"), (-3, 0.4, "Dropped 3 places")],
)
def test_explanations(change, weight, start):
    row = pd.Series({"rank_change": change, "shrinkage_weight": weight, "incidents": 40,
                     "line_minutes_per_incident": 2.5, "naive_minutes_per_incident": 4.0,
                     "shrunk_minutes_per_incident": 3.4})
    text = explain(row)
    assert text.startswith(start)
    if weight >= 0.25 and change:
        assert "treated as noise" in text


def test_closed_station_not_ranked_after_closure(tmp_path):
    from tests.mini_dataset import _write_codes, _write_csv
    from ttc_delay import pipeline

    rows = [
        ("2025-01-01", "08:00", "MCCOWAN STATION", "SRDP", 5, 9, "S", "SRT", 1),  # Line 3 closed 2023-07-24
        ("2025-01-02", "08:00", "FINCH STATION", "SUDP", 4, 8, "S", "YU", 2),
    ]
    raw = tmp_path / "raw"
    raw.mkdir()
    _write_csv(rows, raw / "ttc-subway-delay-data-since-2025.csv")
    _write_codes(raw)
    con = pipeline.run(raw, ":memory:", None, None).con
    labels = [r[0] for r in con.execute("SELECT station_label FROM station_ranking_all").fetchall()]
    assert labels == ["Finch (Line 1)"]
    early = con.execute("SELECT count(*) FROM station_ranking_for(DATE '2023-01-01', DATE '2025-12-31')").fetchone()[0]
    assert early == 2
