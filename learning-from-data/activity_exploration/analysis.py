import argparse
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REQUIRED = {"shift_id", "event_time", "iclass", "resolved_location"}


def load(path):
    p = Path(path)
    df = (
        pd.read_parquet(p)
        if p.suffix.lower() in {".parquet", ".pq"}
        else pd.read_csv(p)
    )
    missing = REQUIRED - set(df.columns)
    if missing:
        raise SystemExit(f"Missing columns: {sorted(missing)}")
    df["event_time"] = pd.to_datetime(df["event_time"], errors="coerce")
    return df.sort_values(["shift_id", "event_time"]).reset_index(drop=True)


def heatmap(m, title, path):
    if m.empty:
        return
    fig, ax = plt.subplots(figsize=(8, 6))
    im = ax.imshow(m.values, aspect="auto")
    fig.colorbar(im, ax=ax, label="Probability")
    ax.set_title(title)
    ax.set_xlabel("Next")
    ax.set_ylabel("Current")
    ax.set_xticks(range(len(m.columns)))
    ax.set_xticklabels(m.columns, rotation=45, ha="right")
    ax.set_yticks(range(len(m.index)))
    ax.set_yticklabels(m.index)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="/data/canonical_events.parquet")
    ap.add_argument("--out", default="/outputs/activity_exploration")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    df = load(a.input)
    g = df.groupby("shift_id", sort=False)
    shifts = g.agg(
        total_events=("iclass", "size"),
        start=("event_time", "min"),
        end=("event_time", "max"),
        distinct_locations=("resolved_location", lambda x: x.dropna().nunique()),
    ).reset_index()
    shifts["duration_hours"] = (
        shifts["end"] - shifts["start"]
    ).dt.total_seconds() / 3600
    shifts["events_per_hour"] = shifts["total_events"] / shifts[
        "duration_hours"
    ].replace(0, np.nan)
    shifts.to_csv(out / "shift_activity_features.csv", index=False)

    x = df.copy()
    x["prev_class"] = x.groupby("shift_id")["iclass"].shift()
    ct = (
        x.dropna(subset=["prev_class"])
        .groupby(["prev_class", "iclass"])
        .size()
        .rename("count")
        .reset_index()
    )
    ct["from_total"] = ct.groupby("prev_class")["count"].transform("sum")
    ct["probability"] = ct["count"] / ct["from_total"]
    ct.to_csv(out / "class_transition_probabilities.csv", index=False)
    cm = ct.pivot(index="prev_class", columns="iclass", values="probability").fillna(0)
    cm.to_csv(out / "class_transition_probability_matrix.csv")
    heatmap(
        cm,
        "Event-class transition probabilities",
        out / "class_transition_probabilities.png",
    )

    loc = x.dropna(subset=["resolved_location"]).copy()
    loc["prev_location"] = loc.groupby("shift_id")["resolved_location"].shift()
    lc = loc.dropna(subset=["prev_location"])
    lc = lc[lc["resolved_location"] != lc["prev_location"]]
    counts = (
        lc.groupby(["prev_location", "resolved_location"])
        .size()
        .rename("count")
        .reset_index()
    )
    if not counts.empty:
        counts["from_total"] = counts.groupby("prev_location")["count"].transform("sum")
        counts["probability"] = counts["count"] / counts["from_total"]
    counts.to_csv(out / "location_transition_probabilities.csv", index=False)

    vals = shifts["events_per_hour"].replace([np.inf, -np.inf], np.nan).dropna()
    if len(vals):
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.hist(vals, bins=40)
        ax.set_title("Events per hour")
        ax.set_xlabel("Events/hour")
        ax.set_ylabel("Shifts")
        fig.tight_layout()
        fig.savefig(out / "events_per_hour.png", dpi=160)
        plt.close(fig)


if __name__ == "__main__":
    main()
