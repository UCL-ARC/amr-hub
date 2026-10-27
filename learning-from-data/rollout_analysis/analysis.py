import argparse
from pathlib import Path
from collections import Counter, defaultdict
import pandas as pd
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

SEEDS = [1, 2, 3, 5, 10]


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
    if "role" not in df:
        df["role"] = "unknown"
    if "roster_unit" not in df:
        df["roster_unit"] = "unknown"
    df["time_bucket"] = (df["event_time"].dt.hour // 6).astype(int)
    return df.sort_values(["shift_id", "event_time"]).reset_index(drop=True)


def split_ids(df):
    ids = np.array(sorted(df.shift_id.unique()))
    rng = np.random.default_rng(42)
    rng.shuffle(ids)
    n = max(1, int(0.8 * len(ids)))
    return set(ids[:n]), set(ids[n:])


def transitions(df):
    rows = []
    for sid, g in df.groupby("shift_id"):
        s = g.iclass.astype(str).tolist()
        tb = g.time_bucket.tolist()
        role = str(g.role.iloc[0])
        unit = str(g.roster_unit.iloc[0])
        for i in range(1, len(s) - 1):
            rows.append(
                {
                    "prev": s[i - 1],
                    "cur": s[i],
                    "nxt": s[i + 1],
                    "time_bucket": tb[i],
                    "role": role,
                    "roster_unit": unit,
                }
            )
    return pd.DataFrame(rows)


def fit(rows, context=None):
    d = defaultdict(Counter)
    global_counts = Counter()
    for _, r in rows.iterrows():
        k = (
            (r["prev"], r["cur"])
            if context is None
            else (r[context], r["prev"], r["cur"])
        )
        d[k][r["nxt"]] += 1
        global_counts[r["nxt"]] += 1
    table = {k: v.most_common(1)[0][0] for k, v in d.items()}
    fallback = global_counts.most_common(1)[0][0] if global_counts else None
    return table, fallback


def tv(a, b):
    ca, cb = Counter(a), Counter(b)
    keys = set(ca) | set(cb)
    na = max(1, len(a))
    nb = max(1, len(b))
    return 0.5 * sum(abs(ca[k] / na - cb[k] / nb) for k in keys)


def rollout(g, seed, table, fallback, context=None):
    real = g.iclass.astype(str).tolist()
    if len(real) <= seed:
        return None
    gen = real[:seed]
    tbs = g.time_bucket.tolist()
    role = str(g.role.iloc[0])
    unit = str(g.roster_unit.iloc[0])
    for pos in range(seed, len(real)):
        prev = gen[-2] if len(gen) >= 2 else gen[-1]
        cur = gen[-1]
        c = (
            tbs[pos - 1]
            if context == "time_bucket"
            else role
            if context == "role"
            else unit
            if context == "roster_unit"
            else None
        )
        k = (prev, cur) if context is None else (c, prev, cur)
        gen.append(table.get(k, fallback))
    actual, pred = real[seed:], gen[seed:]
    acc = float(np.mean(np.array(actual, dtype=object) == np.array(pred, dtype=object)))
    prefix = 0
    for x, y in zip(actual, pred):
        if x != y:
            break
        prefix += 1
    return acc, tv(actual, pred), prefix


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="/data/canonical_events.parquet")
    ap.add_argument("--out", default="/outputs/rollout_analysis")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    df = load(a.input)
    tr_ids, te_ids = split_ids(df)
    tr = transitions(df[df.shift_id.isin(tr_ids)])
    specs = [
        ("global", None),
        ("time", "time_bucket"),
        ("role", "role"),
        ("unit", "roster_unit"),
    ]
    fitted = {name: (fit(tr, c), c) for name, c in specs}
    rows = []
    for sid, g in df[df.shift_id.isin(te_ids)].groupby("shift_id"):
        for seed in SEEDS:
            for name, (model, c) in fitted.items():
                r = rollout(g, seed, *model, context=c)
                if r:
                    rows.append(
                        {
                            "shift_id": sid,
                            "seed": seed,
                            "policy": name,
                            "accuracy": r[0],
                            "tv_distance": r[1],
                            "correct_prefix": r[2],
                        }
                    )
    per = pd.DataFrame(rows)
    per.to_csv(out / "rollout_per_shift_by_seed.csv", index=False)
    if per.empty:
        return
    summ = per.groupby(["seed", "policy"], as_index=False).agg(
        accuracy=("accuracy", "mean"),
        tv_distance=("tv_distance", "mean"),
        correct_prefix=("correct_prefix", "mean"),
        n_shifts=("shift_id", "nunique"),
    )
    summ.to_csv(out / "rollout_summary_by_seed.csv", index=False)
    for metric, title, name in [
        ("accuracy", "Rollout accuracy", "rollout_accuracy_by_seed.png"),
        ("tv_distance", "Composition deviation", "rollout_deviation_by_seed.png"),
        ("correct_prefix", "Correct prefix length", "correct_prefix_by_seed.png"),
    ]:
        fig, ax = plt.subplots(figsize=(8, 5))
        for policy, g in summ.groupby("policy"):
            ax.plot(g.seed, g[metric], marker="o", label=policy)
        ax.set_xlabel("Seed events")
        ax.set_ylabel(metric)
        ax.set_title(title)
        ax.legend()
        fig.tight_layout()
        fig.savefig(out / name, dpi=160)
        plt.close(fig)


if __name__ == "__main__":
    main()
