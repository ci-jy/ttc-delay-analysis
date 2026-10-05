# Tests and checks

```bash
python3 -m pytest -q          # 172 tests, offline, about 6 seconds
python3 tools/check_pbip.py   # PBIP structure, DAX references, SQL twins, exports, report bindings
```

## Hand-computed values

`tests/test_kpis.py` compares every SQL twin of a DAX measure with values worked out by hand on `tests/mini_dataset.py`. That dataset has 17 rows in the three real file formats, with a duplicate, a misspelt station, a yard, a two-line entry, an unmatched location and an undocumented code. It also includes a five-station shrinkage example. The arithmetic is written out in the docstring of `tests/hand_values.py`.

## Other tests

- station cleaning and matching: interchange platforms, renamed stations, fuzzy matches (reviewed, unreviewed and rejected), segments, yards and line-wide entries
- line and cause normalisation, including repair of mis-encoded text
- each file format
- every data-quality check, including that orphan keys, negative minutes and misfiled rows are caught
- ranking edge cases: full pooling when stations do not differ, and closed stations
- an end-to-end run on the sample
- the PBIP checker, shown to catch broken DAX, missing twins, bad indentation, bad relationships and missing visual fields

## PBIP checker

`tools/check_pbip.py` parses the TMDL and checks:

- tables, columns, partitions, the date table and relationships
- every `[measure]` and `table[column]` reference in the DAX
- that each measure's `SqlTwin` annotation names a `view.column` that exists in the warehouse and has a hand-computed test case
- that the TMDL columns equal the exported CSV headers
- that every report visual binds to existing fields and fits on its page

It does not evaluate DAX.
