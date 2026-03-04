"""tools/check_pbip.py passes on the committed project and catches breakage."""

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("check_pbip", ROOT / "tools" / "check_pbip.py")
check_pbip = importlib.util.module_from_spec(spec)
sys.modules["check_pbip"] = check_pbip
spec.loader.exec_module(check_pbip)

MODEL = "TTCDelay.SemanticModel/definition"
REPORT = "TTCDelay.Report/definition"


def run(pbip_dir):
    checker = check_pbip.Checker(pbip_dir)
    status = checker.run()
    return status, checker.errors


@pytest.fixture
def project(tmp_path):
    target = tmp_path / "powerbi"
    shutil.copytree(ROOT / "powerbi", target)
    return target


def edit(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new, 1))


def test_committed_project_passes():
    status, errors = run(ROOT / "powerbi")
    assert status == 0, errors


def test_unknown_measure_reference(project):
    edit(project / MODEL / "tables/fact_delay.tmdl", "DIVIDE ( [Delay Minutes], [Incidents] )",
         "DIVIDE ( [Delay Minutez], [Incidents] )")
    assert any("unknown measure [Delay Minutez]" in e for e in run(project)[1])


def test_unknown_column_reference(project):
    edit(project / MODEL / "tables/fact_delay.tmdl", "SUM ( fact_delay[min_gap] )", "SUM ( fact_delay[gap] )")
    assert any("unknown column fact_delay[gap]" in e for e in run(project)[1])


def test_unbalanced_dax(project):
    edit(project / MODEL / "tables/fact_delay.tmdl", "SUM ( fact_delay[min_gap] )", "SUM ( fact_delay[min_gap] ")
    assert any("unbalanced" in e for e in run(project)[1])


def test_missing_sql_twin(project):
    edit(project / MODEL / "tables/fact_delay.tmdl", "annotation SqlTwin = kpi_year.gap_minutes\n", "")
    assert any("'Gap Minutes': no SqlTwin" in e for e in run(project)[1])


def test_twin_without_hand_value(project):
    edit(project / MODEL / "tables/fact_delay.tmdl", "annotation SqlTwin = kpi_year.gap_minutes",
         "annotation SqlTwin = kpi_month.gap_minutes")
    assert any("has no hand-computed test case" in e for e in run(project)[1])


def test_twin_column_missing_from_sql(project):
    edit(project / MODEL / "tables/fact_delay.tmdl", "annotation SqlTwin = kpi_year.gap_minutes",
         "annotation SqlTwin = kpi_year.no_such_column")
    assert any("does not exist" in e for e in run(project)[1])


def test_bad_indentation(project):
    edit(project / MODEL / "tables/dim_line.tmdl", "\tcolumn line_code", "  column line_code")
    assert any("indentation must use tabs" in e for e in run(project)[1])


def test_relationship_to_missing_column(project):
    edit(project / MODEL / "relationships.tmdl", "toColumn: dim_cause.cause_key", "toColumn: dim_cause.cause_id")
    assert any("column not found" in e for e in run(project)[1])


def test_column_not_in_export(project):
    edit(project / MODEL / "tables/dim_line.tmdl", "sourceColumn: line_code", "sourceColumn: line_kode")
    errors = run(project)[1]
    assert any("differ between TMDL and export" in e for e in errors)


def test_visual_field_must_exist(project):
    path = project / REPORT / "pages/overview/visuals/ov_minutes/visual.json"
    doc = json.loads(path.read_text())
    doc["visual"]["query"]["queryState"]["Values"]["projections"][0]["field"]["Measure"]["Property"] = "Nope"
    path.write_text(json.dumps(doc))
    assert any("measure fact_delay[Nope] not found" in e for e in run(project)[1])


def test_visual_must_fit_on_page(project):
    path = project / REPORT / "pages/overview/visuals/ov_minutes/visual.json"
    doc = json.loads(path.read_text())
    doc["position"]["x"] = 1200
    path.write_text(json.dumps(doc))
    assert any("does not fit" in e for e in run(project)[1])


def test_invalid_json(project):
    (project / REPORT / "pages/pages.json").write_text("{not json")
    assert any("invalid JSON" in e for e in run(project)[1])


def test_parse_tmdl_multiline_expression():
    nodes = check_pbip.parse_tmdl(
        "table t\n\tmeasure 'A b' =\n\t\t\tVAR x = 1\n\t\t\tRETURN\n\t\t\t    x\n\t\tformatString: 0\n\n"
        "\tcolumn c\n\t\tdataType: int64\n\t\tisHidden\n"
    )
    table = nodes[0]
    m = table.of("measure")[0]
    assert m.name == "A b" and m.expression == "VAR x = 1\nRETURN\n    x" and m.props["formatString"] == "0"
    assert table.of("column")[0].props == {"dataType": "int64", "isHidden": True}


def test_dax_reference_extraction():
    qualified, bare = check_pbip.dax_references(
        "CALCULATE ( [Delay Minutes], 'dim date'[date] > 1, fact_delay[min_delay] > 0, \"[not a ref]\" ) + [@m]"
    )
    assert qualified == {("dim date", "date"), ("fact_delay", "min_delay")}
    assert bare == {"Delay Minutes", "@m"}
