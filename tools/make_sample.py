"""Write a small sample of the real source files to data/sample/.

Keeps every Nth row of every sheet (default 25), with the original file
names, sheet names and column layout, so the pipeline's format handling runs
offline on realistic data. Usage: ``python3 tools/make_sample.py [--every 25]``.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ttc_delay.config import RAW_DIR, SAMPLE_DIR  # noqa: E402
from ttc_delay.extract import delay_files  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--every", type=int, default=25)
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--out", type=Path, default=SAMPLE_DIR)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for path in delay_files(args.raw_dir):
        target = args.out / path.name
        if path.suffix.lower() == ".csv":
            df = pd.read_csv(path, dtype=str, keep_default_na=False)
            df.iloc[:: args.every].to_csv(target, index=False)
        else:
            sheets = pd.read_excel(path, sheet_name=None, dtype=object)
            with pd.ExcelWriter(target, engine="openpyxl") as writer:
                for name, df in sheets.items():
                    df.iloc[:: args.every].to_excel(writer, sheet_name=name, index=False)
        print(f"wrote {target}")
    for name in ("code-descriptions.csv", "ttc-subway-delay-codes.xlsx"):
        if (args.raw_dir / name).exists():
            shutil.copy(args.raw_dir / name, args.out / name)


if __name__ == "__main__":
    main()
