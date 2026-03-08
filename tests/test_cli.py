from ttc_delay import cli


def test_cli_sample_run(tmp_path, capsys):
    status = cli.main(["run", "--sample", "--db", str(tmp_path / "w.duckdb"),
                       "--reports-dir", str(tmp_path / "reports"), "--export-dir", str(tmp_path / "export")])
    out = capsys.readouterr().out
    assert status == 0
    assert "[PASS] Row counts per year reconcile" in out
    assert (tmp_path / "w.duckdb").exists()
    assert (tmp_path / "reports" / "data_quality.md").exists()
    assert (tmp_path / "export" / "fact_delay.csv").exists()
