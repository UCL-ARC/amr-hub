import argparse
from pathlib import Path
from collections import Counter
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.cluster import KMeans
from sklearn.metrics import calinski_harabasz_score
from sklearn.decomposition import PCA


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
    return df.sort_values(["shift_id", "event_time"])


def make_features(df):
    rows = []
    for sid, g in df.groupby("shift_id", sort=False):
        s = g["iclass"].astype(str).tolist()
        c = Counter(tuple(s[i : i + 3]) for i in range(max(0, len(s) - 2)))
        total = sum(c.values()) or 1
        row = {"shift_id": sid}
        row.update({"tri__" + "__".join(k): v / total for k, v in c.items()})
        rows.append(row)
    return pd.DataFrame(rows).fillna(0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="/data/canonical_events.parquet")
    ap.add_argument("--out", default="/outputs/sequence_clustering")
    ap.add_argument("--k-min", type=int, default=2)
    ap.add_argument("--k-max", type=int, default=6)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    f = make_features(load(a.input))
    f.to_csv(out / "trigram_features.csv", index=False)
    X = f.drop(columns="shift_id").values
    scores = []
    models = {}
    for k in range(a.k_min, a.k_max + 1):
        if len(X) <= k:
            continue
        m = KMeans(n_clusters=k, random_state=42, n_init=20).fit(X)
        models[k] = m
        scores.append(
            {"k": k, "calinski_harabasz": calinski_harabasz_score(X, m.labels_)}
        )
    s = pd.DataFrame(scores)
    s.to_csv(out / "cluster_scores.csv", index=False)
    if s.empty:
        return
    best = int(s.loc[s["calinski_harabasz"].idxmax(), "k"])
    m = models[best]
    pd.DataFrame({"shift_id": f["shift_id"], "cluster": m.labels_}).to_csv(
        out / "cluster_assignments.csv", index=False
    )
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.plot(s["k"], s["calinski_harabasz"], marker="o")
    ax.set_xlabel("k")
    ax.set_ylabel("Calinski-Harabasz")
    ax.set_title("Cluster screening")
    fig.tight_layout()
    fig.savefig(out / "cluster_scores.png", dpi=160)
    plt.close(fig)
    if X.shape[1] >= 2:
        z = PCA(n_components=2, random_state=42).fit_transform(X)
        fig, ax = plt.subplots(figsize=(7, 5))
        ax.scatter(z[:, 0], z[:, 1], c=m.labels_, s=10)
        ax.set_title(f"PCA view, k={best}")
        fig.tight_layout()
        fig.savefig(out / "cluster_pca.png", dpi=160)
        plt.close(fig)


if __name__ == "__main__":
    main()
