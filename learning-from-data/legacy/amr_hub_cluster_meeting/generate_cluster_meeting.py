#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import math
from pathlib import Path

import numpy as np
import pandas as pd


REQUIRED = {
    "trigram_features": "per_shift_class_trigram_features.csv",
    "assignments": "trigram_cluster_assignments.csv",
    "top_patterns": "trigram_cluster_top_patterns.csv",
    "per_shift_transitions": "per_shift_class_transition_probabilities_long.csv",
}


def esc(x) -> str:
    return html.escape(str(x))


def short_pattern(x: str) -> str:
    return (
        str(x)
        .replace(" -> ", "→")
        .replace("Door Message", "DOOR")
        .replace("Workstation", "WS")
        .replace("Flowsheet", "FS")
    )


def discover_input_folder(input_dir: Path) -> Path:
    """Use requested input dir, otherwise find a folder under /outputs with all required files."""
    if all((input_dir / name).exists() for name in REQUIRED.values()):
        return input_dir

    root = Path("/outputs")
    if root.exists():
        candidates = []
        for p in root.rglob(REQUIRED["assignments"]):
            parent = p.parent
            if all((parent / name).exists() for name in REQUIRED.values()):
                candidates.append(parent)
        if len(candidates) == 1:
            print(
                f"[input] requested folder incomplete; using discovered folder: {candidates[0]}"
            )
            return candidates[0]
        if len(candidates) > 1:
            raise FileNotFoundError(
                "Multiple analysis folders contain the required files. Re-run with --input and choose one:\n  "
                + "\n  ".join(str(x) for x in candidates)
            )

    missing = [name for name in REQUIRED.values() if not (input_dir / name).exists()]
    raise FileNotFoundError(
        f"Could not find required activity-exploration files in {input_dir}. Missing: {missing}"
    )


def load_inputs(input_dir: Path):
    F = pd.read_csv(input_dir / REQUIRED["trigram_features"])
    A = pd.read_csv(input_dir / REQUIRED["assignments"])
    T = pd.read_csv(input_dir / REQUIRED["top_patterns"])
    P = pd.read_csv(input_dir / REQUIRED["per_shift_transitions"])

    for df, name in [
        (F, "trigram features"),
        (A, "cluster assignments"),
        (P, "per-shift transitions"),
    ]:
        if "shift_id" not in df.columns:
            raise ValueError(f"{name} file has no shift_id column")
    if "cluster" not in A.columns:
        raise ValueError("trigram_cluster_assignments.csv has no cluster column")

    return F, A, T, P


def cluster_names(T: pd.DataFrame, clusters: list[int]) -> dict[int, str]:
    names = {}
    if {"cluster", "pattern"}.issubset(T.columns):
        sort_cols = [c for c in ["cluster", "rank_within_cluster"] if c in T.columns]
        TT = T.sort_values(sort_cols) if sort_cols else T
        for c, g in TT.groupby("cluster"):
            pats = [short_pattern(x) for x in g["pattern"].dropna().astype(str).head(2)]
            if pats:
                names[int(c)] = " / ".join(pats)
    for c in clusters:
        names.setdefault(int(c), "")
    return names


