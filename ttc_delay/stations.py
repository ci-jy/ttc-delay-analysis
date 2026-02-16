"""Station-name normalisation.

The raw ``Station`` field is free text typed by transit control staff, cut to
22 characters, and spelled hundreds of ways ("KENNEDY BD STATION",
"KENNEDY BD STATION - P", "SCARB CTR STATION", "DUFFERIN STATON", ...).
Each raw name is resolved in this order:

1. ``clean_name``: upper-case, drop punctuation, the word STATION and any text
   after it, truncated "STATIO"/"STATI" endings, and a trailing line hint
   (``BD``, ``YUS``, ``SHP``, ``SRT``) that is kept to pick the right platform
   at interchange stations.
2. Non-station locations: line-wide entries ("YONGE UNIVERSITY LINE"),
   segments between stations ("UNION STATION TO KING") and yards/carhouses.
3. Exact alias lookup: every canonical station name plus the curated aliases
   in ``reference/station_aliases.csv``.
4. Fuzzy match (``difflib`` ratio) against the alias keys, for misspellings.
   Suggestions listed in ``reference/station_fuzzy_review.csv`` with
   ``decision=reject`` are refused; ``accept`` marks them as reviewed.
5. Anything left is ``unmatched`` and is listed in the matching report.
"""

from __future__ import annotations

import csv
import difflib
import re
from dataclasses import dataclass
from pathlib import Path

from .config import REFERENCE_DIR

SUBWAY_LINES = ("YU", "BD", "SRT", "SHP")
FUZZY_CUTOFF = 0.85

LINE_HINTS = {
    "BD": "BD",
    "B D": "BD",
    "YUS": "YU",
    "YU": "YU",
    "SHP": "SHP",
    "SHEP": "SHP",
    "SRT": "SRT",
    "RT": "SRT",
}

LINE_WIDE_PATTERNS = [
    r"\bLINES?\b",
    r"\bSUBWAY\b",
    r"\bSYSTEM\b",
    r"\bALL STATIONS\b",
    r"\bTRAN[SI]+T COMMIS",
    r"^TTC\b",
    r"^YONGE UNIVERSITY\b",
    r"^YONGE UNIVERISTY\b",
    r"^BLOOR DANFORTH",
    r"\bRAPID TRAN",
    r"^TYSSE\b",
    r"^YUS AND BD\b",
    r"^YU AND BD\b",
    r"\bCLOSURE\b",
    r"\bSUBW",
    r"^(YUS?|BD|SHP|SRT|LINE ?\d)$",
    r"\bSYSTEMWIDE\b",
    r"\bVARIOUS\b",
    r"\bUNIVERSITY SPADI",
    r"\bUNIVERS?TIY\b",
    r"^CHANGE OVERS\b",
    r"\bUNKNOWN\b",
]

FACILITY_PATTERNS = [
    r"\bYARD\b",
    r"\bCARHOUSE\b",
    r"\bHOSTLER\b",
    r"\bWYE\b",
    r"\bPORTAL\b",
    r"\bBUILD UP\b",
    r"\bSHOPS?\b",
    r"\bTRACK\b",
    r"\bSUBSTATION\b",
    r"\bPOWER\b",
    r"\bCOMPLEX\b",
    r"\bSIGNALS?\b",
    r"\bPOCKET\b",
    r"\bINTERLOCKING\b",
    r"\bCENTRE TRACK\b",
    r"\bEE[B]?$",
    r"\bDI?VI?SION\b",
    r"\bBUILDING\b",
    r"\bTRANSIT CONTRO",
    r"\bCAR ?HOUSE\b",
    r"\bGARAGE\b",
    r"\bBUILD ?UP\b",
    r"\bBU$",
    r"\bMIGRATI",
    r"\bEMERGENCY E",
    r"\bTAIL TR",
    r"\bCENTRE TRAC",
    r"\bTRAINING\b",
    r"\bHOS[LT]+ER\b",
    r"\bVIADUCT\b",
    r"\bBUS TERMINAL\b",
    r"\bHUB\b",
    r"^HILLCREST\b",
    r"\bLOWER\b",
    r"^\d+ [A-Z]+ (AVE|AVENUE|ST|STREET|RD|ROAD|DR|DRIVE|BLVD)\b",
]

SEGMENT_PATTERNS = [r"\bTO\b", r"\bAND\b", r"\bTOWARDS\b", r"\bBETWEEN\b"]


@dataclass(frozen=True)
class Station:
    station_code: str
    station_name: str
    line_code: str


@dataclass(frozen=True)
class Match:
    location_type: str  # station | segment | facility | line_wide | unmatched
    station_code: str | None
    method: str  # alias | fuzzy | rule | none
    cleaned: str
    line_hint: str | None
    score: float | None = None
    fuzzy_target: str | None = None


