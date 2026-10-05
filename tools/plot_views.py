"""Draw the report's two main views as PNGs for the README, from the pipeline's outputs.

Run after `python3 -m ttc_delay all` (or `run --sample`): reads the warehouse exports in data/export/, writes docs/cause-pareto.png and docs/station-ranking.png.
Needs matplotlib (not in requirements.txt, since the pipeline itself doesn't use it).
"""
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"


def cause_minutes():
    """Delay minutes per cause code over every year, most first (from the warehouse export)."""
    with open(ROOT / "data" / "export" / "dim_cause.csv", newline="") as f:
        code = {r["cause_key"]: r["cause_code"] for r in csv.DictReader(f)}
    minutes = {}
    with open(ROOT / "data" / "export" / "fact_delay.csv", newline="") as f:
        for r in csv.DictReader(f):
            m = float(r["min_delay"] or 0)
            if m > 0:
                minutes[r["cause_key"]] = minutes.get(r["cause_key"], 0) + m
    return sorted(((code.get(k, k), m) for k, m in minutes.items()), key=lambda pair: -pair[1])


def cause_pareto():
    causes = cause_minutes()
    total = sum(m for _, m in causes)
    cumulative, running = [], 0
    for _, m in causes:
        running += m
        cumulative.append(100 * running / total)
    to80 = next(i for i, c in enumerate(cumulative, 1) if c >= 80)
    fig, ax = plt.subplots(figsize=(10, 4.2))
    ax.bar(range(len(causes)), [m for _, m in causes], width=1.0, color="#4c72b0")
    ax.set_yscale("log")
    ax.set_ylabel("Delay minutes (log scale)")
    ax.set_xlabel("Causes, most minutes first")
    share = ax.twinx()
    share.plot(range(len(causes)), cumulative, color="#dd8452")
    share.axhline(80, color="grey", linestyle="--", linewidth=1)
    share.axvline(to80 - 1, color="grey", linestyle=":", linewidth=1)
    share.annotate(f"{to80} causes reach 80%", (to80 - 1, 80), xytext=(8, -16), textcoords="offset points")
    share.set_ylim(0, 100)
    share.set_ylabel("Cumulative share of minutes (%)")
    ax.set_title(f"{total:,.0f} delay minutes by cause, {len(causes)} causes with minutes")
    fig.tight_layout()
    fig.savefig(DOCS / "cause-pareto.png", dpi=130)
    plt.close(fig)


def station_ranking():
    with open(ROOT / "data" / "export" / "station_ranking.csv", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["period"] == "Last 36 months"]
    incidents = [float(r["incidents"]) for r in rows]
    shrunk = [float(r["shrunk_minutes_per_incident"]) for r in rows]
    busiest = sorted(rows, key=lambda r: -float(r["incidents"]))[:5]
    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.scatter(incidents, shrunk, s=18, color="#8c8c8c")
    key = []
    for i, r in enumerate(busiest, 1):
        x, y = float(r["incidents"]), float(r["shrunk_minutes_per_incident"])
        ax.scatter([x], [y], s=30, color="#c44e52")
        ax.annotate(str(i), (x, y), fontsize=8, xytext=(4, 4), textcoords="offset points", color="#c44e52")
        key.append(f"{i}  {r['station_label']}: rank {r['shrunk_rank']}")
    ax.text(0.02, 0.97, "\n".join(key), transform=ax.transAxes, va="top", fontsize=8,
            bbox={"boxstyle": "round", "facecolor": "white", "edgecolor": "#cccccc"})
    ax.set_xscale("log")
    ax.set_xlabel("Incidents logged in the last 36 months (log scale)")
    ax.set_ylabel("Minutes per incident (empirical Bayes)")
    ax.set_title(f"The 5 stations with the most incidents, and their rank of {len(rows)} on minutes per incident")
    fig.tight_layout()
    fig.savefig(DOCS / "station-ranking.png", dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    DOCS.mkdir(exist_ok=True)
    cause_pareto()
    station_ranking()
    print("wrote docs/cause-pareto.png and docs/station-ranking.png")