def make_cluster_embedding(
    F: pd.DataFrame, A: pd.DataFrame, T: pd.DataFrame, out_svg: Path, out_csv: Path
):
    tri = [c for c in F.columns if c.startswith("tri_")]
    if len(tri) < 2:
        raise ValueError("Need at least two trigram feature columns for the dot plot")

    df = (
        A[["shift_id", "cluster"]]
        .merge(F[["shift_id", *tri]], on="shift_id", how="inner")
        .dropna()
    )
    if len(df) < 3:
        raise ValueError("Not enough clustered shifts to build the dot plot")

    X = df[tri].to_numpy(float)
    Xc = X - X.mean(axis=0, keepdims=True)
    _, _, Vt = np.linalg.svd(Xc, full_matrices=False)
    Z = Xc @ Vt[:2].T

    # Clip display coordinates at the 1st/99th percentiles; all points are kept.
    Zdisplay = Z.copy()
    for j in range(2):
        lo, hi = np.quantile(Zdisplay[:, j], [0.01, 0.99])
        if hi > lo:
            Zdisplay[:, j] = np.clip(Zdisplay[:, j], lo, hi)

    embedding = df[["shift_id", "cluster"]].copy()
    embedding["embedding_1"] = Z[:, 0]
    embedding["embedding_2"] = Z[:, 1]
    embedding.to_csv(out_csv, index=False)

    clusters = sorted(
        pd.to_numeric(df["cluster"], errors="coerce").dropna().astype(int).unique()
    )
    names = cluster_names(T, clusters)
    palette = [
        "#2563eb",
        "#d97706",
        "#059669",
        "#7c3aed",
        "#dc2626",
        "#0891b2",
        "#4f46e5",
        "#65a30d",
    ]
    colors = {c: palette[i % len(palette)] for i, c in enumerate(clusters)}

    W, H = 1200, 820
    ml, mr, mt, mb = 85, 55, 82, 92
    xmin, ymin = Zdisplay.min(axis=0)
    xmax, ymax = Zdisplay.max(axis=0)
    xx = ml + (Zdisplay[:, 0] - xmin) / (xmax - xmin + 1e-12) * (W - ml - mr)
    yy = H - mb - (Zdisplay[:, 1] - ymin) / (ymax - ymin + 1e-12) * (H - mt - mb)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{W / 2}" y="31" text-anchor="middle" font-family="Arial" font-size="24" font-weight="bold">Shift clusters from three-event activity patterns</text>',
        f'<text x="{W / 2}" y="56" text-anchor="middle" font-family="Arial" font-size="13" fill="#555">One dot per rostered shift</text>',
        f'<line x1="{ml}" y1="{H - mb}" x2="{W - mr}" y2="{H - mb}" stroke="#999"/>',
        f'<line x1="{ml}" y1="{mt}" x2="{ml}" y2="{H - mb}" stroke="#999"/>',
        f'<text x="{(ml + W - mr) / 2}" y="{H - 32}" text-anchor="middle" font-family="Arial" font-size="12">Embedding dimension 1</text>',
        f'<text x="24" y="{(mt + H - mb) / 2}" transform="rotate(-90 24 {(mt + H - mb) / 2})" text-anchor="middle" font-family="Arial" font-size="12">Embedding dimension 2</text>',
    ]

    cluster_values = (
        pd.to_numeric(df["cluster"], errors="coerce").astype(int).to_numpy()
    )
    for i, c in enumerate(cluster_values):
        parts.append(
            f'<circle cx="{xx[i]:.2f}" cy="{yy[i]:.2f}" r="2.6" fill="{colors[c]}" opacity="0.34"/>'
        )

    for c in clusters:
        mask = cluster_values == c
        cx = float(np.median(xx[mask]))
        cy = float(np.median(yy[mask]))
        subtitle = names.get(c, "")
        width = 255
        height = 48 if subtitle else 30
        x0 = min(max(cx + 11, ml + 5), W - width - 8)
        y0 = min(max(cy - 29, mt + 5), H - mb - height - 5)
        parts.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="7" fill="{colors[c]}" stroke="white" stroke-width="2"/>'
        )
        parts.append(
            f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{width}" height="{height}" rx="5" fill="white" stroke="{colors[c]}" opacity="0.94"/>'
        )
        parts.append(
            f'<text x="{x0 + 9:.1f}" y="{y0 + 18:.1f}" font-family="Arial" font-size="12" font-weight="bold" fill="{colors[c]}">Cluster {c}</text>'
        )
        if subtitle:
            parts.append(
                f'<text x="{x0 + 9:.1f}" y="{y0 + 36:.1f}" font-family="Arial" font-size="10" fill="#444">{esc(subtitle[:46])}</text>'
            )

    lx, ly = W - 245, 94
    sizes = pd.Series(cluster_values).value_counts().to_dict()
    for k, c in enumerate(clusters):
        parts.append(f'<circle cx="{lx}" cy="{ly + 23 * k}" r="5" fill="{colors[c]}"/>')
        parts.append(
            f'<text x="{lx + 12}" y="{ly + 4 + 23 * k}" font-family="Arial" font-size="11">Cluster {c} ({sizes.get(c, 0):,} shifts)</text>'
        )

    parts.append(
        '<text x="28" y="790" font-family="Arial" font-size="11" fill="#555">Axes are embedding dimensions, not clinical variables.</text>'
    )
    parts.append("</svg>")
    out_svg.write_text("\n".join(parts), encoding="utf-8")


