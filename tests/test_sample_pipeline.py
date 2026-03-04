"""End-to-end run on the committed sample of the real files."""

import pytest

from ttc_delay import pipeline
from ttc_delay.config import SAMPLE_DIR


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    base = tmp_path_factory.mktemp("sample")
    return pipeline.run(SAMPLE_DIR, ":memory:", base / "reports", base / "export")


def test_sample_checks_pass(sample):
    assert sample.ok, [(c.name, c.detail) for c in sample.checks if c.status == "fail"]


def test_sample_covers_every_year_and_line(sample):
    years = [r[0] for r in sample.con.execute("SELECT DISTINCT year FROM v_delay ORDER BY 1").fetchall()]
    assert years[0] == 2014 and years == list(range(2014, years[-1] + 1))
    lines = {r[0] for r in sample.con.execute("SELECT DISTINCT line_code FROM v_delay").fetchall()}
    assert {"YU", "BD", "SHP", "SRT"} <= lines


def test_sample_station_resolution_rate(sample):
    share = sample.con.execute(
        "SELECT avg(CASE WHEN location_type = 'unmatched' THEN 1 ELSE 0 END) FROM v_delay"
    ).fetchone()[0]
    assert share < 0.01


def test_sample_kpis_are_consistent(sample):
    con = sample.con
    total = con.execute("SELECT sum(min_delay) FROM fact_delay").fetchone()[0]
    assert con.execute("SELECT sum(delay_minutes) FROM kpi_year WHERE line_code = 'ALL'").fetchone()[0] == total
    assert con.execute("SELECT sum(delay_minutes) FROM kpi_month WHERE line_code = 'ALL'").fetchone()[0] == total
    assert con.execute(
        "SELECT delay_minutes FROM kpi_pareto WHERE line_scope = 'ALL' AND year_scope = 'ALL'"
    ).fetchone()[0] == total
    # rolling 12 months at the last month equals the sum of the last 12 monthly values
    r12, direct = con.execute(
        """SELECT (SELECT rolling_12m_minutes FROM kpi_month WHERE line_code='ALL' ORDER BY month_start DESC LIMIT 1),
                  (SELECT sum(delay_minutes) FROM (SELECT delay_minutes FROM kpi_month WHERE line_code='ALL'
                   ORDER BY month_start DESC LIMIT 12))"""
    ).fetchone()
    assert r12 == direct
    ranks = con.execute("SELECT count(*), count(DISTINCT shrunk_rank) FROM station_ranking_all").fetchone()
    assert ranks[0] == ranks[1] > 60
