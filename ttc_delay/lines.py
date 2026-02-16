"""Normalise the free-text ``Line`` field to a small set of line codes."""

from __future__ import annotations

import re

_EXACT = {
    "YU": "YU", "YUS": "YU", "Y U": "YU", "LINE 1": "YU", "LINE1": "YU", "YU LINE": "YU",
    "YONGE UNIVERSITY": "YU", "1": "YU",
    "BD": "BD", "B D": "BD", "BD LINE": "BD", "BD LINE 2": "BD", "LINE 2": "BD", "LINE2": "BD",
    "BLOOR DANFORTH": "BD", "2": "BD",
    "SHP": "SHP", "SHEP": "SHP", "SHEPPARD": "SHP", "LINE 4": "SHP", "LINE4": "SHP", "4": "SHP",
    "SRT": "SRT", "RT": "SRT", "LINE 3": "SRT", "LINE3": "SRT", "3": "SRT",
}


def normalise_line(raw: object) -> str:
    """Map a raw line label to YU, BD, SRT, SHP, MULTI, OTHER or UNKNOWN."""
    if raw is None or (isinstance(raw, float) and raw != raw):
        return "UNKNOWN"
    s = str(raw).upper().strip()
    if s in ("", "999", "0", "NAN"):
        return "UNKNOWN"
    s = re.sub(r"[/&,\-]", " ", s)
    s = re.sub(r"\bLINES?\b", " LINE ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if s in _EXACT:
        return _EXACT[s]
    tokens = set(re.findall(r"[A-Z]+|\d+", s))
    found = set()
    if tokens & {"YU", "YUS", "Y"} or "YONGE" in tokens:
        found.add("YU")
    if tokens & {"BD", "B"} or "BLOOR" in tokens or "DANFORTH" in tokens:
        found.add("BD")
    if tokens & {"SHP", "SHEP", "SHEPPARD"}:
        found.add("SHP")
    if tokens & {"SRT"}:
        found.add("SRT")
    if len(found) > 1:
        return "MULTI"
    if len(found) == 1 and not re.match(r"^\d{2,3} ", s):
        return found.pop()
    if re.match(r"^\d{1,3} [A-Z]", s):
        return "OTHER"  # a bus or streetcar route, e.g. "29 DUFFERIN"
    return "OTHER"
