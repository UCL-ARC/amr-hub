#!/usr/bin/env python3
from __future__ import annotations
import argparse
import random
from pathlib import Path
from collections import Counter, defaultdict
import duckdb
import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

MODEL_STATES = {
    "majority": None,
    "markov_current_class": ["current_class"],
    "current_plus_previous_class": ["current_class", "prev_class"],
    "plus_time_role": ["current_class", "prev_class", "time_bucket_label", "role"],
    "full_context": [
        "current_class",
        "prev_class",
        "time_bucket_label",
        "role",
        "roster_unit",
    ],
}
MODEL_LABELS = {
    "majority": "Majority",
    "markov_current_class": "Current class",
    "current_plus_previous_class": "Current + previous",
    "plus_time_role": "+ time + role",
    "full_context": "Full context",
}
SCOPE_LABELS = {
    "global": "All training shifts",
    "time_bucket_label": "Time-specific",
    "role": "Role-specific",
    "roster_unit": "Unit-specific",
}


def load_events(path: Path) -> pd.DataFrame:
    con = duckdb.connect(":memory:")
    try:
        df = con.execute(
            f"select * from read_parquet('{str(path).replace(chr(39), chr(39) * 2)}')"
        ).df()
    finally:
        con.close()
    req = {
        "shift_id",
        "event_index",
        "interaction_class",
        "time_bucket",
        "role",
        "roster_unit",
    }
    miss = sorted(req - set(df.columns))
    if miss:
        raise SystemExit(f"Missing columns in canonical_events.parquet: {miss}")
    df = df.sort_values(["shift_id", "event_index"]).reset_index(drop=True)
    df["interaction_class"] = df["interaction_class"].astype(str)
    df["role"] = df["role"].fillna("unknown").astype(str)
    df["roster_unit"] = df["roster_unit"].fillna("unknown").astype(str)
    df["time_bucket"] = (
        pd.to_numeric(df["time_bucket"], errors="coerce").fillna(-1).astype(int)
    )
    df["time_bucket_label"] = (
        df["time_bucket"]
        .map(
            {
                0: "00-06 overnight",
                1: "06-12 morning",
                2: "12-18 afternoon",
                3: "18-24 evening/night",
            }
        )
        .fillna("unknown")
    )
    return df


def split_shifts(events, train_fraction, seed, max_test_shifts):
    ids = sorted(events.shift_id.dropna().astype(int).unique().tolist())
    rng = random.Random(seed)
    rng.shuffle(ids)
    cut = max(1, min(len(ids) - 1, int(len(ids) * train_fraction)))
    train_ids = set(ids[:cut])
    test_list = ids[cut:]
    if max_test_shifts:
        test_list = test_list[:max_test_shifts]
    test_ids = set(test_list)
    return (
        events[events.shift_id.isin(train_ids)].copy(),
        events[events.shift_id.isin(test_ids)].copy(),
        train_ids,
        test_ids,
    )


def make_pairs(df):
    x = df.sort_values(["shift_id", "event_index"]).copy()
    g = x.groupby("shift_id", sort=False)
    x["prev_class"] = g["interaction_class"].shift(1)
    x["current_class"] = x["interaction_class"]
    x["action"] = g["interaction_class"].shift(-1)
    x = x[x.action.notna()].copy()
    return x[
        [
            "shift_id",
            "event_index",
            "current_class",
            "prev_class",
            "action",
            "time_bucket_label",
            "role",
            "roster_unit",
        ]
    ]


def key(vals):
    return tuple(None if pd.isna(v) else str(v) for v in vals)


