"""Every SQL twin of a Power BI measure, checked against hand-computed values."""

import pytest

from tests.hand_values import TWIN_CASES

CASES = [
    pytest.param(twin, dataset, filters, expected, id=f"{twin}[{'|'.join(map(str, filters.values()))}]")
    for twin, cases in TWIN_CASES.items()
    for dataset, filters, expected in cases
]


@pytest.mark.parametrize("twin,dataset,filters,expected", CASES)
def test_twin_matches_hand_value(twin, dataset, filters, expected, mini, ranking_con):
    con = {"mini": mini, "ranking": ranking_con}[dataset]
    view, column = twin.split(".")
    where = " AND ".join(f"{k} = ?" for k in filters)
    rows = con.execute(f"SELECT {column} FROM {view} WHERE {where}", list(filters.values())).fetchall()
    assert len(rows) == 1, f"{twin} {filters}: expected one row, got {len(rows)}"
    assert rows[0][0] == pytest.approx(expected, abs=1e-5)


def test_month_grid_is_complete(mini):
    # 2023-01 .. 2025-02 = 26 months for each of 4 subway lines plus ALL.
    assert mini.execute("SELECT count(*) FROM kpi_month").fetchone()[0] == 26 * 5
    assert mini.execute(
        "SELECT incidents, delay_minutes FROM kpi_month WHERE line_code = 'ALL' AND year_month = '2023-06'"
    ).fetchone() == (0, 0)


def test_first_period_has_no_comparison(mini):
    row = mini.execute(
        "SELECT prev_year_minutes, yoy_change_minutes FROM kpi_year WHERE line_code = 'ALL' AND year = 2023"
    ).fetchone()
    assert row == (None, None)
    row = mini.execute(
        "SELECT prev_month_minutes, mom_change_minutes FROM kpi_month WHERE line_code = 'ALL' AND year_month = '2023-01'"
    ).fetchone()
    assert row == (None, None)


def test_mom_is_null_when_previous_month_is_zero(mini):
    # Network minutes: 2023-03 is 0, so April's change has no base.
    assert mini.execute(
        "SELECT mom_change_minutes FROM kpi_month WHERE line_code = 'ALL' AND year_month = '2023-04'"
    ).fetchone()[0] is None


def test_cause_shares_sum_to_one_per_scope(mini):
    rows = mini.execute(
        "SELECT line_scope, year_scope, sum(share_of_minutes) FROM kpi_cause "
        "GROUP BY ALL HAVING sum(delay_minutes) > 0"
    ).fetchall()
    assert rows and all(abs(r[2] - 1) < 1e-9 for r in rows)


def test_pareto_order_and_flags(mini):
    rows = mini.execute(
        "SELECT cause_code, delay_minutes, in_pareto_80 FROM kpi_cause "
        "WHERE line_scope = 'ALL' AND year_scope = 'ALL' ORDER BY minutes_rank"
    ).fetchall()
    assert [r[0] for r in rows[:4]] == ["SUDP", "PUOPO", "MUI", "EUDO"]
    assert [r[2] for r in rows[:4]] == [True, True, True, False]
    # zero-minute causes never count toward the 80%
    assert all(not r[2] for r in rows if r[1] == 0)


def test_pareto_ties_break_by_cause_code(tmp_path):
    import duckdb

    from ttc_delay.config import SQL_DIR

    con = duckdb.connect()
    con.execute((SQL_DIR / "schema.sql").read_text())
    con.execute("INSERT INTO dim_date VALUES (20240101, DATE '2024-01-01', 2024, 1, 1, 'Jan', DATE '2024-01-01', '2024-01', 1, 'Monday', false)")
    con.execute("INSERT INTO dim_line VALUES (1, 'YU', 1, 'Line 1', true, 1)")
    con.execute("INSERT INTO dim_station VALUES (1, 'YU_FINCH', 'Finch', 'Finch (Line 1)', 'YU', 'station', true, NULL, NULL)")
    con.execute("INSERT INTO dim_cause VALUES (1, 'BBB', 'b', 'x', 'c', 'Subway', 'BBB - b'), (2, 'AAA', 'a', 'x', 'c', 'Subway', 'AAA - a')")
    con.execute(
        "INSERT INTO fact_delay (delay_id, date_key, station_key, line_key, cause_key, min_delay, min_gap, source_file, source_row) "
        "VALUES (1, 20240101, 1, 1, 1, 5, 5, 'f', 1), (2, 20240101, 1, 1, 2, 5, 5, 'f', 2)"
    )
    con.execute((SQL_DIR / "kpis.sql").read_text())
    rows = con.execute(
        "SELECT cause_code, minutes_rank, in_pareto_80 FROM kpi_cause WHERE line_scope='ALL' AND year_scope='ALL' ORDER BY minutes_rank"
    ).fetchall()
    assert rows == [("AAA", 1, True), ("BBB", 2, True)]
