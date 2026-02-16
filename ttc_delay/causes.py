"""Delay-code (cause) descriptions.

Two code lists are published: the current ``code-descriptions.csv`` and an
older ``ttc-subway-delay-codes.xlsx`` with separate subway and SRT columns.
The current list wins; the legacy list fills in retired and SRT codes; codes
found in the data but in neither list are kept as "Undocumented code".
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

CATEGORY_BY_PREFIX = {
    "E": "Equipment (rolling stock)",
    "M": "Miscellaneous & customer",
    "P": "Plant (track, signals, power, stations)",
    "S": "Security & passenger behaviour",
    "T": "Transportation (operations & crew)",
}
MODE_BY_SECOND_LETTER = {"U": "Subway", "R": "SRT"}


def repair_text(value: object) -> str:
    """Undo UTF-8 text that was decoded as Latin-1/CP1252 ("â€”" -> "—")."""
    if value is None or (isinstance(value, float) and value != value):
        return ""
    text = str(value).strip()
    for codec in ("cp1252", "latin-1"):
        try:
            repaired = text.encode(codec).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        if repaired != text:
            return repaired
    return text


def normalise_code(raw: object) -> str:
    if raw is None or (isinstance(raw, float) and raw != raw):
        return "UNKNOWN"
    code = str(raw).upper().strip()
    return code if code else "UNKNOWN"


def load_code_lists(raw_dir: Path) -> pd.DataFrame:
    """Return ``code, description, description_source`` from the published lists."""
    rows: dict[str, tuple[str, str]] = {}
    current = raw_dir / "code-descriptions.csv"
    if current.exists():
        df = pd.read_csv(current, dtype=str, encoding="utf-8")
        df.columns = [c.strip().upper() for c in df.columns]
        for code, desc in zip(df["CODE"], df["DESCRIPTION"]):
            code = normalise_code(code)
            if code != "UNKNOWN":
                rows[code] = (repair_text(desc), "current code list")
    legacy = raw_dir / "ttc-subway-delay-codes.xlsx"
    if legacy.exists():
        sheet = pd.read_excel(legacy, header=None, dtype=str)
        # Header cells read "SUB RMENU CODE" / "SRT RMENU CODE"; the description
        # is in the next column.
        for r_idx, c_idx in zip(*((sheet.apply(lambda col: col.str.contains("RMENU CODE", na=False))).values.nonzero())):
            for code, desc in zip(sheet.iloc[r_idx + 1 :, c_idx], sheet.iloc[r_idx + 1 :, c_idx + 1]):
                code = normalise_code(code)
                if code != "UNKNOWN" and code not in rows:
                    rows[code] = (repair_text(desc), "legacy code list")
    return pd.DataFrame(
        [(c, d, s) for c, (d, s) in sorted(rows.items())],
        columns=["code", "description", "description_source"],
    )


def build_dim_cause(codes_in_data: pd.Series, code_lists: pd.DataFrame) -> pd.DataFrame:
    """One row per code seen in the data, with description, category and mode."""
    seen = sorted(set(codes_in_data.dropna()) | {"UNKNOWN"})
    lookup = code_lists.set_index("code")
    records = []
    for code in seen:
        if code in lookup.index:
            desc, source = lookup.at[code, "description"], lookup.at[code, "description_source"]
        elif code == "UNKNOWN":
            desc, source = "Code not recorded", "not recorded"
        else:
            desc, source = "Undocumented code", "undocumented"
        category = CATEGORY_BY_PREFIX.get(code[:1], "Other / unknown") if code != "UNKNOWN" else "Other / unknown"
        mode = MODE_BY_SECOND_LETTER.get(code[1:2], "Unknown") if code != "UNKNOWN" else "Unknown"
        records.append((code, desc, source, category, mode))
    out = pd.DataFrame(records, columns=["cause_code", "cause_description", "description_source", "cause_category", "cause_mode"])
    out.insert(0, "cause_key", range(1, len(out) + 1))
    out["cause_label"] = out["cause_code"] + " - " + out["cause_description"]
    return out