def aggregate_cluster_transitions(A: pd.DataFrame, P: pd.DataFrame, outdir: Path):
    cols_needed = {"shift_id", "from_class", "to_class", "transition_count"}
    missing = cols_needed - set(P.columns)
    if missing:
        raise ValueError(
            f"per_shift transition CSV is missing columns: {sorted(missing)}"
        )

    a = A[["shift_id", "cluster"]].copy()
    df = P.merge(a, on="shift_id", how="inner")
    df["transition_count"] = pd.to_numeric(
        df["transition_count"], errors="coerce"
    ).fillna(0)
    counts = (
        df.groupby(["cluster", "from_class", "to_class"], as_index=False)[
            "transition_count"
        ]
        .sum()
        .sort_values(
            ["cluster", "from_class", "transition_count"], ascending=[True, True, False]
        )
    )
    counts["from_total"] = counts.groupby(["cluster", "from_class"])[
        "transition_count"
    ].transform("sum")
    counts["probability"] = counts["transition_count"] / counts["from_total"].replace(
        0, np.nan
    )
    counts.to_csv(outdir / "cluster_transition_probabilities_long.csv", index=False)

    for c, g in counts.groupby("cluster"):
        m = g.pivot(
            index="from_class", columns="to_class", values="probability"
        ).fillna(0)
        m.to_csv(outdir / f"cluster_{int(c)}_transition_probability_matrix.csv")
    return counts


def make_transition_matrix_svg(counts: pd.DataFrame, T: pd.DataFrame, out_svg: Path):
    clusters = sorted(
        pd.to_numeric(counts["cluster"], errors="coerce").dropna().astype(int).unique()
    )
    names = cluster_names(T, clusters)
    classes = sorted(
        set(counts["from_class"].astype(str)) | set(counts["to_class"].astype(str))
    )
    n = len(classes)
    if n == 0 or not clusters:
        raise ValueError("No cluster transitions available")

    ncols = 2 if len(clusters) > 1 else 1
    nrows = math.ceil(len(clusters) / ncols)
    panel_w, panel_h = 560, 420
    W, H = ncols * panel_w, 70 + nrows * panel_h + 35
    cell = min(90, 270 / max(n, 1))

    lookup = {
        (int(r.cluster), str(r.from_class), str(r.to_class)): (
            float(r.probability),
            int(r.transition_count),
        )
        for r in counts.itertuples(index=False)
    }

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{W / 2}" y="30" text-anchor="middle" font-family="Arial" font-size="24" font-weight="bold">Next-event transition probabilities within each cluster</text>',
        f'<text x="{W / 2}" y="53" text-anchor="middle" font-family="Arial" font-size="12" fill="#555">Rows: current class; columns: next class</text>',
    ]

    for k, c in enumerate(clusters):
        col, row = k % ncols, k // ncols
        ox, oy = col * panel_w + 35, 75 + row * panel_h
        subtitle = names.get(c, "")
        parts.append(
            f'<text x="{ox + panel_w / 2 - 35}" y="{oy + 20}" text-anchor="middle" font-family="Arial" font-size="17" font-weight="bold">Cluster {c}</text>'
        )
        if subtitle:
            parts.append(
                f'<text x="{ox + panel_w / 2 - 35}" y="{oy + 39}" text-anchor="middle" font-family="Arial" font-size="10" fill="#555">{esc(subtitle[:70])}</text>'
            )

        gx, gy = ox + 165, oy + 82
        for j, cl in enumerate(classes):
            label = short_pattern(cl)
            parts.append(
                f'<text x="{gx + j * cell + cell / 2:.1f}" y="{gy - 12}" text-anchor="middle" font-family="Arial" font-size="10">{esc(label)}</text>'
            )
        for i, fr in enumerate(classes):
            label = short_pattern(fr)
            parts.append(
                f'<text x="{gx - 10}" y="{gy + i * cell + cell / 2 + 4:.1f}" text-anchor="end" font-family="Arial" font-size="10">{esc(label)}</text>'
            )
            for j, to in enumerate(classes):
                p, cnt = lookup.get((c, fr, to), (0.0, 0))
                shade = int(245 - 150 * max(0, min(1, p)))
                fill = f"rgb({shade},{shade + 5 if shade < 250 else shade},{255})"
                parts.append(
                    f'<rect x="{gx + j * cell:.1f}" y="{gy + i * cell:.1f}" width="{cell:.1f}" height="{cell:.1f}" fill="{fill}" stroke="white"/>'
                )
                parts.append(
                    f'<text x="{gx + j * cell + cell / 2:.1f}" y="{gy + i * cell + cell / 2 - 2:.1f}" text-anchor="middle" font-family="Arial" font-size="12" font-weight="bold">{p * 100:.0f}%</text>'
                )
                parts.append(
                    f'<text x="{gx + j * cell + cell / 2:.1f}" y="{gy + i * cell + cell / 2 + 13:.1f}" text-anchor="middle" font-family="Arial" font-size="8" fill="#555">n={cnt:,}</text>'
                )

    parts.append(
        '<text x="25" y="{}" font-family="Arial" font-size="11" fill="#555">Within-cluster transition probabilities (in-sample).</text>'.format(
            H - 13
        )
    )
    parts.append("</svg>")
    out_svg.write_text("\n".join(parts), encoding="utf-8")


