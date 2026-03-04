import json

from tests import mini_dataset
from ttc_delay import quality


def test_all_checks_pass_on_mini(mini_build):
    result, _ = mini_build
    assert result.ok
    statuses = {c.name: c.status for c in result.checks}
    assert all(s in ("pass", "warn") for s in statuses.values())


def test_row_counts_reconcile(mini_build):
    result, _ = mini_build
    rec = next(c for c in result.checks if c.name.startswith("Row counts"))
    by_year = {r["year"]: r for r in rec.data}
    assert by_year[2023] == {"year": 2023, "source_rows": 8, "removed_rows": 1, "loaded_rows": 7}
    assert by_year[2024]["loaded_rows"] == 6 and by_year[2025]["loaded_rows"] == 3
    assert sum(r["source_rows"] for r in rec.data) == mini_dataset.MINI_SOURCE_ROWS


def test_duplicates_and_orphans(mini):
    assert quality.check_duplicates(mini).data == {"removed": 1, "remaining": 0}
    assert quality.check_orphans(mini).status == "pass"
    assert quality.check_minutes(mini).status == "pass"


def test_station_and_cause_coverage(mini):
    st = quality.check_station_matching(mini)
    types = {r["location_type"]: r["rows"] for r in st.data}
    assert types == {"station": 13, "line_wide": 1, "facility": 1, "unmatched": 1}
    causes = quality.check_causes(mini)
    assert {r["description_source"]: r["rows"] for r in causes.data}["undocumented"] == 1


def test_orphan_and_negative_rows_are_detected(tmp_path):
    raw = mini_dataset.write_mini(tmp_path / "raw")
    from ttc_delay import extract, transform, warehouse

    schema = transform.transform(extract.read_all(raw), raw)
    con = warehouse.load(schema, ":memory:")
    # Recreate fact_delay without constraints to simulate a broken load.
    con.execute("CREATE TABLE broken AS SELECT * FROM fact_delay")
    con.execute("DROP VIEW v_delay; DROP TABLE fact_delay; ALTER TABLE broken RENAME TO fact_delay")
    con.execute("UPDATE fact_delay SET station_key = 9999 WHERE delay_id = 1")
    con.execute("UPDATE fact_delay SET min_delay = -5 WHERE delay_id = 2")
    assert quality.check_orphans(con).data["station_key"] == 1
    assert quality.check_orphans(con).status == "fail"
    assert quality.check_minutes(con).status == "fail"


def test_file_period_check_flags_misfiled_rows(tmp_path):
    raw = mini_dataset.write_mini(tmp_path / "raw")
    # rename the 2024 workbook so its rows sit outside the file's stated year
    (raw / "ttc-subway-delay-2024.xlsx").rename(raw / "ttc-subway-delay-2019.xlsx")
    from ttc_delay import pipeline

    res = pipeline.run(raw, ":memory:", None, None)
    period = next(c for c in res.checks if c.name.startswith("Dates fall"))
    assert period.status == "warn"
    assert sum(r["source_rows"] for r in period.data) == 6


def test_datastore_reconciliation(mini, tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "files": [{"file": "ttc-subway-delay-data-since-2025.csv", "resource_name": "TTC Subway Delay Data since 2025.csv"}],
        "datastore_row_counts": {"TTC Subway Delay Data since 2025": 3},
    }))
    assert quality.check_datastore_counts(mini, manifest).status == "pass"
    manifest.write_text(manifest.read_text().replace('": 3', '": 4'))
    assert quality.check_datastore_counts(mini, manifest).status == "fail"


def test_reports_written(mini_build):
    _, base = mini_build
    reports = base / "reports"
    text = (reports / "data_quality.md").read_text()
    assert "| 2023 | 8 | 1 | 7 |" in text
    assert (reports / "station_unmatched.csv").read_text().splitlines()[1].startswith("ZZZ NOWHERE,1")
    assert (reports / "kpi_summary.md").exists()
    exports = sorted(p.name for p in (base / "export").iterdir())
    assert exports == ["dim_cause.csv", "dim_date.csv", "dim_line.csv", "dim_station.csv",
                       "fact_delay.csv", "station_ranking.csv"]
