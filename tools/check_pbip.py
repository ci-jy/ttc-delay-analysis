"""Check the Power BI project (powerbi/) is well formed and tied to the SQL KPIs.

Checks
  * every JSON file parses and declares its ``$schema``; the .pbip and .pbir
    paths resolve; pages.json lists the page folders;
  * TMDL parses (tab indentation, known object kinds); ``model.tmdl`` refers
    to exactly the table files; columns have valid types and sort columns;
    one import partition per table reading ``<table>.csv`` from the
    ``DataFolder`` parameter with a type for every column; one date table;
  * relationships join existing columns of the same type, and the "one" side
    is unique in the exported data;
  * the TMDL columns equal the CSV headers the pipeline exports;
  * DAX: balanced brackets and quotes; every ``[Measure]`` and
    ``table[column]`` reference resolves;
  * every measure has a ``SqlTwin`` annotation naming ``view.column``s that
    exist in the warehouse and have hand-computed cases in
    ``tests/hand_values.py`` (which the test suite checks);
  * every field used by a report visual exists in the model with the right
    kind (measure or column) and every visual fits on its page.

Usage: ``python3 tools/check_pbip.py [--pbip-dir powerbi]``. Exit status 1 on
any error.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OBJECT_KINDS = {
    "model", "database", "table", "column", "measure", "partition", "relationship", "expression",
    "annotation", "hierarchy", "level", "calculationGroup", "calculationItem", "role", "perspective",
    "cultureInfo", "ref", "changedProperty", "extendedProperty",
}
DATA_TYPES = {"int64", "string", "double", "decimal", "dateTime", "boolean", "binary"}
NAME = r"('(?:[^']|'')*'|[^\s=']+)"
OBJ_RE = re.compile(rf"^(?P<kind>[A-Za-z]+)(?:\s+(?P<sub>table|cultureInfo))?\s+{NAME}(?P<eq>\s*=\s*(?P<expr>.*))?$".replace(NAME, "(?P<name>" + NAME[1:-1] + ")", 1))
PROP_RE = re.compile(r"^(?P<key>[A-Za-z]+)(?:\s*:\s*(?P<value>.*)|\s*=\s*(?P<expr>.*))?$")


class TmdlError(ValueError):
    pass


@dataclass
class Node:
    kind: str
    name: str
    indent: int
    line: int
    expression: str | None = None
    props: dict = field(default_factory=dict)
    children: list = field(default_factory=list)
    description: str = ""

    def of(self, kind: str) -> list["Node"]:
        return [c for c in self.children if c.kind == kind]


def unquote(name: str) -> str:
    if name.startswith("'") and name.endswith("'"):
        return name[1:-1].replace("''", "'")
    return name


def parse_tmdl(text: str, source: str = "<tmdl>") -> list[Node]:
    """Parse the TMDL subset used by Power BI semantic models into nodes."""
    lines = text.split("\n")
    root = Node("root", "", -1, 0)
    stack = [root]
    description: list[str] = []
    i = 0

    def collect_expression(start: int, base_indent: int) -> tuple[str, int]:
        body, j = [], start
        while j < len(lines):
            raw = lines[j]
            if raw.strip() and (len(raw) - len(raw.lstrip("\t"))) <= base_indent + 1:
                break
            body.append(raw)
            j += 1
        while body and not body[-1].strip():
            body.pop()
        if not body:
            raise TmdlError(f"{source}:{start}: empty multi-line expression")
        cut = min(len(b) - len(b.lstrip("\t")) for b in body if b.strip())
        return "\n".join(b[cut:] for b in body), j

    while i < len(lines):
        raw = lines[i]
        lineno = i + 1
        if not raw.strip():
            i += 1
            continue
        if raw.startswith(" "):
            raise TmdlError(f"{source}:{lineno}: indentation must use tabs")
        indent = len(raw) - len(raw.lstrip("\t"))
        text_ = raw.strip()
        if text_.startswith("///"):
            description.append(text_[3:].strip())
            i += 1
            continue
        while stack[-1].indent >= indent:
            stack.pop()
        parent = stack[-1]
        if indent != parent.indent + 1:
            raise TmdlError(f"{source}:{lineno}: unexpected indentation")
        m = OBJ_RE.match(text_)
        if m and m.group("kind") in OBJECT_KINDS:
            kind = m.group("kind") + (f" {m.group('sub')}" if m.group("sub") else "")
            node = Node(kind, unquote(m.group("name")), indent, lineno, description=" ".join(description))
            description = []
            i += 1
            if m.group("eq"):
                expr = (m.group("expr") or "").strip()
                if expr in ("", "```"):
                    node.expression, i = collect_expression(i, indent)
                else:
                    node.expression = expr
            parent.children.append(node)
            stack.append(node)
            continue
        p = PROP_RE.match(text_)
        if not p or parent.kind == "root":
            raise TmdlError(f"{source}:{lineno}: cannot parse line: {text_!r}")
        i += 1
        if p.group("expr") is not None:
            expr = p.group("expr").strip()
            if expr:
                parent.props[p.group("key")] = expr
            else:
                parent.props[p.group("key")], i = collect_expression(i, indent - 1)
        else:
            value = p.group("value")
            parent.props[p.group("key")] = True if value is None else value.strip()
            if value is None:
                # A flag such as "isHidden", or a group such as "dataAccessOptions"
                # whose nested settings follow on deeper-indented lines.
                group = Node("property", p.group("key"), indent, lineno)
                parent.children.append(group)
                stack.append(group)
    return root.children


# ---------------------------------------------------------------------------
# DAX helpers
# ---------------------------------------------------------------------------
def strip_dax_strings(dax: str) -> str:
    """Remove string literals (\"...\" with \"\" escapes) and comments."""
    dax = re.sub(r'"(?:[^"]|"")*"', '""', dax)
    dax = re.sub(r"//[^\n]*|--[^\n]*", "", dax)
    return re.sub(r"/\*.*?\*/", "", dax, flags=re.S)


def balanced(dax: str) -> bool:
    if dax.count('"') % 2:
        return False
    s = re.sub(r"'(?:[^']|'')*'", "''", strip_dax_strings(dax))
    pairs, stack = {")": "(", "]": "[", "}": "{"}, []
    for ch in s:
        if ch in "([{":
            stack.append(ch)
        elif ch in ")]}":
            if not stack or stack.pop() != pairs[ch]:
                return False
    return not stack


def dax_references(dax: str) -> tuple[set[tuple[str, str]], set[str]]:
    """Return ({(table, column)}, {bare [name]}) referenced by a DAX expression."""
    s = strip_dax_strings(dax)
    qualified = set()
    for m in re.finditer(r"(?:'((?:[^']|'')+)'|\b([A-Za-z_][A-Za-z0-9_]*))\[([^\]]+)\]", s):
        table = m.group(1).replace("''", "'") if m.group(1) else m.group(2)
        qualified.add((table, m.group(3)))
    bare = set()
    for m in re.finditer(r"(?<![\w'\]])\[([^\]]+)\]", s):
        bare.add(m.group(1))
    return qualified, bare


# ---------------------------------------------------------------------------
# Checker
# ---------------------------------------------------------------------------
class Checker:
    def __init__(self, pbip_dir: Path):
        self.dir = pbip_dir
        self.errors: list[str] = []
        self.notes: list[str] = []
        self.tables: dict[str, Node] = {}
        self.measures: dict[str, tuple[str, Node]] = {}

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def rel(self, p: Path) -> str:
        return str(p.relative_to(self.dir.parent))

    # -- JSON / project structure -------------------------------------------
    def load_json(self, path: Path):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            self.error(f"{self.rel(path)}: invalid JSON ({exc})")
            return None
        if isinstance(doc, dict) and "$schema" not in doc and "BaseThemes" not in str(path):
            self.error(f"{self.rel(path)}: missing $schema")
        return doc

    def check_project(self) -> tuple[Path | None, Path | None]:
        pbips = sorted(self.dir.glob("*.pbip"))
        if len(pbips) != 1:
            self.error(f"expected one .pbip file in {self.dir}, found {len(pbips)}")
            return None, None
        doc = self.load_json(pbips[0]) or {}
        report_dirs = [self.dir / a["report"]["path"] for a in doc.get("artifacts", []) if "report" in a]
        if len(report_dirs) != 1 or not report_dirs[0].is_dir():
            self.error(f"{pbips[0].name}: report artifact path does not resolve")
            return None, None
        report_dir = report_dirs[0]
        pbir = report_dir / "definition.pbir"
        if not pbir.exists():
            self.error(f"{self.rel(pbir)} missing")
            return report_dir, None
        ref = ((self.load_json(pbir) or {}).get("datasetReference") or {}).get("byPath", {}).get("path")
        model_dir = (report_dir / ref).resolve() if ref else None
        if not model_dir or not model_dir.is_dir():
            self.error(f"{self.rel(pbir)}: datasetReference.byPath does not resolve")
            return report_dir, None
        if not (model_dir / "definition.pbism").exists():
            self.error(f"{model_dir.name}: definition.pbism missing")
        else:
            self.load_json(model_dir / "definition.pbism")
        return report_dir, model_dir

    # -- TMDL ------------------------------------------------------------------
    def parse_file(self, path: Path) -> list[Node]:
        try:
            return parse_tmdl(path.read_text(encoding="utf-8"), self.rel(path))
        except TmdlError as exc:
            self.error(str(exc))
            return []

    def check_model(self, model_dir: Path) -> None:
        definition = model_dir / "definition"
        for required in ("database.tmdl", "model.tmdl", "relationships.tmdl", "expressions.tmdl"):
            if not (definition / required).exists():
                self.error(f"{model_dir.name}/definition/{required} missing")
        model_nodes = self.parse_file(definition / "model.tmdl")
        refs = {n.name for n in model_nodes if n.kind == "ref table"}
        if not any(n.kind == "model" for n in model_nodes):
            self.error("model.tmdl: no model object")
        if not any(n.kind == "database" for n in self.parse_file(definition / "database.tmdl")):
            self.error("database.tmdl: no database object")
        params = {n.name for n in self.parse_file(definition / "expressions.tmdl") if n.kind == "expression"}
        if "DataFolder" not in params:
            self.error("expressions.tmdl: DataFolder parameter missing")

        files = sorted((definition / "tables").glob("*.tmdl"))
        for path in files:
            nodes = [n for n in self.parse_file(path) if n.kind == "table"]
            if len(nodes) != 1 or nodes[0].name != path.stem:
                self.error(f"{self.rel(path)}: must declare exactly one table named {path.stem!r}")
                continue
            self.tables[path.stem] = nodes[0]
        if refs != set(self.tables):
            self.error(f"model.tmdl refs {sorted(refs)} differ from table files {sorted(self.tables)}")

        date_tables = []
        for tname, table in self.tables.items():
            cols = table.of("column")
            names = [c.name for c in cols]
            if len(names) != len(set(names)):
                self.error(f"table {tname}: duplicate column names")
            for c in cols:
                if c.props.get("dataType") not in DATA_TYPES:
                    self.error(f"{tname}[{c.name}]: invalid dataType {c.props.get('dataType')!r}")
                if not c.props.get("sourceColumn"):
                    self.error(f"{tname}[{c.name}]: no sourceColumn")
                if "sortByColumn" in c.props and c.props["sortByColumn"] not in names:
                    self.error(f"{tname}[{c.name}]: sortByColumn {c.props['sortByColumn']!r} not in table")
            parts = table.of("partition")
            if len(parts) != 1:
                self.error(f"table {tname}: expected one partition, found {len(parts)}")
            else:
                self.check_partition(tname, parts[0], cols, params)
            if table.props.get("dataCategory") == "Time":
                keys = [c for c in cols if c.props.get("isKey") is True]
                if len(keys) != 1 or keys[0].props.get("dataType") != "dateTime":
                    self.error(f"date table {tname}: needs exactly one isKey dateTime column")
                date_tables.append(tname)
            for m in table.of("measure"):
                if m.name in self.measures:
                    self.error(f"measure {m.name!r} defined twice")
                if m.name in names:
                    self.error(f"measure {m.name!r} clashes with a column of {tname}")
                self.measures[m.name] = (tname, m)
        if len(date_tables) != 1:
            self.error(f"expected one date table (dataCategory: Time), found {date_tables}")
        self.check_relationships(definition)
        self.check_measures()

    def check_partition(self, tname: str, part: Node, cols: list[Node], params: set[str]) -> None:
        src = part.props.get("source", "")
        if part.props.get("mode") != "import" or part.expression != "m":
            self.error(f"{tname}: partition must be an import M partition")
        if f'DataFolder & "\\{tname}.csv"' not in src:
            self.error(f"{tname}: partition does not read DataFolder\\{tname}.csv")
        typed = dict(re.findall(r'\{"([^"]+)",\s*([^}]+)\}', src))
        expected = {c.props.get("sourceColumn") for c in cols}
        if set(typed) != expected:
            self.error(f"{tname}: M type list {sorted(typed)} does not match columns {sorted(expected)}")
        m_types = {"int64": "Int64.Type", "string": "type text", "double": "type number",
                   "dateTime": "type date", "boolean": "type logical"}
        for c in cols:
            want = m_types.get(c.props.get("dataType"))
            got = typed.get(c.props.get("sourceColumn"), "").strip()
            if want and got and got not in (want, "type datetime"):
                self.error(f"{tname}[{c.name}]: M type {got} does not match dataType {c.props.get('dataType')}")

    def column(self, ref: str) -> Node | None:
        table, _, col = ref.partition(".")
        node = self.tables.get(table)
        return next((c for c in node.of("column") if c.name == col), None) if node else None

    def check_relationships(self, definition: Path) -> None:
        self.relationships = []
        for r in self.parse_file(definition / "relationships.tmdl"):
            if r.kind != "relationship":
                continue
            frm, to = r.props.get("fromColumn", ""), r.props.get("toColumn", "")
            fc, tc = self.column(frm), self.column(to)
            if not fc or not tc:
                self.error(f"relationship {frm} -> {to}: column not found")
                continue
            if fc.props.get("dataType") != tc.props.get("dataType"):
                self.error(f"relationship {frm} -> {to}: data types differ")
            self.relationships.append((frm, to))
        if not self.relationships:
            self.error("no relationships defined")

    def check_measures(self) -> None:
        all_columns = {(t, c.name) for t, n in self.tables.items() for c in n.of("column")}
        for name, (tname, m) in self.measures.items():
            dax = m.expression or ""
            if not dax.strip():
                self.error(f"measure {name!r}: empty expression")
                continue
            if not balanced(dax):
                self.error(f"measure {name!r}: unbalanced brackets or quotes")
            if "formatString" not in m.props:
                self.error(f"measure {name!r}: no formatString")
            qualified, bare = dax_references(dax)
            for table, col in qualified:
                if (table, col) not in all_columns:
                    self.error(f"measure {name!r}: unknown column {table}[{col}]")
            for ref in bare:
                if ref.startswith("@"):
                    continue  # column added by ADDCOLUMNS/SELECTCOLUMNS
                if ref not in self.measures:
                    self.error(f"measure {name!r}: unknown measure [{ref}]")

    # -- SQL twins and exports --------------------------------------------------
    def check_twins_and_exports(self) -> None:
        from tests import mini_dataset
        from tests.hand_values import TWIN_CASES
        from ttc_delay import pipeline

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            built = {}
            for key, writer in (("mini", mini_dataset.write_mini), ("ranking", mini_dataset.write_ranking)):
                built[key] = pipeline.run(writer(tmp / key / "raw"), ":memory:", None, tmp / key / "export")
            con = built["mini"].con
            twin_count = 0
            for name, (tname, m) in sorted(self.measures.items()):
                ann = {a.name: a.expression for a in m.of("annotation")}
                twins = [t.strip() for t in (ann.get("SqlTwin") or "").split(",") if t.strip()]
                if not twins:
                    self.error(f"measure {name!r}: no SqlTwin annotation")
                for twin in twins:
                    twin_count += 1
                    view, _, col = twin.partition(".")
                    try:
                        cols = {r[0] for r in con.execute(f"DESCRIBE {view}").fetchall()}
                    except Exception:  # noqa: BLE001 - any DuckDB error means the view is missing
                        self.error(f"measure {name!r}: SQL twin view {view!r} does not exist")
                        continue
                    if col not in cols:
                        self.error(f"measure {name!r}: SQL twin column {twin!r} does not exist")
                    if not TWIN_CASES.get(twin):
                        self.error(f"measure {name!r}: SQL twin {twin!r} has no hand-computed test case")
            self.notes.append(f"{len(self.measures)} measures, {twin_count} SQL twins checked")

            export_dir = tmp / "mini" / "export"
            for tname, table in self.tables.items():
                path = export_dir / f"{tname}.csv"
                if not path.exists():
                    self.error(f"table {tname}: pipeline does not export {path.name}")
                    continue
                with open(path, newline="", encoding="utf-8") as fh:
                    reader = csv.DictReader(fh)
                    header = set(reader.fieldnames or [])
                    rows = list(reader)
                cols = {c.props.get("sourceColumn") for c in table.of("column")}
                if header != cols:
                    self.error(f"table {tname}: columns {sorted(cols ^ header)} differ between TMDL and export")
                for frm, to in getattr(self, "relationships", []):
                    t_table, _, t_col = to.partition(".")
                    if t_table == tname and rows:
                        values = [r[t_col] for r in rows]
                        if len(values) != len(set(values)):
                            self.error(f"relationship target {to} is not unique in the export")

    # -- report -----------------------------------------------------------------
    def check_report(self, report_dir: Path) -> None:
        definition = report_dir / "definition"
        for required in ("report.json", "version.json", "pages/pages.json"):
            if not (definition / required).exists():
                self.error(f"{report_dir.name}/definition/{required} missing")
        report = self.load_json(definition / "report.json") or {}
        for pkg in report.get("resourcePackages", []):
            for item in pkg.get("items", []):
                path = report_dir / "StaticResources" / pkg["name"] / item["path"]
                if not path.exists():
                    self.error(f"report resource {self.rel(path)} missing")
                else:
                    self.load_json(path)
        self.load_json(definition / "version.json")
        pages_meta = self.load_json(definition / "pages" / "pages.json") or {}
        folders = sorted(p.name for p in (definition / "pages").iterdir() if p.is_dir())
        if sorted(pages_meta.get("pageOrder", [])) != folders:
            self.error(f"pages.json pageOrder {pages_meta.get('pageOrder')} does not match page folders {folders}")
        n_visuals = 0
        for folder in folders:
            pdir = definition / "pages" / folder
            page = self.load_json(pdir / "page.json") or {}
            if page.get("name") != folder:
                self.error(f"page {folder}: name {page.get('name')!r} differs from folder")
            width, height = page.get("width", 0), page.get("height", 0)
            names = set()
            for vpath in sorted((pdir / "visuals").glob("*/visual.json")):
                n_visuals += 1
                v = self.load_json(vpath) or {}
                vname = v.get("name")
                if vname != vpath.parent.name or vname in names:
                    self.error(f"{self.rel(vpath)}: name must match folder and be unique")
                names.add(vname)
                pos = v.get("position", {})
                if pos.get("x", -1) < 0 or pos.get("y", -1) < 0 or \
                        pos.get("x", 0) + pos.get("width", 0) > width or pos.get("y", 0) + pos.get("height", 0) > height:
                    self.error(f"{self.rel(vpath)}: visual does not fit on the {width}x{height} page")
                self.check_visual_fields(vpath, v.get("visual", {}))
        self.notes.append(f"{len(folders)} report pages, {n_visuals} visuals checked")

    def check_visual_fields(self, vpath: Path, visual: dict) -> None:
        query = visual.get("query", {})
        fields = [p for role in query.get("queryState", {}).values() for p in role.get("projections", [])]
        sorts = [{"field": s["field"]} for s in query.get("sortDefinition", {}).get("sort", [])]
        for proj in fields + sorts:
            f = proj.get("field", {})
            kind = "Measure" if "Measure" in f else "Column" if "Column" in f else None
            if not kind:
                self.error(f"{self.rel(vpath)}: unsupported field {f}")
                continue
            entity = f[kind]["Expression"]["SourceRef"].get("Entity")
            prop = f[kind]["Property"]
            if entity not in self.tables:
                self.error(f"{self.rel(vpath)}: unknown table {entity!r}")
                continue
            if kind == "Measure":
                owner = self.measures.get(prop, (None,))[0]
                if owner != entity:
                    self.error(f"{self.rel(vpath)}: measure {entity}[{prop}] not found")
            elif prop not in {c.name for c in self.tables[entity].of("column")}:
                self.error(f"{self.rel(vpath)}: column {entity}[{prop}] not found")
            if "queryRef" in proj and proj["queryRef"] != f"{entity}.{prop}":
                self.error(f"{self.rel(vpath)}: queryRef {proj['queryRef']!r} does not match field")

    def run(self) -> int:
        report_dir, model_dir = self.check_project()
        if model_dir:
            self.check_model(model_dir)
            if self.tables:
                self.check_twins_and_exports()
        if report_dir and self.tables:
            self.check_report(report_dir)
        for note in self.notes:
            print(f"ok    {note}")
        for err in self.errors:
            print(f"ERROR {err}")
        print("PBIP check " + ("failed" if self.errors else "passed") + f" ({len(self.errors)} errors)")
        return 1 if self.errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pbip-dir", type=Path, default=ROOT / "powerbi")
    args = parser.parse_args(argv)
    return Checker(args.pbip_dir).run()


if __name__ == "__main__":
    sys.exit(main())