def predictability_metrics(counts: pd.DataFrame, A: pd.DataFrame, out_csv: Path):
    rows = []
    for c, g in counts.groupby("cluster"):
        total = float(g["transition_count"].sum())
        top1 = 0.0
        top2 = 0.0
        entropy_weighted = 0.0
        for _, r in g.groupby("from_class"):
            vals = r["transition_count"].to_numpy(float)
            row_total = vals.sum()
            if row_total <= 0:
                continue
            probs = vals / row_total
            ordered = np.sort(vals)[::-1]
            top1 += ordered[:1].sum()
            top2 += ordered[:2].sum()
            entropy = -float(np.sum(probs[probs > 0] * np.log2(probs[probs > 0])))
            entropy_weighted += row_total * entropy
        n_shifts = int((pd.to_numeric(A["cluster"], errors="coerce") == int(c)).sum())
        rows.append(
            {
                "cluster": int(c),
                "n_shifts": n_shifts,
                "n_class_transitions": int(total),
                "top1_transition_concentration": top1 / total if total else np.nan,
                "top2_transition_coverage": top2 / total if total else np.nan,
                "conditional_entropy_bits": entropy_weighted / total
                if total
                else np.nan,
            }
        )

    out = pd.DataFrame(rows).sort_values("cluster")
    out.to_csv(out_csv, index=False)
    return out


def make_predictability_svg(metrics: pd.DataFrame, T: pd.DataFrame, out_svg: Path):
    clusters = metrics["cluster"].astype(int).tolist()
    names = cluster_names(T, clusters)
    W, H = 1120, 540
    ml, mr, mt, mb = 115, 60, 95, 95
    plot_w = W - ml - mr
    plot_h = H - mt - mb
    y0 = H - mb
    vals = metrics["top1_transition_concentration"].to_numpy(float)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{W / 2}" y="31" text-anchor="middle" font-family="Arial" font-size="24" font-weight="bold">Transition concentration by cluster</text>',
        f'<text x="{W / 2}" y="56" text-anchor="middle" font-family="Arial" font-size="12" fill="#555">Share of transitions to the most common next class</text>',
        f'<line x1="{ml}" y1="{y0}" x2="{W - mr}" y2="{y0}" stroke="#888"/>',
        f'<line x1="{ml}" y1="{mt}" x2="{ml}" y2="{y0}" stroke="#888"/>',
    ]
    for tick in np.linspace(0, 1, 6):
        y = y0 - tick * plot_h
        parts.append(
            f'<line x1="{ml}" y1="{y:.1f}" x2="{W - mr}" y2="{y:.1f}" stroke="#eee"/>'
        )
        parts.append(
            f'<text x="{ml - 10}" y="{y + 4:.1f}" text-anchor="end" font-family="Arial" font-size="10">{tick * 100:.0f}%</text>'
        )

    n = max(len(clusters), 1)
    slot = plot_w / n
    bw = min(100, slot * 0.55)
    palette = [
        "#2563eb",
        "#d97706",
        "#059669",
        "#7c3aed",
        "#dc2626",
        "#0891b2",
        "#4f46e5",
        "#65a30d",
    ]
    for i, (c, v) in enumerate(zip(clusters, vals)):
        x = ml + slot * (i + 0.5) - bw / 2
        h = max(0, min(1, v)) * plot_h
        color = palette[i % len(palette)]
        parts.append(
            f'<rect x="{x:.1f}" y="{y0 - h:.1f}" width="{bw:.1f}" height="{h:.1f}" fill="{color}" opacity="0.82" rx="4"/>'
        )
        parts.append(
            f'<text x="{x + bw / 2:.1f}" y="{y0 - h - 9:.1f}" text-anchor="middle" font-family="Arial" font-size="13" font-weight="bold">{v * 100:.1f}%</text>'
        )
        parts.append(
            f'<text x="{x + bw / 2:.1f}" y="{y0 + 19:.1f}" text-anchor="middle" font-family="Arial" font-size="11" font-weight="bold">Cluster {c}</text>'
        )
        subtitle = names.get(c, "")[:30]
        if subtitle:
            parts.append(
                f'<text x="{x + bw / 2:.1f}" y="{y0 + 36:.1f}" text-anchor="middle" font-family="Arial" font-size="9" fill="#555">{esc(subtitle)}</text>'
            )

    parts.append(
        '<text x="28" y="510" font-family="Arial" font-size="11" fill="#555">In-sample concentration, not held-out accuracy.</text>'
    )
    parts.append("</svg>")
    out_svg.write_text("\n".join(parts), encoding="utf-8")