def fit_policy(pairs, cols):
    if cols is None:
        return None
    counts = defaultdict(Counter)
    for r in pairs.itertuples(index=False):
        d = r._asdict()
        counts[key([d[c] for c in cols])][str(d["action"])] += 1
    return {
        st: sorted(ctr.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        for st, ctr in counts.items()
    }


def fit_scope(train_pairs, scope, model, min_pairs):
    cols = MODEL_STATES[model]
    gctr = Counter(train_pairs.action.astype(str))
    maj = sorted(gctr.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    pack = {
        "scope": scope,
        "model": model,
        "cols": cols,
        "majority": maj,
        "global_policy": fit_policy(train_pairs, cols),
        "seg_policy": {},
        "seg_majority": {},
    }
    if scope != "global":
        for val, sub in train_pairs.groupby(scope, dropna=False):
            if len(sub) < min_pairs:
                continue
            ctr = Counter(sub.action.astype(str))
            pack["seg_majority"][str(val)] = sorted(
                ctr.items(), key=lambda kv: (-kv[1], kv[0])
            )[0][0]
            pack["seg_policy"][str(val)] = fit_policy(sub, cols)
    return pack


def predict(pack, ctx):
    if pack["model"] == "majority":
        if pack["scope"] != "global":
            return pack["seg_majority"].get(
                str(ctx.get(pack["scope"], "unknown")), pack["majority"]
            ), True
        return pack["majority"], True
    st = key([ctx.get(c) for c in pack["cols"]])
    if pack["scope"] != "global":
        seg = str(ctx.get(pack["scope"], "unknown"))
        pol = pack["seg_policy"].get(seg)
        if pol is not None and st in pol:
            return pol[st], True
    if pack["global_policy"] is not None and st in pack["global_policy"]:
        return pack["global_policy"][st], True
    if pack["scope"] != "global":
        seg = str(ctx.get(pack["scope"], "unknown"))
        if seg in pack["seg_majority"]:
            return pack["seg_majority"][seg], False
    return pack["majority"], False


def rollout_shift(sdf, pack, seed_events):
    sdf = sdf.sort_values("event_index").reset_index(drop=True)
    actual = sdf.interaction_class.astype(str).tolist()
    n = len(actual)
    if n <= seed_events:
        return None
    gen = actual[:seed_events].copy()
    unseen = 0
    correct = []
    first_error = -1
    for j in range(seed_events, n):
        i = j - 1
        ctx = {
            "current_class": gen[j - 1],
            "prev_class": gen[j - 2] if j >= 2 else None,
            "time_bucket_label": sdf.loc[i, "time_bucket_label"],
            "role": sdf.loc[i, "role"],
            "roster_unit": sdf.loc[i, "roster_unit"],
        }
        pred, seen = predict(pack, ctx)
        gen.append(pred)
        ok = int(pred == actual[j])
        correct.append(ok)
        if not seen:
            unseen += 1
        if first_error < 0 and not ok:
            first_error = j
    denom = max(1, n - seed_events)
    classes = sorted(set(actual[seed_events:]) | set(gen[seed_events:]))
    a = Counter(actual[seed_events:])
    b = Counter(gen[seed_events:])
    tv = 0.5 * sum(abs(a.get(c, 0) / denom - b.get(c, 0) / denom) for c in classes)
    pref = 0
    for ok in correct:
        if ok:
            pref += 1
        else:
            break
    return {
        "shift_id": int(sdf.loc[0, "shift_id"]),
        "seed_events": seed_events,
        "scope": pack["scope"],
        "model": pack["model"],
        "sequence_length": n,
        "predicted_events": n - seed_events,
        "rollout_accuracy": float(np.mean(correct)),
        "exact_suffix_match": int(all(correct)),
        "correct_prefix_after_seed": pref,
        "first_error_position": first_error,
        "unseen_state_fraction": unseen / denom,
        "class_composition_TV_distance": float(tv),
        "actual_sequence": " → ".join(actual[:60]),
        "generated_sequence": " → ".join(gen[:60]),
        "sequence_truncated_at_60": int(n > 60),
    }


def export_markov(pairs, outdir, min_pairs):
    blocks = []

    def add(gtype, gval, sub):
        c = (
            sub.groupby(["current_class", "action"])
            .size()
            .reset_index(name="transition_count")
            .rename(columns={"current_class": "from_class", "action": "to_class"})
        )
        if c.empty:
            return
        c["from_total"] = c.groupby("from_class").transition_count.transform("sum")
        c["probability"] = c.transition_count / c.from_total
        c["group_type"] = gtype
        c["group_value"] = str(gval)
        blocks.append(
            c[
                [
                    "group_type",
                    "group_value",
                    "from_class",
                    "to_class",
                    "transition_count",
                    "from_total",
                    "probability",
                ]
            ]
        )

    add("global", "all", pairs)
    for col, gtype in [
        ("time_bucket_label", "time_bucket"),
        ("role", "role"),
        ("roster_unit", "roster_unit"),
    ]:
        for val, sub in pairs.groupby(col, dropna=False):
            if len(sub) >= min_pairs:
                add(gtype, val, sub)
    df = pd.concat(blocks, ignore_index=True)
    df.to_csv(outdir / "markov_transition_probabilities_by_segment.csv", index=False)
    return df


def matrix(df, gtype, gval):
    s = df[(df.group_type.eq(gtype)) & (df.group_value.eq(str(gval)))]
    if s.empty:
        return pd.DataFrame()
    cats = sorted(set(s.from_class) | set(s.to_class))
    return (
        s.pivot(index="from_class", columns="to_class", values="probability")
        .reindex(index=cats, columns=cats)
        .fillna(0)
    )


def plot_time_matrices(markov, outdir):
    vals = ["all"] + sorted(
        markov[markov.group_type.eq("time_bucket")]
        .group_value.drop_duplicates()
        .tolist()
    )
    labs = ["All"] + [str(v) for v in vals[1:]]
    mats = [matrix(markov, "global" if v == "all" else "time_bucket", v) for v in vals]
    mats = [m for m in mats if not m.empty]
    if not mats:
        return
    cats = sorted(set().union(*[set(m.index) | set(m.columns) for m in mats]))
    n = len(mats)
    fig, axes = plt.subplots(1, n, figsize=(4.5 * n, 4.5), squeeze=False)
    vmax = max(float(m.to_numpy().max()) for m in mats) or 1
    for ax, m, lab in zip(axes[0], mats, labs):
        mm = m.reindex(index=cats, columns=cats).fillna(0)
        im = ax.imshow(mm.to_numpy(), vmin=0, vmax=vmax, aspect="auto")
        ax.set_title(lab)
        ax.set_xticks(range(len(cats)))
        ax.set_yticks(range(len(cats)))
        ax.set_xticklabels(cats, rotation=45, ha="right", fontsize=8)
        ax.set_yticklabels(cats, fontsize=8)
        for i in range(len(cats)):
            for j in range(len(cats)):
                if mm.iloc[i, j] > 0:
                    ax.text(
                        j,
                        i,
                        f"{mm.iloc[i, j]:.2f}",
                        ha="center",
                        va="center",
                        fontsize=8,
                    )
    fig.suptitle("Markov transition probabilities by time of day", y=1.02)
    fig.colorbar(im, ax=axes.ravel().tolist(), fraction=0.018, pad=0.02)
    fig.savefig(
        outdir / "01_markov_transition_matrices_by_time.png",
        dpi=180,
        bbox_inches="tight",
    )
    plt.close(fig)


def summarise(rollouts, outdir):
    s = (
        rollouts.groupby(["scope", "model", "seed_events"])
        .agg(
            test_shifts=("shift_id", "nunique"),
            mean_accuracy=("rollout_accuracy", "mean"),
            median_accuracy=("rollout_accuracy", "median"),
            exact_suffix_match_rate=("exact_suffix_match", "mean"),
            mean_correct_prefix=("correct_prefix_after_seed", "mean"),
            mean_unseen_state_fraction=("unseen_state_fraction", "mean"),
            mean_TV_distance=("class_composition_TV_distance", "mean"),
            median_TV_distance=("class_composition_TV_distance", "median"),
        )
        .reset_index()
    )
    s.to_csv(outdir / "rollout_summary_by_seed.csv", index=False)
    return s


def plot_lines(
    summary,
    outdir,
    metric,
    fname,
    title,
    ylabel,
    scope_filter="global",
    model_filter=None,
):
    sub = summary.copy()
    if scope_filter is not None:
        sub = sub[sub.scope.eq(scope_filter)]
    if model_filter is not None:
        sub = sub[sub.model.isin(model_filter)]
    if sub.empty:
        return
    fig, ax = plt.subplots(figsize=(9.5, 5.5))
    sub["label"] = sub.apply(
        lambda r: (
            SCOPE_LABELS.get(r.scope, r.scope)
            + "\n"
            + MODEL_LABELS.get(r.model, r.model)
        )
        if scope_filter is None
        else MODEL_LABELS.get(r.model, r.model),
        axis=1,
    )
    for lab, g in sub.groupby("label"):
        y = g[metric].to_numpy() * 100 if "accuracy" in metric else g[metric].to_numpy()
        ax.plot(g.seed_events, y, marker="o", label=lab)
    ax.set_title(title)
    ax.set_xlabel("Number of real events used to seed rollout")
    ax.set_ylabel(ylabel)
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8, ncol=2)
    if "accuracy" in metric:
        ax.set_ylim(0, 100)
    fig.tight_layout()
    fig.savefig(outdir / fname, dpi=180)
    plt.close(fig)


def write_docs(outdir):
    brief = """# AMR-HUB rollout and Markov demo

Input: `learnability_analysis/canonical_events.parquet`.

## Markov transitions by time of day
![Markov by time](01_markov_transition_matrices_by_time.png)

## Rollout accuracy by seed length (global policies)
![Rollout accuracy](02_global_models_rollout_accuracy_by_seed.png)

First N real events given, the rest generated recursively.

## Global vs context-split policies
![Context-split accuracy](03_context_split_rollout_accuracy_by_seed.png)

## Class-mix deviation (TV distance, lower is better)
![Global deviation](04_global_models_rollout_deviation_by_seed.png)

![Split deviation](05_context_split_rollout_deviation_by_seed.png)

## Correct prefix after seed
![Correct prefix](06_global_models_correct_prefix_by_seed.png)
"""
    irl = """# IRL design notes

Candidate state: current room, previous room, current event class, previous event class,
time bucket, role, roster unit.

Candidate reward features: event-class persistence and switching, staying in or changing
room, returning to recent rooms, time-, role- and unit-compatible destinations, movement cost.

If time/role/unit-specific rollouts are more plausible, use separate policies for those
contexts or include them as reward features.

Predictive importance of a state variable is not its reward weight.
"""
    (outdir / "ADVANCED_DEMO_BRIEF.md").write_text(brief, encoding="utf-8")
    (outdir / "IRL_REWARD_DESIGN_NOTES.md").write_text(irl, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--events", default="/outputs/learnability_analysis/canonical_events.parquet"
    )
    ap.add_argument("--out", default="/outputs/advanced_demo_analysis")
    ap.add_argument("--train-fraction", type=float, default=0.80)
    ap.add_argument("--seed", type=int, default=20260813)
    ap.add_argument("--seed-events", default="1,2,3,5,10")
    ap.add_argument("--max-test-shifts", type=int, default=0)
    ap.add_argument("--min-segment-train-pairs", type=int, default=1000)
    ap.add_argument("--min-markov-segment-pairs", type=int, default=1000)
    args = ap.parse_args()
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    seeds = [int(x) for x in args.seed_events.split(",") if x.strip()]
    max_test = args.max_test_shifts if args.max_test_shifts > 0 else None
    ev = load_events(Path(args.events))
    tr, te, trids, teids = split_shifts(ev, args.train_fraction, args.seed, max_test)
    trp = make_pairs(tr)
    print(
        f"[data] events={len(ev):,}; train shifts={len(trids):,}; test shifts used={len(teids):,}; train pairs={len(trp):,}"
    )
    markov = export_markov(trp, outdir, args.min_markov_segment_pairs)
    plot_time_matrices(markov, outdir)
    specs = [("global", m) for m in MODEL_STATES] + [
        ("time_bucket_label", "current_plus_previous_class"),
        ("role", "current_plus_previous_class"),
        ("roster_unit", "current_plus_previous_class"),
        ("time_bucket_label", "full_context"),
    ]
    packs = [
        fit_scope(trp, scope, model, args.min_segment_train_pairs)
        for scope, model in specs
    ]
    rows = []
    for _, sdf in te.groupby("shift_id", sort=True):
        for seedn in seeds:
            for pack in packs:
                r = rollout_shift(sdf, pack, seedn)
                if r is not None:
                    rows.append(r)
    roll = pd.DataFrame(rows)
    roll.to_csv(outdir / "rollout_per_shift_by_seed.csv", index=False)
    summ = summarise(roll, outdir)
    ex = (
        roll[roll.seed_events.eq(2 if 2 in seeds else seeds[0])]
        .sort_values(["model", "rollout_accuracy"])
        .groupby("model")
        .head(3)
    )
    ex.to_csv(outdir / "rollout_examples.csv", index=False)
    meta = pd.DataFrame(
        [
            {"metric": "events_input", "value": len(ev)},
            {"metric": "shifts_input", "value": ev.shift_id.nunique()},
            {"metric": "train_shifts", "value": len(trids)},
            {"metric": "test_shifts_used", "value": len(teids)},
            {"metric": "seed_events_tested", "value": ",".join(map(str, seeds))},
        ]
    )
    meta.to_csv(outdir / "advanced_demo_summary.csv", index=False)
    plot_lines(
        summ,
        outdir,
        "mean_accuracy",
        "02_global_models_rollout_accuracy_by_seed.png",
        "Free-running rollout accuracy by seed length",
        "Mean rollout accuracy (%)",
        "global",
    )
    plot_lines(
        summ,
        outdir,
        "mean_accuracy",
        "03_context_split_rollout_accuracy_by_seed.png",
        "Global policy vs context-split policies",
        "Mean rollout accuracy (%)",
        None,
        ["current_plus_previous_class", "full_context"],
    )
    plot_lines(
        summ,
        outdir,
        "mean_TV_distance",
        "04_global_models_rollout_deviation_by_seed.png",
        "Rollout deviation from actual class composition",
        "Mean total-variation distance (lower is better)",
        "global",
    )
    plot_lines(
        summ,
        outdir,
        "mean_TV_distance",
        "05_context_split_rollout_deviation_by_seed.png",
        "Does splitting training data reduce rollout composition error?",
        "Mean total-variation distance (lower is better)",
        None,
        ["current_plus_previous_class", "full_context"],
    )
    plot_lines(
        summ,
        outdir,
        "mean_correct_prefix",
        "06_global_models_correct_prefix_by_seed.png",
        "How long does rollout stay correct after seed?",
        "Mean correct events before first error",
        "global",
    )
    write_docs(outdir)
    print("\n=== COMPLETE ===")
    print(summ.to_string(index=False))
    print(f"\nSaved to {outdir}")


if __name__ == "__main__":
    main()
