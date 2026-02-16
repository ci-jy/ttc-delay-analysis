"""Download the TTC subway delay files from Toronto Open Data (CKAN API)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import requests

from .config import CKAN_BASE, CKAN_PACKAGE, RAW_DIR

TIMEOUT = 120


def package_resources(session: requests.Session | None = None) -> list[dict]:
    session = session or requests.Session()
    resp = session.get(
        f"{CKAN_BASE}/api/3/action/package_show", params={"id": CKAN_PACKAGE}, timeout=TIMEOUT
    )
    resp.raise_for_status()
    return resp.json()["result"]["resources"]


def select_resources(resources: list[dict]) -> list[dict]:
    """Keep the yearly delay files (XLSX up to 2024, CSV since 2025) and code lists.

    The CKAN package also offers the same datastore tables as XLSX/XML/JSON
    dumps; only the file downloads are needed.
    """
    chosen = []
    for res in resources:
        url = res.get("url", "")
        fmt = (res.get("format") or "").upper()
        if "/download/" not in url:
            continue
        name = url.rsplit("/", 1)[-1].lower()
        is_delay_xlsx = fmt == "XLSX" and re.search(r"delay.*20\d\d", name)
        is_delay_csv = fmt == "CSV" and "delay" in name
        is_codes = name in ("code-descriptions.csv", "ttc-subway-delay-codes.xlsx")
        if is_delay_xlsx or is_delay_csv or is_codes:
            chosen.append(res)
    return chosen


def datastore_row_counts(resources: list[dict], session: requests.Session) -> dict[str, int]:
    """Record count of each datastore table, used to reconcile the CSV download."""
    counts = {}
    for res in resources:
        if res.get("datastore_active"):
            resp = session.get(
                f"{CKAN_BASE}/api/3/action/datastore_search",
                params={"resource_id": res["id"], "limit": 0},
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            counts[res["name"]] = resp.json()["result"]["total"]
    return counts


def download_all(raw_dir: Path = RAW_DIR, force: bool = False) -> Path:
    """Fetch every selected resource into ``raw_dir`` and write ``manifest.json``."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    resources = package_resources(session)
    files = []
    for res in select_resources(resources):
        filename = res["url"].rsplit("/", 1)[-1]
        target = raw_dir / filename
        if force or not target.exists():
            with session.get(res["url"], stream=True, timeout=TIMEOUT) as resp:
                resp.raise_for_status()
                tmp = target.with_suffix(target.suffix + ".part")
                with open(tmp, "wb") as fh:
                    for chunk in resp.iter_content(1 << 16):
                        fh.write(chunk)
                tmp.replace(target)
        files.append(
            {
                "file": filename,
                "resource_id": res["id"],
                "resource_name": res["name"],
                "format": res.get("format"),
                "last_modified": res.get("last_modified"),
                "url": res["url"],
            }
        )
    manifest = {
        "package": CKAN_PACKAGE,
        "files": files,
        "datastore_row_counts": datastore_row_counts(resources, session),
    }
    path = raw_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2))
    return path