def clean_name(raw: object) -> tuple[str, str | None]:
    """Return ``(core_name, line_hint)`` for a raw station string."""
    if raw is None or (isinstance(raw, float) and raw != raw):
        return "", None
    s = str(raw).upper().strip()
    # Platform/entrance qualifiers after " - " or "(" ("KIPLING STATION (ENTER").
    s = re.split(r"\s+-\s+|\(", s, maxsplit=1)[0]
    s = s.replace("&", " AND ").replace("’", "").replace("'", "").replace(".", " ")
    s = re.sub(r"[-/,:;]", " ", s)
    s = re.sub(r"\bSAINT\b", "ST", s)
    s = re.sub(r"\s+", " ", s).strip()
    # Keep text before the word STATION unless STATION starts a segment
    # description ("UNION STATION TO KING" must stay a segment).
    m = re.search(r"\bSTATION\b", s)
    if m and not re.search(r"\b(TO|AND)\b", s[m.end():]):
        s = s[: m.start()].strip()
    else:
        s = re.sub(r"\s+STA(T(I(O(N)?)?)?)?$", "", s).strip()
        s = re.sub(r"\s+(STATON|SATION|STAION|STAITON|STATIN|STATOIN|STN)$", "", s).strip()
    s = re.sub(r"\s+PLAT(F(O(R(M)?)?)?)?$", "", s).strip()
    hint = None
    # "ST GEORGE BD/YU STATIO": a two-line hint says nothing about the platform.
    s = re.sub(r"\s+(BD YUS?|YUS? BD)$", "", s).strip()
    for token, line in sorted(LINE_HINTS.items(), key=lambda kv: -len(kv[0])):
        if s.endswith(" " + token):
            hint = line
            s = s[: -len(token) - 1].strip()
            break
    return s, hint


def _clean_alias(name: str) -> str:
    return clean_name(name)[0]


class StationMatcher:
    """Resolve raw station strings to canonical station codes."""

    def __init__(self, reference_dir: Path = REFERENCE_DIR):
        self.stations: list[Station] = []
        with open(reference_dir / "stations.csv", newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                self.stations.append(
                    Station(row["station_code"], row["station_name"], row["line_code"])
                )
        self.by_code = {s.station_code: s for s in self.stations}
        # alias -> list of (line_code or None, station_code), in priority order
        self.aliases: dict[str, list[tuple[str | None, str]]] = {}
        with open(reference_dir / "station_aliases.csv", newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if row["station_code"] not in self.by_code:
                    raise ValueError(f"alias {row['alias']!r} points to unknown station {row['station_code']!r}")
                self._add_alias(row["alias"], row["line_code"] or None, row["station_code"])
        for st in self.stations:
            self._add_alias(st.station_name, None, st.station_code)
        self.fuzzy_review: dict[tuple[str, str], str] = {}
        review_path = reference_dir / "station_fuzzy_review.csv"
        if review_path.exists():
            with open(review_path, newline="", encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    self.fuzzy_review[(row["cleaned_name"], row["station_code"])] = row["decision"].strip().lower()
        self._cache: dict[tuple[str, str | None], Match] = {}

    def _add_alias(self, alias: str, line: str | None, code: str) -> None:
        key = _clean_alias(alias)
        entries = self.aliases.setdefault(key, [])
        if (line, code) not in entries:
            entries.append((line, code))

    def _pick(self, key: str, line: str | None) -> str | None:
        entries = self.aliases.get(key)
        if not entries:
            return None
        if line:
            for alias_line, code in entries:
                if alias_line == line:
                    return code
            for alias_line, code in entries:
                if alias_line is None and self.by_code[code].line_code == line:
                    return code
        for alias_line, code in entries:
            if alias_line is None:
                return code
        return entries[0][1]

    def match(self, raw: object, record_line: str | None = None) -> Match:
        key = (str(raw), record_line)
        if key not in self._cache:
            self._cache[key] = self._match(raw, record_line)
        return self._cache[key]

    def _match(self, raw: object, record_line: str | None) -> Match:
        cleaned, hint = clean_name(raw)
        line = hint or (record_line if record_line in SUBWAY_LINES else None)
        if not cleaned:
            return Match("unmatched", None, "none", cleaned, hint)
        code = self._pick(cleaned, line)
        if code:
            return Match("station", code, "alias", cleaned, hint)
        for pattern in LINE_WIDE_PATTERNS:
            if re.search(pattern, cleaned):
                return Match("line_wide", None, "rule", cleaned, hint)
        for pattern in FACILITY_PATTERNS:
            if re.search(pattern, cleaned):
                return Match("facility", None, "rule", cleaned, hint)
        for pattern in SEGMENT_PATTERNS:
            if re.search(pattern, cleaned):
                return Match("segment", None, "rule", cleaned, hint)
        candidates = difflib.get_close_matches(cleaned, list(self.aliases), n=1, cutoff=FUZZY_CUTOFF)
        if candidates:
            target = candidates[0]
            code = self._pick(target, line)
            score = difflib.SequenceMatcher(None, cleaned, target).ratio()
            decision = self.fuzzy_review.get((cleaned, code))
            if decision != "reject":
                method = "fuzzy_reviewed" if decision == "accept" else "fuzzy"
                return Match("station", code, method, cleaned, hint, round(score, 3), target)
            return Match("unmatched", None, "fuzzy_rejected", cleaned, hint, round(score, 3), target)
        return Match("unmatched", None, "none", cleaned, hint)