def write_markdown(
    outdir: Path, input_dir: Path, metrics: pd.DataFrame, T: pd.DataFrame
):
    clusters = metrics["cluster"].astype(int).tolist()
    names = cluster_names(T, clusters)
    rows = []
    for r in metrics.itertuples(index=False):
        rows.append(
            f"| {int(r.cluster)} | {names.get(int(r.cluster), '') or '—'} | {int(r.n_shifts):,} | {int(r.n_class_transitions):,} | {100 * r.top1_transition_concentration:.1f}% | {100 * r.top2_transition_coverage:.1f}% | {r.conditional_entropy_bits:.2f} |"
        )

    best = (
        metrics.sort_values("top1_transition_concentration", ascending=False).iloc[0]
        if not metrics.empty
        else None
    )
    worst = (
        metrics.sort_values("top1_transition_concentration", ascending=True).iloc[0]
        if not metrics.empty
        else None
    )

    md = f"""# AMR-HUB trigram clusters

Built from the trigram outputs in `{input_dir}`. Each rostered shift is represented by the
proportions of its three-event motifs (e.g. `WS → WS → FS`). Role, roster unit and room
coverage are not used to define the clusters.

## Cluster embedding

![Cluster dot plot](01_cluster_dot_plot.svg)

One dot per shift; 2-D projection of the trigram features. Labels show the two most common
motifs per cluster.

## Transition matrices by cluster

![Transition matrices within clusters](02_transition_matrices_by_cluster.svg)

Rows: current class. Columns: next class. Calculated only from shifts in each cluster;
`n` is the number of transitions behind each cell.

## Transition concentration

![Transition concentration](03_cluster_transition_concentration.svg)

Share of transitions that go to the most common next class for each current class.
In-sample, not held-out accuracy.

| Cluster | Most common motifs | Shifts | Class transitions | Top-1 concentration | Top-2 coverage | Conditional entropy (bits) |
|---:|---|---:|---:|---:|---:|---:|
{chr(10).join(rows)}
"""
    if best is not None and worst is not None:
        md += f"""
Highest concentration: cluster {int(best.cluster)} ({100 * best.top1_transition_concentration:.1f}%).
Lowest: cluster {int(worst.cluster)} ({100 * worst.top1_transition_concentration:.1f}%).
"""

    md += """
## Files

- `01_cluster_dot_plot.svg`, `cluster_embedding_coordinates.csv`
- `02_transition_matrices_by_cluster.svg`, `cluster_transition_probabilities_long.csv`,
  `cluster_<n>_transition_probability_matrix.csv`
- `03_cluster_transition_concentration.svg`, `cluster_predictability_proxy.csv`
"""
    (outdir / "CLUSTER_MEETING_BRIEF.md").write_text(md, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(
        description="Cluster profiles from existing trigram outputs."
    )
    ap.add_argument(
        "--input",
        default="/outputs/activity_exploration",
        help="Existing activity_exploration folder",
    )
    ap.add_argument("--out", default="/outputs/cluster_meeting", help="Output folder")
    args = ap.parse_args()

    input_dir = discover_input_folder(Path(args.input))
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    print(f"[input] {input_dir}")
    print(f"[output] {outdir}")
    F, A, T, P = load_inputs(input_dir)

    print("[1/4] cluster dot plot")
    make_cluster_embedding(
        F,
        A,
        T,
        outdir / "01_cluster_dot_plot.svg",
        outdir / "cluster_embedding_coordinates.csv",
    )

    print("[2/4] cluster-specific transition probabilities")
    counts = aggregate_cluster_transitions(A, P, outdir)
    make_transition_matrix_svg(
        counts, T, outdir / "02_transition_matrices_by_cluster.svg"
    )

    print("[3/4] descriptive predictability proxy")
    metrics = predictability_metrics(
        counts, A, outdir / "cluster_predictability_proxy.csv"
    )
    make_predictability_svg(
        metrics, T, outdir / "03_cluster_transition_concentration.svg"
    )

    print("[4/4] markdown summary")
    write_markdown(outdir, input_dir, metrics, T)

    print("\nDone. Open:")
    print(outdir / "CLUSTER_MEETING_BRIEF.md")


if __name__ == "__main__":
    main()
