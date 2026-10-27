import argparse
from pathlib import Path
import pandas as pd
import numpy as np


def load(path):
    p = Path(path)
    df = (
        pd.read_parquet(p)
        if p.suffix.lower() in {".parquet", ".pq"}
        else pd.read_csv(p)
    )
    need = {"shift_id", "event_time", "iclass"}
    missing = need - set(df.columns)
    if missing:
        raise SystemExit(f"Missing columns: {sorted(missing)}")
    df["event_time"] = pd.to_datetime(df["event_time"], errors="coerce")
    return df.sort_values(["shift_id", "event_time"]).reset_index(drop=True)


def prep(df):
    x = df.copy()
    x["prev_class"] = x.groupby("shift_id")["iclass"].shift()
    x["next_class"] = x.groupby("shift_id")["iclass"].shift(-1)
    x["time_bucket"] = (x["event_time"].dt.hour // 6).astype("Int64")
    if "role" not in x:
        x["role"] = "unknown"
    if "roster_unit" not in x:
        x["roster_unit"] = "unknown"
    if "resolved_location" in x:
        x["next_location"] = x.groupby("shift_id")["resolved_location"].shift(-1)
        x["next_room_change"] = np.where(
            x["resolved_location"].notna()
            & x["next_location"].notna()
            & (x["resolved_location"] != x["next_location"]),
            x["next_location"],
            pd.NA,
        )
    return x


def split(df):
    ids = np.array(sorted(df["shift_id"].dropna().unique()))
    rng = np.random.default_rng(42)
    rng.shuffle(ids)
    n = max(1, int(0.8 * len(ids)))
    return df[df.shift_id.isin(set(ids[:n]))], df[df.shift_id.isin(set(ids[n:]))]


def evaluate(train, test, keys, target, name):
    t = train.dropna(subset=[target] + keys)
    fb = t[target].mode().iat[0] if len(t) else None
    table = {}
    if keys:
        for k, g in t.groupby(keys, dropna=False):
            if not isinstance(k, tuple):
                k = (k,)
            table[k] = g[target].value_counts().idxmax()
    q = test.dropna(subset=[target])
    preds = []
    unseen = 0
    for _, r in q.iterrows():
        k = tuple(r[c] for c in keys)
        if keys and k not in table:
            unseen += 1
        preds.append(table.get(k, fb) if keys else fb)
    acc = (
        float(
            np.mean(np.array(preds, dtype=object) == q[target].to_numpy(dtype=object))
        )
        if len(q)
        else np.nan
    )
    return {
        "task": target,
        "model": name,
        "n": len(q),
        "accuracy": acc,
        "unseen_fraction": unseen / len(q) if len(q) else np.nan,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="/data/canonical_events.parquet")
    ap.add_argument("--out", default="/outputs/learnability")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    df = prep(load(a.input))
    tr, te = split(df)
    models = [
        ([], "majority"),
        (["iclass"], "current"),
        (["prev_class", "iclass"], "previous_current"),
        (["prev_class", "iclass", "time_bucket", "role"], "plus_time_role"),
        (
            ["prev_class", "iclass", "time_bucket", "role", "roster_unit"],
            "full_context",
        ),
    ]
    tasks = ["next_class"] + (
        ["next_location", "next_room_change"]
        if "resolved_location" in df.columns
        else []
    )
    rows = [evaluate(tr, te, k, t, n) for t in tasks for k, n in models]
    pd.DataFrame(rows).to_csv(out / "pooled_learnability.csv", index=False)
    pd.DataFrame({"train_shift_id": sorted(tr.shift_id.unique())}).to_csv(
        out / "train_shifts.csv", index=False
    )
    pd.DataFrame({"test_shift_id": sorted(te.shift_id.unique())}).to_csv(
        out / "test_shifts.csv", index=False
    )


if __name__ == "__main__":
    main()
